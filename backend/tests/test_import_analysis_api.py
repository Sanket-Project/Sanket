import pytest


async def test_authenticated_analysis_and_confirmed_import_use_same_payload(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    file = ("data.csv", b"Title\nSKU,Qty,Date\nAI-API-1,3,2026-01-01\n", "text/csv")
    analyzed = await client.post("/api/v1/integrations/upload/analyze", headers=headers,
                                 data={"kind": "sales"}, files={"file": file})
    assert analyzed.status_code == 200, analyzed.text
    result = analyzed.json()
    assert result["tables"][0]["header_start"] == 2
    table = result["tables"][0]
    import json
    response = await client.post("/api/v1/integrations/upload", headers=headers, files={"file": file},
        data={"kind": "sales", "analysis_token": result["analysis_token"], "remember_mapping": "true",
              "table_selections": json.dumps([{"id": table["id"], "mapping": table["mapping"]}])})
    assert response.status_code == 200, response.text
    assert response.json()["sales_rows"] == 1


async def test_analyze_requires_authentication(client):
    response = await client.post("/api/v1/integrations/upload/analyze", data={"kind": "sales"},
                                 files={"file": ("a.csv", b"SKU,Qty,Date\nA,2,2026-01-01\n")})
    assert response.status_code == 401
