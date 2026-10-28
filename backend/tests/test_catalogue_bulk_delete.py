from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_products_bulk_delete_and_delete_all(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")

    # Create 3 products
    p1 = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Shirt A", "category": "Shirts", "external_id": "P-A"},
    )).json()["id"]

    p2 = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Shirt B", "category": "Shirts", "external_id": "P-B"},
    )).json()["id"]

    p3 = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Shirt C", "category": "Shirts", "external_id": "P-C"},
    )).json()["id"]

    # Bulk delete p1 and p2
    res = await client.post(
        "/api/v1/products/bulk-delete",
        headers=headers,
        json={"product_ids": [p1, p2]},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["deleted"] == 2

    # Check remaining products
    list_res = await client.get("/api/v1/products", headers=headers)
    remaining_ids = [p["id"] for p in list_res.json()]
    assert p1 not in remaining_ids
    assert p2 not in remaining_ids
    assert p3 in remaining_ids

    # Delete all products in fashion
    del_all_res = await client.delete("/api/v1/products/all", headers=headers)
    assert del_all_res.status_code == 200, del_all_res.text
    assert del_all_res.json()["deleted"] == 1

    # Check that fashion products are empty
    list_after = await client.get("/api/v1/products", headers=headers)
    assert len(list_after.json()) == 0


async def test_skus_bulk_delete_and_delete_all(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")

    p = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Pants A", "category": "Pants", "external_id": "P-PANTS"},
    )).json()["id"]

    # Create 3 SKUs
    s1 = (await client.post(
        f"/api/v1/skus/{p}/skus",
        headers=headers,
        json={"sku_code": "PANTS-S", "unit_price": 50},
    )).json()["id"]

    s2 = (await client.post(
        f"/api/v1/skus/{p}/skus",
        headers=headers,
        json={"sku_code": "PANTS-M", "unit_price": 50},
    )).json()["id"]

    s3 = (await client.post(
        f"/api/v1/skus/{p}/skus",
        headers=headers,
        json={"sku_code": "PANTS-L", "unit_price": 50},
    )).json()["id"]

    # Bulk delete s1 and s2
    res = await client.post(
        "/api/v1/skus/bulk-delete",
        headers=headers,
        json={"sku_ids": [s1, s2]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] == 2

    remaining = [s["id"] for s in (await client.get("/api/v1/skus", headers=headers)).json()]
    assert s1 not in remaining
    assert s2 not in remaining
    assert s3 in remaining

    # Delete all SKUs
    del_all = await client.delete("/api/v1/skus/all", headers=headers)
    assert del_all.status_code == 200, del_all.text
    assert del_all.json()["deleted"] == 1

    remaining_all = (await client.get("/api/v1/skus", headers=headers)).json()
    assert len(remaining_all) == 0


async def test_inventory_levels_bulk_delete_and_delete_all(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")

    p = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Hat A", "category": "Hats", "external_id": "P-HAT"},
    )).json()["id"]

    s1 = (await client.post(
        f"/api/v1/skus/{p}/skus",
        headers=headers,
        json={"sku_code": "HAT-RED", "unit_price": 20},
    )).json()["id"]

    s2 = (await client.post(
        f"/api/v1/skus/{p}/skus",
        headers=headers,
        json={"sku_code": "HAT-BLU", "unit_price": 20},
    )).json()["id"]

    # Upsert inventory levels
    upsert_res = await client.put(
        "/api/v1/inventory/levels",
        headers=headers,
        json={
            "items": [
                {"sku_id": s1, "on_hand_units": 100, "location": "wh-1"},
                {"sku_id": s2, "on_hand_units": 50, "location": "wh-1"},
            ]
        },
    )
    assert upsert_res.status_code == 200

    # Bulk delete level for s1
    bulk_del = await client.post(
        "/api/v1/inventory/levels/bulk-delete",
        headers=headers,
        json={"sku_ids": [s1]},
    )
    assert bulk_del.status_code == 200, bulk_del.text
    assert bulk_del.json()["deleted"] >= 1

    levels = (await client.get("/api/v1/inventory/levels", headers=headers)).json()["levels"]
    assert any(lvl["sku_id"] == s2 for lvl in levels)
    assert not any(lvl["sku_id"] == s1 for lvl in levels)

    # Delete all inventory levels
    del_all = await client.delete("/api/v1/inventory/levels/all", headers=headers)
    assert del_all.status_code == 200, del_all.text
    assert del_all.json()["deleted"] >= 1

    levels_after = (await client.get("/api/v1/inventory/levels", headers=headers)).json()["levels"]
    assert len(levels_after) == 0


async def test_delete_product_with_skus_cascades(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")

    # Create product
    p = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Jacket with SKU", "category": "Jackets", "external_id": "P-JACKET-SKU"},
    )).json()["id"]

    # Create SKU under product
    s = (await client.post(
        f"/api/v1/skus/{p}/skus",
        headers=headers,
        json={"sku_code": "JACKET-SKU-1", "unit_price": 120},
    )).json()["id"]

    # Delete product - must succeed and cascade delete SKUs without 500 error
    del_res = await client.delete(f"/api/v1/products/{p}", headers=headers)
    assert del_res.status_code == 200, del_res.text
    assert del_res.json()["deleted"] is True
    assert del_res.json()["cascaded_skus"] == 1

    # SKU should also be gone
    skus_res = await client.get("/api/v1/skus", headers=headers)
    assert not any(sku["id"] == s for sku in skus_res.json())


async def test_delete_all_products_with_skus_cascades(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")

    # Create 2 products with SKUs
    p1 = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Shirt X", "category": "Shirts", "external_id": "P-X"},
    )).json()["id"]
    await client.post(f"/api/v1/skus/{p1}/skus", headers=headers, json={"sku_code": "SKU-X1", "unit_price": 50})
    await client.post(f"/api/v1/skus/{p1}/skus", headers=headers, json={"sku_code": "SKU-X2", "unit_price": 60})

    p2 = (await client.post(
        "/api/v1/products",
        headers=headers,
        json={"name": "Shirt Y", "category": "Shirts", "external_id": "P-Y"},
    )).json()["id"]
    await client.post(f"/api/v1/skus/{p2}/skus", headers=headers, json={"sku_code": "SKU-Y1", "unit_price": 70})

    # Delete all products in fashion
    del_all_res = await client.delete("/api/v1/products/all", headers=headers)
    assert del_all_res.status_code == 200, del_all_res.text
    assert del_all_res.json()["deleted"] >= 2
    assert del_all_res.json()["cascaded_skus"] >= 3

    # Check products and SKUs are empty
    assert len((await client.get("/api/v1/products", headers=headers)).json()) == 0
    assert len((await client.get("/api/v1/skus", headers=headers)).json()) == 0


