"""
Mint a dev JWT, call POST /api/v1/forecasts/generate for each industry,
print the real Chronos P10/P50/P90 results.

Run from: C:\\Users\\admin\\Desktop\\Sanket\\
Requires: pip install pyjwt requests psycopg2-binary
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt           # PyJWT
import psycopg2
import requests

JWT_SECRET = os.environ["JWT_SECRET"]
DB_DSN     = "host=localhost port=5432 dbname=sanket user=postgres password=postgres"
API_BASE   = "http://localhost:8000/api/v1"

INDUSTRIES = ["fashion", "electronics", "pharma", "agrocenter", "hardware"]

# Default recommended horizon per industry (matches Forecasts.tsx HORIZON_PRESETS)
DEFAULT_HORIZON = {
    "fashion":     12,
    "electronics": 12,
    "pharma":      52,
    "agrocenter":  26,
    "hardware":    16,
}


def get_tenant_info():
    """Pull tenant + owner user details from Postgres."""
    conn = psycopg2.connect(DB_DSN)
    cur  = conn.cursor()
    cur.execute("SELECT id FROM tenants LIMIT 1")
    tenant_id = str(cur.fetchone()[0])
    cur.execute(
        "SELECT id, email, role FROM users WHERE tenant_id = %s AND role = 'owner' LIMIT 1",
        (tenant_id,)
    )
    row = cur.fetchone()
    user_id, email, role = str(row[0]), row[1], row[2]
    cur.close()
    conn.close()
    return tenant_id, user_id, email, role


def mint_token(tenant_id: str, user_id: str, email: str, role: str, industry: str) -> str:
    """Mint an HS256 dev token matching the backend's mint_dev_token format."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "uid": user_id,
        "puid": user_id,
        "email": email,
        "tid": tenant_id,
        "role": role,
        "ind": industry,
        "industries": INDUSTRIES,
        "iat": now,
        "exp": now + timedelta(hours=2),
        "dev_identity": True,   # DEV_IDENTITY_MARKER = "dev_identity"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def generate_forecast(token: str, industry: str, horizon: int) -> dict:
    """POST /forecasts/generate with a long timeout (120 s)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "X-Industry-Code": industry,
    }
    body = {"horizon": horizon, "force_zero_shot": False}
    r = requests.post(
        f"{API_BASE}/forecasts/generate",
        json=body,
        headers=headers,
        timeout=150,   # backend ML timeout is 120 s; add buffer
    )
    r.raise_for_status()
    return r.json()


def summarise(result: dict, industry: str, horizon: int):
    rows = result.get("rows", [])
    source = result.get("source", "?")
    ctx    = result.get("context_source", "?")
    n_pred = result.get("n_predictions", len(rows))

    # Group by sku
    skus: dict[str, list] = {}
    for r in rows:
        skus.setdefault(r["sku_id"], []).append(r)

    print(f"\n{'─'*60}")
    print(f"  {industry.upper()}  |  horizon={horizon}w  |  source={source}  |  ctx={ctx}")
    print(f"  {n_pred} forecast rows, {len(skus)} SKUs")
    print(f"{'─'*60}")
    for sku_id, sku_rows in sorted(skus.items()):
        p10s = [r["p10"] for r in sku_rows]
        p50s = [r["p50"] for r in sku_rows]
        p90s = [r["p90"] for r in sku_rows]
        print(f"  {sku_id}")
        print(f"    Week 1 → P10={p10s[0]:,.0f}  P50={p50s[0]:,.0f}  P90={p90s[0]:,.0f}")
        if len(sku_rows) > 1:
            mid = len(sku_rows) // 2
            print(f"    Week {mid+1} → P10={p10s[mid]:,.0f}  P50={p50s[mid]:,.0f}  P90={p90s[mid]:,.0f}")
        last = len(sku_rows) - 1
        print(f"    Week {last+1} → P10={p10s[last]:,.0f}  P50={p50s[last]:,.0f}  P90={p90s[last]:,.0f}")


def main():
    print("Fetching tenant info…")
    tenant_id, user_id, email, role = get_tenant_info()
    print(f"  tenant={tenant_id}")
    print(f"  user  ={user_id} ({email}, {role})")

    results = {}
    for industry in INDUSTRIES:
        horizon = DEFAULT_HORIZON[industry]
        token   = mint_token(tenant_id, user_id, email, role, industry)
        print(f"\nCalling forecast for [{industry}] horizon={horizon}w …  (may take 30–90s)")
        t0 = time.time()
        try:
            result = generate_forecast(token, industry, horizon)
            elapsed = time.time() - t0
            print(f"  ✓ done in {elapsed:.1f}s — {result.get('n_predictions')} rows, source={result.get('source')}")
            results[industry] = result
            summarise(result, industry, horizon)
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  ✗ FAILED after {elapsed:.1f}s: {exc}")
            results[industry] = None

    # Save full results for inspection
    out_path = "forecast_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n\nFull results saved to {out_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
