"""Bulk SKU import: one request per 500 rows, products matched by code, per-row results.

The in-app importer used to send one request per SKU. A 2,352-row catalogue blew
through the 300/min per-user rate limit, and its "Product ID" codes (PRD-1001)
were sent as internal ids, which crashed the endpoint with a 500.
"""

from __future__ import annotations

from sqlalchemy import text


async def _product(client, headers, code: str) -> str:
    r = await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": f"Synthetic saree {code}", "category": "Sarees", "external_id": code},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _bulk(client, headers, rows):
    return await client.post("/api/v1/skus/bulk", headers=headers, json={"rows": rows})


async def _skus(client, headers) -> dict[str, dict]:
    r = await client.get("/api/v1/skus?limit=200&active_only=false", headers=headers)
    assert r.status_code == 200, r.text
    return {s["sku_code"]: s for s in r.json()}


async def test_rows_link_to_products_by_code_or_id(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    by_code = await _product(client, headers, "PRD-1001")
    by_id = await _product(client, headers, "PRD-1002")

    r = await _bulk(
        client,
        headers,
        [
            {"product": "PRD-1001", "sku_code": "SWF-1001-NVY", "unit_price": "11849"},
            {"product": by_id, "sku_code": "SWF-1002-TEL"},
        ],
    )

    assert r.status_code == 200, r.text
    assert r.json() == {"created": 2, "skipped": 0, "failed": 0, "errors": []}
    skus = await _skus(client, headers)
    assert skus["SWF-1001-NVY"]["product_id"] == by_code
    assert float(skus["SWF-1001-NVY"]["unit_price"]) == 11849
    assert skus["SWF-1002-TEL"]["product_id"] == by_id


async def test_only_the_rows_that_cannot_be_created_fail(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    await _product(client, headers, "PRD-1001")

    r = await _bulk(
        client,
        headers,
        [
            {"product": "PRD-1001", "sku_code": "OK-1", "gtin": "8907412100019"},
            {"product": "PRD-1185", "sku_code": "NO-PRODUCT"},
            {"product": "PRD-1001", "sku_code": "BAD-SIZE", "attributes": {"size": "9XL"}},
            {"product": "PRD-1001", "sku_code": "BAD-PRICE", "unit_price": -5},
            {"product": "PRD-1001", "sku_code": "DUP-BARCODE", "gtin": "8907412100019"},
            {"sku_code": "NO-REFERENCE"},
        ],
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["created"], body["skipped"], body["failed"]) == (1, 0, 5)
    reasons = {e["index"]: (e["sku_code"], e["reason"]) for e in body["errors"]}
    assert reasons[1][0] == "NO-PRODUCT"
    assert "PRD-1185" in reasons[1][1]
    assert "size" in reasons[2][1]
    assert "unit_price" in reasons[3][1]
    assert "8907412100019" in reasons[4][1]
    assert "product" in reasons[5][1].lower()
    assert set(await _skus(client, headers)) == {"OK-1"}


async def test_codes_that_already_exist_are_skipped(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    await _product(client, headers, "PRD-1001")
    first = await _bulk(client, headers, [{"product": "PRD-1001", "sku_code": "SWF-A"}])
    assert first.json()["created"] == 1

    r = await _bulk(
        client,
        headers,
        [
            {"product": "PRD-1001", "sku_code": "SWF-A"},
            {"product": "PRD-1001", "sku_code": "SWF-B"},
            {"product": "PRD-1001", "sku_code": "SWF-B"},
        ],
    )

    assert r.json() == {"created": 1, "skipped": 2, "failed": 0, "errors": []}


async def test_the_workspace_sku_cap_still_applies(client, db_session, signed_in_workspace):
    tenant_id, headers = await signed_in_workspace()
    await _product(client, headers, "PRD-1001")
    await db_session.execute(
        text("UPDATE tenants SET max_skus = 2 WHERE id = :t"), {"t": str(tenant_id)}
    )
    await db_session.commit()

    r = await _bulk(
        client,
        headers,
        [{"product": "PRD-1001", "sku_code": f"CAP-{i}"} for i in range(3)],
    )

    body = r.json()
    assert (body["created"], body["failed"]) == (2, 1)
    assert "limit" in body["errors"][0]["reason"].lower()


async def test_inactive_rows_are_created_inactive(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    await _product(client, headers, "PRD-1001")

    await _bulk(
        client,
        headers,
        [{"product": "PRD-1001", "sku_code": "SWF-OLD", "is_active": False}],
    )

    assert (await _skus(client, headers))["SWF-OLD"]["is_active"] is False


async def test_a_batch_is_capped_at_500_rows(client, signed_in_workspace):
    _, headers = await signed_in_workspace()

    r = await _bulk(
        client, headers, [{"product": "PRD-1", "sku_code": f"X-{i}"} for i in range(501)]
    )

    assert r.status_code == 422


async def test_a_product_code_in_the_single_create_path_is_not_found(client, signed_in_workspace):
    _, headers = await signed_in_workspace()

    r = await client.post(
        "/api/v1/skus/PRD-1001/skus", headers=headers, json={"sku_code": "SWF-1001-NVY"}
    )

    assert r.status_code == 404, r.text
