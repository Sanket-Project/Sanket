"""Confirmed formats contain configuration only, never input rows."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import text


def issue_analysis(secret, tenant, actor, kind, content, tables, *, lifetime_s=1800, overrides=None, profile_revisions=None):
    now = datetime.now(UTC)
    return jwt.encode({"purpose": "import_analysis", "tenant": str(tenant), "actor": str(actor),
                       "kind": kind, "digest": hashlib.sha256(content).hexdigest(), "tables": tables,
                       "overrides": overrides or {}, "profiles": profile_revisions or {}, "version": "1", "jti": uuid.uuid4().hex,
                       "iat": now, "exp": now + timedelta(seconds=lifetime_s)}, secret, algorithm="HS256")


def verify_analysis(token, secret, tenant, actor, kind, content):
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "iat", "jti"]})
        expected = {"purpose": "import_analysis", "tenant": str(tenant), "actor": str(actor),
                    "kind": kind, "digest": hashlib.sha256(content).hexdigest(), "version": "1"}
        if any(claims.get(key) != value for key, value in expected.items()):
            raise ValueError()
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        raise ValueError("File analysis is stale or invalid; analyze this file again") from None


async def load_profile(session, tenant, kind, fingerprint):
    row = (await session.execute(text("""SELECT id,mapping,column_types,options,revision
        FROM import_mapping_profiles WHERE tenant_id=:t AND kind=:k AND fingerprint=:f"""),
        {"t": tenant, "k": kind, "f": fingerprint})).mappings().first()
    return dict(row) if row else None


async def save_profile(session, tenant, kind, fingerprint, mapping, column_types, *, expected_revision, options=None):
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                          {"key": f"import-profile:{tenant}:{kind}:{fingerprint}"})
    old = await load_profile(session, tenant, kind, fingerprint)
    if (old["revision"] if old else 0) != expected_revision:
        raise ValueError("Saved format changed concurrently; analyze the file again")
    if old and old["options"].get("disabled") is True:
        options = {**(options or {}), "disabled": True}
    if old and old["mapping"] == mapping and old["column_types"] == column_types and old["options"] == (options or {}):
        return old["revision"]
    revision = expected_revision + 1
    await session.execute(text("""INSERT INTO import_mapping_profiles
        (tenant_id,kind,fingerprint,mapping,column_types,options,revision)
        VALUES (:t,:k,:f,CAST(:m AS jsonb),CAST(:c AS jsonb),CAST(:o AS jsonb),:r)
        ON CONFLICT (tenant_id,kind,fingerprint) DO UPDATE SET mapping=EXCLUDED.mapping,
        column_types=EXCLUDED.column_types,options=EXCLUDED.options,revision=EXCLUDED.revision,
        updated_at=clock_timestamp()"""),
        {"t": tenant, "k": kind, "f": fingerprint, "m": json.dumps(mapping),
         "c": json.dumps(column_types), "o": json.dumps(options or {}), "r": revision})
    return revision


async def _manager(db, session, ctx):
    from app.services.llm.policy import PolicyStore
    user, _, _ = await PolicyStore(db)._rows(session, ctx, lock=True)
    if user.role not in {"owner", "admin"}:
        raise ValueError("Only an owner or admin can manage saved formats")


async def list_profiles(db, ctx):
    async with db.session(str(ctx.tenant_id)) as session:
        await _manager(db, session, ctx)
        rows = (await session.execute(text("""SELECT id,kind,fingerprint,revision,updated_at,
            COALESCE(options->'disabled' = to_jsonb(true),false) AS disabled FROM import_mapping_profiles
            WHERE tenant_id=:t ORDER BY updated_at DESC LIMIT 1000"""), {"t": ctx.tenant_id})).mappings().all()
        return [dict(row) for row in rows]


async def manage_profile(db, ctx, profile_id, *, expected_revision, disabled):
    from app.services import audit
    if type(expected_revision) is not int or expected_revision < 1 or (disabled is not None and type(disabled) is not bool):
        raise ValueError("Invalid format revision or state")
    async with db.session(str(ctx.tenant_id)) as session:
        await _manager(db, session, ctx)
        row = (await session.execute(text("""SELECT options,revision FROM import_mapping_profiles
            WHERE id=:id AND tenant_id=:t FOR UPDATE"""), {"id": profile_id, "t": ctx.tenant_id})).mappings().first()
        if row is None or row["revision"] != expected_revision:
            raise ValueError("Saved format is unavailable or changed; refresh the list")
        args = {"id": profile_id, "t": ctx.tenant_id}
        if disabled is None:
            await session.execute(text("DELETE FROM import_mapping_profiles WHERE id=:id AND tenant_id=:t"), args)
        else:
            await session.execute(text("""UPDATE import_mapping_profiles SET options=CAST(:o AS jsonb),
                revision=revision+1,updated_at=clock_timestamp() WHERE id=:id AND tenant_id=:t"""),
                {**args, "o": json.dumps({**row["options"], "disabled": disabled})})
        await audit.record(session, tenant_id=ctx.tenant_id, user_id=ctx.user_id, industry=ctx.industry,
                           action="import.format.updated", entity_type="import_format", entity_id=str(profile_id), strict=True,
                           new_value={"deleted": disabled is None, "disabled": disabled})
