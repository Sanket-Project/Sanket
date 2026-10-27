import json

from test_smart_import import STOCK

PLAN = "/api/v1/integrations/import/plan"


async def test_plan_preview_and_confirm_round_trip(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    files = [("files", ("stock.csv", STOCK, "text/csv")), ("files", ("notes.csv", b"just,one\n", "text/csv"))]
    planned = await client.post(PLAN, headers=headers, files=files)
    assert planned.status_code == 200, planned.text
    slots = planned.json()["files"]
    assert len(slots) == 2
    stock = slots[0]
    assert stock["decision"]["destinations"] == ["products", "inventory"]

    form = {"plan_token": stock["plan_token"], "decision": json.dumps(stock["decision"])}
    upload = {"file": ("stock.csv", STOCK, "text/csv")}
    preview = await client.post(f"{PLAN}/preview", headers=headers, data=form, files=upload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["preview"]["output_rows"] == 2

    confirmed = await client.post(f"{PLAN}/confirm", headers=headers, data=form, files=upload)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["destinations"]["inventory"]["inventory_rows"] == 2


async def test_plan_rejects_too_many_files(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    files = [("files", (f"f{i}.csv", STOCK, "text/csv")) for i in range(11)]
    response = await client.post(PLAN, headers=headers, files=files)
    assert response.status_code == 400
    assert "10" in response.json()["detail"]


async def test_confirm_rejects_tampered_token_and_bad_decision(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    planned = (await client.post(PLAN, headers=headers, files=[("files", ("stock.csv", STOCK, "text/csv"))])).json()
    stock = planned["files"][0]
    upload = {"file": ("stock.csv", STOCK, "text/csv")}
    bad_token = await client.post(f"{PLAN}/confirm", headers=headers, files=upload,
                                  data={"plan_token": stock["plan_token"][:-4] + "AAAA",
                                        "decision": json.dumps(stock["decision"])})
    assert bad_token.status_code == 400
    bad_json = await client.post(f"{PLAN}/confirm", headers=headers, files=upload,
                                 data={"plan_token": stock["plan_token"], "decision": "{not json"})
    assert bad_json.status_code == 400


async def test_plan_requires_authentication(client):
    response = await client.post(PLAN, files=[("files", ("stock.csv", STOCK, "text/csv"))])
    assert response.status_code == 401
