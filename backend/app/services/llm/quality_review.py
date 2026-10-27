"""A reviewed repair is bound to the current source-record snapshot."""
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import text

from app.services import audit, data_quality_audit
from app.services.integrations.file_import import _lock_sales_import
from app.services.llm.policy import PolicyStore


async def _authorize(session, db, ctx):
    user, _, _ = await PolicyStore(db)._rows(session, ctx, lock=True)
    if user.role not in {"owner", "admin"}:
        raise ValueError("Only an owner or admin can confirm a repair")
    await _lock_sales_import(session, ctx.tenant_id)


async def _fingerprint(session, ctx):
    return await session.scalar(text("""SELECT md5(COALESCE(string_agg(md5(h::text), '' ORDER BY h.id,h.sale_time),''))
        FROM historical_sales h WHERE h.tenant_id=:t AND h.industry=CAST(:i AS industry_code)"""),
        {"t": ctx.tenant_id, "i": ctx.industry.value})


async def preview_fix(db, ctx, secret, action):
    async with db.session(str(ctx.tenant_id)) as session:
        await _authorize(session, db, ctx)
        result = await data_quality_audit.apply_fix(session, tenant_id=ctx.tenant_id, industry=ctx.industry.value,
                                                   action=action, dry_run=True)
        fingerprint = await _fingerprint(session, ctx)
        result["preview_token"] = jwt.encode({"purpose": "quality_fix", "tenant": str(ctx.tenant_id),
            "actor": str(ctx.user_id), "industry": ctx.industry.value, "action": action, "fingerprint": fingerprint,
            "exp": datetime.now(UTC) + timedelta(minutes=10)}, secret, algorithm="HS256")
        return result


async def confirm_fix(db, ctx, secret, action, token):
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp"]})
        expected = {"purpose": "quality_fix", "tenant": str(ctx.tenant_id), "actor": str(ctx.user_id),
                    "industry": ctx.industry.value, "action": action}
        if any(claims.get(key) != value for key, value in expected.items()):
            raise ValueError()
    except (jwt.PyJWTError, ValueError, TypeError):
        raise ValueError("Repair preview is invalid or expired; preview again") from None
    async with db.session(str(ctx.tenant_id)) as session:
        await _authorize(session, db, ctx)
        if await _fingerprint(session, ctx) != claims["fingerprint"]:
            raise ValueError("Source records changed; preview the repair again")
        result = await data_quality_audit.apply_fix(session, tenant_id=ctx.tenant_id, industry=ctx.industry.value,
                                                   action=action, dry_run=False)
        await audit.record(session, tenant_id=ctx.tenant_id, user_id=ctx.user_id, industry=ctx.industry,
                           action="data_quality.fix", entity_type="historical_sales", strict=True,
                           new_value={"action": action, "rows_affected": result["rows_affected"]})
        return result
