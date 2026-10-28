"""End-to-end integration and sample reconciliation with Retail V2 review samples.

Validates the 8 synthetic sample CSV files against the V2 contracts and executes
the complete lifecycle in a real PostgreSQL tenant context:
Products -> SKUs -> Inventory Snapshot -> Sales Group -> Linked Returns -> Valuation & Profitability.
"""

from __future__ import annotations

import pathlib
from decimal import Decimal
import pytest
from test_import_confirmation import seed

from app.services.integrations.v2 import contracts as v2_contracts
from app.services.integrations.v2 import catalog as v2_catalog
from app.services.integrations.v2 import inventory as v2_inv
from app.services.integrations.v2 import sales_returns as v2_sr
from app.services.integrations.v2 import valuation as v2_val
from app.services.integrations.v2.event_registry import EventRegistryService

SAMPLES_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "docs" / "audit" / "2026-10-28-retail-v2" / "samples"


def test_v2_sample_files_exist_and_detect_schemas():
    """Verify that all 8 sample CSV files exist, parse cleanly, and identify their schemas."""
    expected_samples = {
        "products_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_PRODUCTS,
        "skus_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_SKUS,
        "inventory_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_INVENTORY,
        "sales_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_SALES,
        "returns_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_RETURNS,
        "purchases_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_PURCHASES,
        "suppliers_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_SUPPLIERS,
        "locations_v2_SAMPLE_ONLY.csv": v2_contracts.SCHEMA_LOCATIONS,
    }

    for filename, expected_schema in expected_samples.items():
        file_path = SAMPLES_DIR / filename
        assert file_path.exists(), f"Sample file {filename} must exist"
        raw_bytes = file_path.read_bytes()
        headers, rows = v2_contracts.parse_v2_csv(raw_bytes)
        assert len(headers) > 0
        assert len(rows) > 0
        detected = v2_contracts.detect_v2_schema(headers, rows[0])
        assert detected == expected_schema, f"File {filename} schema detected as {detected}, expected {expected_schema}"


@pytest.mark.asyncio
async def test_end_to_end_v2_lifecycle_reconciliation(app_role_db):
    """Execute end-to-end lifecycle on the kurti review sample:
    1. Parse and validate products & SKUs
    2. Parse and validate inventory snapshot (20 on-hand, 2 reserved, 1 damaged)
    3. Post sale of 2 units for INR 1,800 ex-tax (INR 90 GST, collected INR 1,890)
    4. Post return of 1 unit for INR 900 ex-tax (INR 45 credited GST, refund INR 945)
    5. Deduplication: exact replay of sale group skips without writing new facts
    6. Reconcile profitability: Retained revenue INR 900, COGS INR 600, GP INR 300, Margin 33.3333%
    """
    ctx = await seed(app_role_db)
    tenant_id = ctx.tenant_id
    service = EventRegistryService()

    # 1. Products & SKUs
    p_headers, p_rows = v2_contracts.parse_v2_csv((SAMPLES_DIR / "products_v2_SAMPLE_ONLY.csv").read_bytes())
    products = [v2_catalog.validate_product_row(r) for r in p_rows]
    assert len(products) == 2
    assert products[0].product_code == "DEMO-KUR-001"
    assert products[1].product_code == "DEMO-DUP-001"

    s_headers, s_rows = v2_contracts.parse_v2_csv((SAMPLES_DIR / "skus_v2_SAMPLE_ONLY.csv").read_bytes())
    skus = [v2_catalog.validate_sku_row(r) for r in s_rows]
    assert len(skus) == 2
    v2_catalog.validate_sku_batch(skus)

    # 2. Inventory snapshot
    inv_headers, inv_rows = v2_contracts.parse_v2_csv((SAMPLES_DIR / "inventory_v2_SAMPLE_ONLY.csv").read_bytes())
    inventory_items = [v2_inv.validate_inventory_row(r) for r in inv_rows]
    kurti_inv = next(i for i in inventory_items if i.sku_code == "DEMO-KUR-001-BLU-M")
    assert kurti_inv.on_hand_qty == 20
    assert kurti_inv.reserved_qty == 2
    assert kurti_inv.damaged_qty == 1
    assert kurti_inv.available_to_sell == 17

    # 3. Post Sale
    sales_headers, sales_rows = v2_contracts.parse_v2_csv((SAMPLES_DIR / "sales_v2_SAMPLE_ONLY.csv").read_bytes())
    validated_sales = [v2_sr.validate_sale_row(r) for r in sales_rows]
    assert len(validated_sales) == 1
    sale = validated_sales[0]
    assert sale.gross_sales_ex_tax == Decimal("2000.00")
    assert sale.discount_ex_tax == Decimal("200.00")
    assert sale.net_sale_ex_tax == Decimal("1800.00")
    assert sale.tax_amount == Decimal("90.00")
    assert sale.customer_charge == Decimal("1890.00")

    async with app_role_db.session(str(tenant_id)) as session:
        sale_res = await service.post_sales_group(session, tenant_id, validated_sales)
        assert sale_res["inserted"] == 1
        assert sale_res["skipped"] == 0
        await session.commit()

    # 4. Post Return
    returns_headers, returns_rows = v2_contracts.parse_v2_csv((SAMPLES_DIR / "returns_v2_SAMPLE_ONLY.csv").read_bytes())
    validated_returns = [v2_sr.validate_return_row(r) for r in returns_rows]
    assert len(validated_returns) == 1
    ret = validated_returns[0]
    assert ret.returns == 1
    assert ret.return_value_ex_tax == Decimal("900.00")
    assert ret.tax_amount == Decimal("45.00")
    assert ret.refund_amount == Decimal("945.00")

    async with app_role_db.session(str(tenant_id)) as session:
        ret_res = await service.post_return_event(session, tenant_id, ret)
        assert ret_res["status"] == "approved"
        assert ret_res["remaining_sold_qty"] == 1
        await session.commit()

    # 5. Idempotent Replay Protection
    async with app_role_db.session(str(tenant_id)) as session:
        replay_res = await service.post_sales_group(session, tenant_id, validated_sales)
        assert replay_res["inserted"] == 0
        assert replay_res["skipped"] == 1
        await session.commit()

    # 6. Profitability calculation
    profit = v2_val.calculate_period_profitability(
        sales=[
            v2_val.SaleProfitabilityInput(
                gross_ex_tax=sale.gross_sales_ex_tax,
                discount_ex_tax=sale.discount_ex_tax,
                net_sale_ex_tax=sale.net_sale_ex_tax,
                quantity_sold=sale.quantity_sold,
                historical_unit_cost=Decimal("600.0000"),
            )
        ],
        returns=[
            v2_val.ReturnProfitabilityInput(
                return_value_ex_tax=ret.return_value_ex_tax,
                returned_qty=ret.returns,
                original_unit_cost=Decimal("600.0000"),
                disposition=ret.disposition,
            )
        ],
    )
    assert profit.net_revenue_ex_tax == Decimal("900.00")
    assert profit.net_cogs == Decimal("600.00")
    assert profit.gross_profit == Decimal("300.00")
    assert profit.gross_margin_pct == Decimal("33.3333")
    assert profit.markup_pct == Decimal("50.0000")
