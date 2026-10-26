"""Reproduce the synthetic Swecha holdout through the normal upload API.

The isolated API and ML processes must use the same disposable database.
MIGRATION_DATABASE_URL is used only to grant this synthetic fixture entitlement.
No access tokens or passwords are written to evidence files.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
DATA = ROOT / 'data/demo-swecha'


async def entitlement(tenant):
    engine = create_async_engine(os.environ['MIGRATION_DATABASE_URL'])
    try:
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO subscriptions (id, tenant_id, plan_id, status, "
                "current_period_start, current_period_end, cancel_at_period_end, metadata) "
                "VALUES (gen_random_uuid(), :t, 'enterprise_monthly', 'active', now(), "
                "now() + interval '7 days', FALSE, jsonb_build_object('source','synthetic_test'))"),
                {'t': tenant})
    finally:
        await engine.dispose()


def main():
    evidence = []
    client = httpx.Client(base_url=os.getenv('HOLDOUT_API_URL', 'http://127.0.0.1:8012/api/v1'), timeout=600)
    def call(label, method, path, **kwargs):
        started = time.perf_counter()
        response = client.request(method, path, **kwargs)
        body = response.json()
        safe = {k: v for k, v in body.items() if 'token' not in k} if isinstance(body, dict) else body
        evidence.append({'label': label, 'method': method, 'path': path, 'status': response.status_code,
                         'seconds': round(time.perf_counter() - started, 3), 'body': safe})
        (OUT / 'holdout-api.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        print(label, response.status_code, flush=True)
        response.raise_for_status()
        return body

    slug = f'location-holdout-{uuid.uuid4().hex[:8]}'
    email = f'{slug}@example.com'
    password = 'SyntheticHoldout2026!'
    workspace = call('create_clean_tenant', 'POST', '/auth/signup', json={
        'name': 'Synthetic location holdout', 'email': email, 'password': password,
        'tenant_slug': slug, 'industry': 'fashion'})
    asyncio.run(entitlement(workspace['tenant_id']))
    auth = call('login', 'POST', '/auth/dev-login', json={'email': email, 'password': password, 'tenant_slug': slug})
    client.headers['Authorization'] = 'Bearer ' + auth['access_token']
    def upload(filename, kind):
        return call(filename, 'POST', '/integrations/upload', data={'kind': kind, 'identity': 'period', 'currency': 'INR'},
                    files={'file': (filename, (DATA / filename).read_bytes(), 'text/csv')})
    upload('00-products.csv', 'products')
    for filename in ['01-steady-training.csv', '02-seasonal-training.csv', '03-intermittent-training.csv']:
        upload(filename, 'sales')
    upload('05-inventory.csv', 'inventory')
    forecast = call('forecast_before_holdout_import', 'POST', '/forecasts/generate',
                    json={'horizon': 8, 'force_zero_shot': True})
    assert forecast['history_end'] == '2026-08-31', forecast
    assert forecast['first_forecast_week'] == '2026-08-31', forecast
    upload('04-heldout-8-weeks.csv', 'sales')
    accuracy = call('holdout_accuracy', 'GET', '/forecast/accuracy')
    locations = accuracy['locations']
    assert {r['location'] for r in locations['locations']} == {'alwal', 'boduppal'}, locations
    assert locations['weighted_mase'] is not None, locations
    (OUT / 'holdout-mase.json').write_text(json.dumps(locations, indent=2), encoding='utf-8')
    print(json.dumps(locations, indent=2), flush=True)


if __name__ == '__main__':
    main()
