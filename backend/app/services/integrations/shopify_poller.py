"""Background poller for near-real-time Shopify sales.

Every ``poll_interval_s`` it enumerates connected Shopify integrations across
all tenants and pulls orders created since each connection's saved cursor,
upserting them into ``historical_sales`` and emitting a ``sale.created`` realtime
event. This is the localhost-friendly path; webhooks (when deployed publicly)
use the same ``ingest_*`` functions for instant updates.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import structlog
from sqlalchemy import select

from app.models.integration import IntegrationConnection
from app.services.integrations.shopify_sync import ingest_orders_incremental

if TYPE_CHECKING:
    from app.core.database import Database
    from app.realtime.connection_manager import ConnectionManager

log = structlog.get_logger(__name__)


class ShopifySalesPoller:
    def __init__(
        self,
        db: Database,
        realtime: ConnectionManager | None = None,
        poll_interval_s: int = 300,
        api_version: str = "2024-10",
    ) -> None:
        self.db = db
        self.realtime = realtime
        self.poll_interval_s = poll_interval_s
        self.api_version = api_version
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._http = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        self._task = asyncio.create_task(self._run_loop(), name="shopify-poller")
        log.info("shopify_poller.started", interval_s=self.poll_interval_s)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._http:
            await self._http.aclose()
            self._http = None
        log.info("shopify_poller.stopped")

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_s)
                break  # stop fired
            except TimeoutError:
                pass
            try:
                await self.run_once()
            except Exception as exc:  # noqa: BLE001
                log.error("shopify_poller.tick.failed", error=str(exc))

    async def run_once(self) -> int:
        """Poll every connected Shopify integration once. Returns #connections."""
        async with self.db.session_no_rls() as session:
            conns = (
                await session.scalars(
                    select(IntegrationConnection).where(
                        IntegrationConnection.provider == "shopify",
                        IntegrationConnection.status.in_(("connected", "syncing")),
                        IntegrationConnection.access_token_encrypted.isnot(None),
                    )
                )
            ).all()

        done = 0
        for conn in conns:
            try:
                await ingest_orders_incremental(
                    db=self.db,
                    tenant_id=conn.tenant_id,
                    connection=conn,
                    http_client=self._http,
                    api_version=self.api_version,
                    realtime=self.realtime,
                )
                done += 1
            except Exception as exc:  # noqa: BLE001 - one bad store shouldn't stop others
                log.warning(
                    "shopify_poller.connection.failed",
                    tenant=str(conn.tenant_id),
                    error=str(exc),
                )
        if done:
            log.info("shopify_poller.tick", connections=done)
        return done
