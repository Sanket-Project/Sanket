from pathlib import Path

from sqlalchemy import text

SAMPLES = Path(__file__).resolve().parents[2] / "docs" / "audit" / "2026-10-28-retail-v2" / "samples"


async def test_v2_preview_and_confirm_are_authenticated_and_atomic(client, signed_in_workspace, db_session):
    tenant_id, headers = await signed_in_workspace("fashion")
    product_id = await db_session.scalar(
        text("""
            INSERT INTO products (id, tenant_id, industry, external_id, name, category, status, attributes)
            VALUES (gen_random_uuid(), :tenant, 'fashion', 'DEMO-KUR-001', 'Demo Kurti', 'apparel', 'active', '{}'::jsonb)
            RETURNING id
        """),
        {"tenant": tenant_id},
    )
    await db_session.execute(
        text("""
            INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, currency, attributes)
            VALUES (gen_random_uuid(), :tenant, :product, 'fashion', 'DEMO-KUR-001-BLU-M', 'INR', '{}'::jsonb)
        """),
        {"tenant": tenant_id, "product": product_id},
    )
    await db_session.execute(
        text("""
            INSERT INTO locations (id, tenant_id, code, name, kind, is_active, attributes)
            VALUES (gen_random_uuid(), :tenant, 'demo-hyd-store', 'Demo Hyderabad Store', 'store', TRUE, '{}'::jsonb)
        """),
        {"tenant": tenant_id},
    )
    await db_session.commit()
    content = (SAMPLES / "sales_v2_SAMPLE_ONLY.csv").read_bytes()
    preview = await client.post(
        "/api/v1/integrations/v2/preview",
        headers=headers,
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    result = preview.json()
    assert result["schema"] == "retail_v2.0.sales"
    assert result["errors"] == []

    confirmed = await client.post(
        "/api/v1/integrations/v2/confirm",
        headers=headers,
        data={"preview_token": result["preview_token"]},
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["inserted"] == 1


async def test_v2_marked_file_cannot_fall_through_legacy_upload(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    content = (SAMPLES / "sales_v2_SAMPLE_ONLY.csv").read_bytes()
    response = await client.post(
        "/api/v1/integrations/upload",
        headers=headers,
        data={"kind": "sales"},
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert response.status_code == 400
    assert "V2 files use" in response.json()["detail"]
