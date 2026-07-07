"""Signal ingestion pipeline orchestrator.

Periodically:
  1. fans out fetch() across all enabled connectors per industry
  2. persists samples into `trend_signals` (global rows; tenant_id NULL)
  3. emits a `signals.updated` realtime event for live UI refresh

The scheduler loop runs on the backend lifespan (see app/main.py wiring).
Connectors are designed to never raise on network failure — they emit
synthetic samples instead so the platform stays demoable offline.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from app.services.external_signals.base import SignalConnector, SignalSample
from app.services.external_signals.competitor_price_connector import CompetitorPriceConnector
from app.services.external_signals.fda_connector import FdaConnector
from app.services.external_signals.fred_connector import FredConnector
from app.services.external_signals.logistics_connector import LogisticsConnector
from app.services.external_signals.reddit_connector import RedditConnector
from app.services.external_signals.regional_demand_connector import RegionalDemandConnector
from app.services.external_signals.rss_connector import RssConnector
from app.services.external_signals.trends_connector import GoogleTrendsConnector
from app.services.external_signals.visual_connector import (
    InstagramConnector,
    PinterestConnector,
    TikTokConnector,
)
from app.services.external_signals.weather_connector import WeatherConnector
from app.services.industry_context import INDUSTRY_REGISTRY

if TYPE_CHECKING:
    from app.core.database import Database
    from app.realtime.connection_manager import ConnectionManager

log = structlog.get_logger(__name__)


# Drive ingestion off the archetype registry so a new industry starts producing
# signals without editing this tuple (previously hardcoded, and missing "hardware").
INDUSTRIES = tuple(INDUSTRY_REGISTRY.keys())


class SignalIngestionPipeline:
    def __init__(
        self,
        db: Database,
        realtime: ConnectionManager | None = None,
        connectors: list[SignalConnector] | None = None,
        poll_interval_s: int = 900,  # 15 min default
    ):
        self.db = db
        self.realtime = realtime
        self.connectors: list[SignalConnector] = connectors or [
            FredConnector(),
            GoogleTrendsConnector(),
            RedditConnector(),
            RssConnector(),
            PinterestConnector(),
            TikTokConnector(),
            InstagramConnector(),
            WeatherConnector(),
            CompetitorPriceConnector(),
            FdaConnector(),
            LogisticsConnector(),
            RegionalDemandConnector(),
        ]
        self.poll_interval_s = poll_interval_s
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="signal-pipeline")
        log.info(
            "signal_pipeline.started",
            interval_s=self.poll_interval_s,
            connectors=[c.name for c in self.connectors],
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        log.info("signal_pipeline.stopped")

    async def _run_loop(self) -> None:
        # initial fetch right away so the dashboard isn't blank
        try:
            await self.run_once()
        except Exception as exc:
            log.error("signal_pipeline.first_run.failed", error=str(exc))

        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_s)
                break  # stop event fired
            except TimeoutError:
                pass
            try:
                await self.run_once()
            except Exception as exc:
                log.error("signal_pipeline.tick.failed", error=str(exc))

    # ── one cycle ────────────────────────────────────────────────────────────

    async def run_once(self) -> dict[str, int]:
        """Fetch from every connector × industry, persist, broadcast.

        Returns count of samples persisted per industry.
        """
        counts: dict[str, int] = {}
        for industry in INDUSTRIES:
            samples = await self._gather_industry(industry)
            if not samples:
                counts[industry] = 0
                continue
            await self._persist(samples)
            counts[industry] = len(samples)
            await self._broadcast(industry, samples)
        log.info("signal_pipeline.tick", counts=counts)
        return counts

    async def _gather_industry(self, industry: str) -> list[SignalSample]:
        tasks = [c.fetch(industry) for c in self.connectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[SignalSample] = []
        for connector, res in zip(self.connectors, results, strict=False):
            if isinstance(res, BaseException):
                log.warning(
                    "signal_pipeline.connector.error",
                    connector=connector.name,
                    industry=industry,
                    error=str(res),
                )
                continue
            out.extend(res)
        return out

    async def _persist(self, samples: list[SignalSample]) -> None:
        """Insert as global signals (tenant_id NULL). RLS is bypassed for the
        ingest worker via session_no_rls()."""
        from app.models.enums import (
            IndustryCode,
            TrendSignalKind,
            TrendSignalSource,
        )
        from app.models.trend import TrendSignal

        async with self.db.session_no_rls() as session:
            for s in samples:
                try:
                    row = TrendSignal(
                        tenant_id=None,
                        industry=IndustryCode(s.industry),
                        source=TrendSignalSource(s.source),
                        kind=TrendSignalKind(s.kind),
                        series_key=s.series_key,
                        category_tags=list(s.category_tags),
                        sku_tags=list(s.sku_tags),
                        region=s.region,
                        raw_value=Decimal(str(s.raw_value)) if s.raw_value is not None else None,
                        normalized_score=Decimal(str(round(s.normalized_score, 4))),
                        confidence=Decimal(str(round(s.confidence, 4))),
                        captured_at=s.captured_at,
                        ingested_at=datetime.now(UTC),
                        payload=s.payload,
                    )
                    session.add(row)
                except Exception as exc:
                    log.warning(
                        "signal_pipeline.persist.row_failed",
                        source=s.source,
                        series=s.series_key,
                        error=str(exc),
                    )

    async def _broadcast(self, industry: str, samples: list[SignalSample]) -> None:
        """Fan out a signals.updated event to every currently connected tenant.

        We don't store tenant-scoped copies for global signals (RLS reads them
        via the IS NULL OR match policy), but we still want sockets to know
        new data is available so the UI can refetch."""
        if self.realtime is None:
            return
        from app.realtime.events import RealtimeEvent

        avg = sum(s.normalized_score for s in samples) / len(samples)
        connected_tenants = list(self.realtime._connections.keys())  # noqa: SLF001
        if not connected_tenants:
            return
        for tenant_id in connected_tenants:
            try:
                evt = RealtimeEvent(
                    type="signals.updated",
                    tenant_id=tenant_id,
                    industry=industry,
                    data={
                        "sample_count": len(samples),
                        "aggregate_score": round(avg, 4),
                        "by_source": {
                            c.name: sum(1 for s in samples if s.source == c.name)
                            for c in self.connectors
                        },
                    },
                )
                await self.realtime.publish(evt)
            except Exception as exc:
                log.warning(
                    "signal_pipeline.broadcast.failed",
                    tenant=str(tenant_id),
                    error=str(exc),
                )
