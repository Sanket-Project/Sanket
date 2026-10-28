"""Production read bounds at the 25k-SKU target, using persisted DB rows only."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import text

from tests.test_location_forecast_split import _forecast, _sku


async def test_25k_sku_forecast_reads_are_bounded_and_summary_reconciles(
    client, db_session, signed_in_workspace,
):
    tenant, headers = await signed_in_workspace()
    first_sku = await _sku(db_session, tenant, 'SCALE-00000')
    run = await _forecast(db_session, tenant, first_sku,
                          completed=datetime.now(UTC), weekly_p50=1)
    # Model the planner statistics immediately before a large import. Reads
    # must remain bounded before autovacuum has refreshed these statistics.
    await db_session.execute(text('ANALYZE skus'))
    await db_session.execute(text('ANALYZE forecast_results'))
    # One SQL insert creates the large catalogue. This tests read scalability,
    # not 25k API product writes or a prohibitively long real inference run.
    await db_session.execute(text("""
        INSERT INTO skus (id, tenant_id, product_id, industry, sku_code)
        SELECT md5(CAST(CAST(:t AS uuid) AS text) || ':' || CAST(n AS text))::uuid,
               :t, s.product_id, 'fashion', 'SCALE-' || lpad(CAST(n AS text), 5, '0')
        FROM generate_series(1, 24999) n CROSS JOIN skus s WHERE s.id=:s
    """), {'t': tenant, 's': first_sku})
    await db_session.execute(text("""
        INSERT INTO forecast_results
            (tenant_id,run_id,sku_id,forecast_date,p10,p50,p90,model_name)
        SELECT :t, :r, s.id, DATE '2026-10-26' + n * 7, 1, 1, 1, 'chronos_zero_shot'
        FROM skus s CROSS JOIN generate_series(0,7) n
        WHERE s.tenant_id=:t AND s.id<>:s
    """), {'t': tenant, 'r': run, 's': first_sku})
    # A second model row for one SKU must be averaged before portfolio summing.
    await db_session.execute(text("""
        INSERT INTO forecast_results
            (tenant_id,run_id,sku_id,forecast_date,p10,p50,p90,model_name)
        SELECT tenant_id,run_id,sku_id,forecast_date,2,2,2,'another-model'
        FROM forecast_results WHERE run_id=:r AND sku_id=:s
    """), {'r': run, 's': first_sku})
    await db_session.commit()

    summary = await client.get('/api/v1/forecasts/latest', headers=headers,
                               params={'view': 'summary'})
    assert summary.status_code == 200, summary.text
    portfolio = summary.json()['forecast']
    assert portfolio['total_skus'] == 25000
    assert len(portfolio['rows']) == 8
    assert all(row['p50'] == 25000.5 for row in portfolio['rows'])
    assert len(summary.content) < 20_000

    response = await asyncio.wait_for(client.get('/api/v1/forecasts/latest', headers=headers,
                                     params={'limit': 6, 'offset': 24996, 'run_id': str(run)}), timeout=10)
    assert response.status_code == 200, response.text
    page = response.json()['forecast']
    assert page['total_skus'] == 25000
    assert page['has_more'] is False
    assert len(page['rows']) == 4 * 8
    assert len({row['sku_id'] for row in page['rows']}) == 4
    assert len(page['sku_labels']) == 4
    assert len(response.content) < 20_000
