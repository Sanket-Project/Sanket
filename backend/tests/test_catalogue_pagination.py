"""Bulk-created rows share timestamps; pagination must not lose identifiers."""
import uuid

from sqlalchemy import text


async def test_sku_pages_cover_bulk_created_catalogue(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    pid = uuid.uuid4()
    await db_session.execute(text("INSERT INTO products (id,tenant_id,industry,name,category,status) "
        "VALUES (:p,:t,'fashion','Bulk','Test','active')"), {"p": pid, "t": tenant})
    await db_session.execute(text("INSERT INTO skus (id,tenant_id,product_id,industry,sku_code,created_at) "
        "SELECT gen_random_uuid(),:t,:p,'fashion','BULK-' || n,now() "
        "FROM generate_series(1,1199) n"), {"p": pid, "t": tenant})
    await db_session.commit()
    ids = []
    for offset in range(0, 1200, 200):
        response = await client.get(f"/api/v1/skus?limit=200&offset={offset}&active_only=false", headers=headers)
        assert response.status_code == 200, response.text
        ids.extend(row["id"] for row in response.json())
    assert len(ids) == 1199
    assert len(set(ids)) == 1199, "SKU pages skipped catalogue entries with identical creation times"


async def test_product_pages_cover_bulk_created_catalogue(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    await db_session.execute(text("INSERT INTO products (id,tenant_id,industry,name,category,status,created_at) "
        "SELECT gen_random_uuid(),:t,'fashion','Product-' || n,'Test','active',now() "
        "FROM generate_series(1,1199) n"), {"t": tenant})
    await db_session.commit()
    ids = []
    for offset in range(0, 1200, 200):
        response = await client.get(f"/api/v1/products?limit=200&offset={offset}", headers=headers)
        assert response.status_code == 200, response.text
        ids.extend(row["id"] for row in response.json())
    assert len(ids) == len(set(ids)) == 1199
