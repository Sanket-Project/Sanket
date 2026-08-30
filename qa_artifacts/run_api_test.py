import json, time
import requests

BASE = "http://localhost:8000/api/v1"
FILE_PATH = r"C:\Users\admin\Downloads\Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx"
FNAME = FILE_PATH.split("\\")[-1]
CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

result = {}

r = requests.post(BASE + "/auth/sandbox-session", timeout=30)
result["auth_status"] = r.status_code
auth = r.json()
result["auth_mode"] = auth.get("mode")
token = auth.get("access_token")
headers = {"Authorization": f"Bearer {token}"}

with open(FILE_PATH, "rb") as f:
    r = requests.post(BASE + "/integrations/upload/analyze", data={"kind": "sales"},
                       files={"file": (FNAME, f, CT)}, timeout=60)
result["analyze_sales_status"] = r.status_code
result["analyze_sales"] = r.json()

with open(FILE_PATH, "rb") as f:
    r = requests.post(BASE + "/integrations/upload", headers=headers,
                       data={"kind": "sales", "target_industry": "fashion"},
                       files={"file": (FNAME, f, CT)}, timeout=60)
result["upload_sales_status"] = r.status_code
try:
    result["upload_sales"] = r.json()
except Exception:
    result["upload_sales"] = r.text

with open(FILE_PATH, "rb") as f:
    r = requests.post(BASE + "/integrations/upload", headers=headers,
                       data={"kind": "inventory", "target_industry": "fashion"},
                       files={"file": (FNAME, f, CT)}, timeout=60)
result["upload_inventory_status"] = r.status_code
try:
    result["upload_inventory"] = r.json()
except Exception:
    result["upload_inventory"] = r.text

with open(FILE_PATH, "rb") as f:
    r = requests.post(BASE + "/integrations/upload", headers=headers,
                       data={"kind": "products", "target_industry": "fashion"},
                       files={"file": (FNAME, f, CT)}, timeout=60)
result["upload_products_status"] = r.status_code
try:
    result["upload_products"] = r.json()
except Exception:
    result["upload_products"] = r.text

r = requests.post(BASE + "/forecasts/generate", headers=headers,
                   json={"horizon": 26, "force_zero_shot": False}, timeout=120)
result["forecast_generate_status"] = r.status_code
try:
    result["forecast_generate"] = r.json()
except Exception:
    result["forecast_generate"] = r.text

r = requests.post(BASE + "/forecast/hybrid/runs", headers=headers, json={}, timeout=60)
result["hybrid_create_status"] = r.status_code
try:
    hybrid_create = r.json()
except Exception:
    hybrid_create = {}
result["hybrid_create"] = hybrid_create

run_id = hybrid_create.get("run_id")
if run_id:
    for _ in range(36):
        rr = requests.get(f"{BASE}/forecast/hybrid/runs/{run_id}", headers=headers, timeout=30)
        try:
            data = rr.json()
        except Exception:
            data = {"raw": rr.text}
        if data.get("status") in ("completed", "failed", "error"):
            result["hybrid_poll_final"] = data
            break
        time.sleep(5)
    else:
        result["hybrid_poll_final"] = {"status": "timed_out_waiting"}

with open(r"C:\Users\admin\Desktop\Prisma\qa_artifacts\api_test_results.json", "w") as f:
    json.dump(result, f, indent=2, default=str)

print("DONE_OK")
