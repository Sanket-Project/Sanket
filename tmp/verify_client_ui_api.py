"""Read-only business-data verification; credentials come from existing local docs."""
import json
import re
import time
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
readme = (root / "data/demo-swecha/README.md").read_text(encoding="utf-8")
credentials = {"tenant_slug": re.search(r"Workspace: `([^`]+)`", readme)[1],
               "email": re.search(r"email: `([^`]+)`", readme)[1],
               "password": re.search(r"password: `([^`]+)`", readme)[1]}
results = {}
with httpx.Client(base_url="http://127.0.0.1:8010/api/v1", timeout=20) as client:
    login = client.post("/auth/dev-login", json=credentials)
    login.raise_for_status()
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    for name, path in {
        "inventory": "/inventory/overview?limit=25",
        "company": "/trends/company",
        "district": "/trends/company?state=Telangana&district=Hyderabad",
        "catalogue": "/trends/company/catalogue?kind=sku&limit=30",
    }.items():
        began = time.perf_counter()
        response = client.get(path)
        response.raise_for_status()
        results[name] = {"status": response.status_code,
                         "duration_ms": round((time.perf_counter() - began) * 1000, 1),
                         "body": response.json()}
assert results["inventory"]["body"]["total_skus"] == 0
assert results["inventory"]["body"]["total_positions"] == 0
assert results["company"]["body"]["catalogue"]["sku_count"] == 0
assert results["company"]["body"]["external"]["items"] == []
assert results["district"]["body"]["external"]["items"] == []
assert results["catalogue"]["body"]["total"] == 0
target = root / "docs/audit/2026-10-27-client-ui-discovery/api-verification.json"
target.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps({name: {"status": row["status"], "duration_ms": row["duration_ms"]}
                  for name, row in results.items()}, indent=2))
print("Existing login works; business catalogue and stock remain empty.")
