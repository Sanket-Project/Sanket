"""Scheduled WhatsApp morning digest.

Runs on the leader replica only (like every other singleton loop) and, on each
tick, sends the digest to any tenant whose configured local send-hour has just
arrived and who has not already been sent one today.

Two things it deliberately does *not* do:

* send an "all clear" — a daily message with nothing in it trains people to
  ignore the channel, so an empty digest is skipped;
* claim success it cannot verify — with no provider credentials the console
  provider reports ``success=False`` and the tenant's ``last_sent_on`` stamp is
  left alone, so nothing is silently marked delivered.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import select

from app.models.tenant import Tenant
from app.services.notifications import digest as digest_svc
from app.services.notifications import whatsapp as wa

log = structlog.get_logger(__name__)


def _local_now(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone))
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("whatsapp.digest.bad_timezone", timezone=timezone)
        return datetime.now(UTC)


def _already_sent_today(settings: dict | None, today: date) -> bool:
    stamp = ((settings or {}).get("notifications") or {}).get("whatsapp_last_sent_on")
    return stamp == today.isoformat()


async def tick(db, app_settings, http_client=None) -> int:
    """One pass over every tenant. Returns the number of digests transmitted."""
    sent = 0

    async with db.session_no_rls() as session:
        tenants = list((await session.execute(select(Tenant))).scalars().all())

    for tenant in tenants:
        config = wa.load_tenant_config(tenant.settings)
        if not config.enabled or not config.recipients:
            continue

        local = _local_now(config.timezone)
        if local.hour != config.send_hour:
            continue
        if _already_sent_today(tenant.settings, local.date()):
            continue

        try:
            sent += await _send_for_tenant(
                db, app_settings, tenant.id, config, local.date(), http_client
            )
        except Exception as exc:  # noqa: BLE001 — one tenant must not stop the loop
            log.error("whatsapp.digest.tenant_failed", tenant_id=str(tenant.id), error=str(exc))

    return sent


async def _send_for_tenant(
    db,
    app_settings,
    tenant_id: uuid.UUID,
    config: wa.WhatsAppConfig,
    today: date,
    http_client,
) -> int:
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            return 0
        industry = str(tenant.industry)
        d = await digest_svc.build_digest(
            session,
            tenant_id=tenant_id,
            tenant_name=tenant.display_name,
            industry=industry,
            config=config,
        )

    if d.is_empty:
        log.info("whatsapp.digest.skipped_empty", tenant_id=str(tenant_id))
        return 0

    body = digest_svc.render_text(d)
    provider = wa.get_provider(app_settings, http_client)
    results = await wa.send_all(provider, recipients=config.recipients, body=body)
    delivered = sum(1 for r in results if r.success)

    if delivered:
        # Stamp only on real delivery, so a credential outage retries next tick
        # instead of skipping the day.
        async with db.session(str(tenant_id)) as session:
            tenant = await session.get(Tenant, tenant_id)
            if tenant is not None:
                settings = dict(tenant.settings or {})
                notifications = dict(settings.get("notifications") or {})
                notifications["whatsapp_last_sent_on"] = today.isoformat()
                settings["notifications"] = notifications
                tenant.settings = settings
                await session.flush()

    log.info(
        "whatsapp.digest.sent",
        tenant_id=str(tenant_id),
        provider=provider.name,
        recipients=len(config.recipients),
        delivered=delivered,
        items=len(d.items),
    )
    return delivered
