"""The test suite must never reach third-party services through the app lifespan.

Regression for the order-dependent failure of
``test_regional_demand_connector_fetch``: every test that used the ``client``
fixture started the live signal pipeline, which called Google Trends, Reddit,
FRED and others from the test process. A real 429 from Google opened the shared
Trends cooldown, and a later, fully mocked test then returned no samples.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_app_lifespan_does_not_poll_live_signal_sources(setup_schema, monkeypatch):
    from app.config import get_settings
    from app.main import create_app
    from app.services.external_signals.signal_pipeline import SignalIngestionPipeline

    calls: list[int] = []

    async def _record_run(self) -> dict[str, int]:
        calls.append(1)
        return {}

    monkeypatch.setattr(SignalIngestionPipeline, "run_once", _record_run)
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        # The singleton loops start from a background leader task; give it
        # ample time to run the pipeline's immediate first fetch if enabled.
        await asyncio.sleep(2.0)

    assert calls == []
