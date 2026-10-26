"""Verify final splitter corrections preserve the frozen synthetic holdout."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.core.database import Database
from app.services.forecast_accuracy import compute_location_accuracy
from app.services.location_forecast import split_run_by_location


async def main():
    out = Path(__file__).resolve().parent
    evidence = json.loads((out / 'holdout-api.json').read_text(encoding='utf-8'))
    tenant = uuid.UUID(next(e['body']['tenant_id'] for e in evidence if e['label'] == 'create_clean_tenant'))
    run = uuid.UUID(next(e['body']['run_id'] for e in evidence if e['label'] == 'forecast_before_holdout_import'))
    db = Database(get_settings().model_copy(update={'database_url': os.environ['BENCH_DATABASE_URL']}))
    await db.assert_tenant_isolation_enforced(strict=True)
    query = text('SELECT sku_id, location_id, forecast_date, p10, p50, p90, share '
                 'FROM location_forecast_results WHERE run_id = :r ORDER BY sku_id, location_id, forecast_date')
    try:
        async with db.session(str(tenant)) as session:
            before = (await session.execute(query, {'r': str(run)})).all()
            await split_run_by_location(session, tenant_id=tenant, industry='fashion', run_id=run,
                                        now=datetime(2026, 8, 31, tzinfo=UTC))
            after = (await session.execute(query, {'r': str(run)})).all()
            assert before == after, 'The final splitter changed the frozen holdout bands'
            accuracy = await compute_location_accuracy(session, tenant_id=tenant, industry='fashion', run_id=run)
        expected = json.loads((out / 'holdout-mase.json').read_text(encoding='utf-8'))
        assert accuracy == expected, (accuracy, expected)
        result = {'cutoff': '2026-08-31', 'quantile_rows_unchanged': len(after), 'accuracy': accuracy}
        (out / 'holdout-final-recheck.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
