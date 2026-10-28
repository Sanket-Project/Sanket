"""
Direct Postgres ingestion for Sanket demo sales data.
Reads sanket_sales_history.csv and bulk-inserts into historical_sales,
creating missing products/SKUs for pharma, agrocenter, hardware.

Run from: C:\\Users\\admin\\Desktop\\Sanket\\
Requires: pip install psycopg2-binary
"""

import csv
import uuid
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras
import os

DB_DSN = "host=localhost port=5432 dbname=sanket user=postgres password=postgres"

# ── Industry/SKU metadata from Forecasts.tsx ──────────────────────────────────
SKU_META = {
    # Fashion
    "FSH-WOM-001": dict(industry="fashion",    name="Women's Premium Jacket",     category="Apparel",      unit_price=189),
    "FSH-MEN-004": dict(industry="fashion",    name="Men's Casual Trousers",      category="Apparel",      unit_price=89),
    "FSH-SHO-011": dict(industry="fashion",    name="Classic Leather Sneakers",   category="Footwear",     unit_price=129),
    "FSH-ACC-006": dict(industry="fashion",    name="Woven Silk Scarf",           category="Accessories",  unit_price=69),
    # Electronics
    "ELC-PHN-001": dict(industry="electronics", name="Flagship Smartphone X1",   category="Mobile",       unit_price=899),
    "ELC-LAP-003": dict(industry="electronics", name="ProBook 15 Laptop",        category="Computing",    unit_price=1299),
    "ELC-AUD-008": dict(industry="electronics", name="NoiseCancel Pro Headphones",category="Audio",       unit_price=249),
    "ELC-SHM-002": dict(industry="electronics", name="4K SmartHome Hub",         category="Smart Home",   unit_price=149),
    # Pharma
    "PHA-ONC-001": dict(industry="pharma",     name="Onco-Therapy 50mg",          category="Oncology",    unit_price=850),
    "PHA-ALL-007": dict(industry="pharma",     name="AllerRelief Tablets 10mg",   category="Allergy",     unit_price=24),
    "PHA-INS-002": dict(industry="pharma",     name="InsulinPen Pro 100U",        category="Diabetes",    unit_price=180),
    "PHA-ANT-009": dict(industry="pharma",     name="BroadSpec Antibiotic 500mg", category="Antibiotics", unit_price=45),
    # Agrocenter
    "AGR-FERT-001": dict(industry="agrocenter", name="NPK Premium Fertilizer 50kg", category="Fertilizers", unit_price=42),
    "AGR-SEED-012": dict(industry="agrocenter", name="Hybrid Corn Seed Pack",       category="Seeds",       unit_price=89),
    "AGR-PEST-007": dict(industry="agrocenter", name="BioShield Pesticide 1L",      category="Pesticides",  unit_price=35),
    "AGR-IRRI-003": dict(industry="agrocenter", name="Drip Irrigation Kit",         category="Irrigation",  unit_price=285),
    # Hardware
    "HW-DRILL-02":  dict(industry="hardware",   name="ProDrill 18V Cordless",      category="Power Tools", unit_price=179),
    "HW-FAST-01":   dict(industry="hardware",   name="Structural Bolt Assortment", category="Fasteners",   unit_price=28),
    "HW-WIRE-01":   dict(industry="hardware",   name="12AWG Electrical Wire 100m", category="Electrical",  unit_price=95),
    "HW-CEMENT-01": dict(industry="hardware",   name="OPC Cement 50kg Bag",        category="Construction",unit_price=32),
}

PRODUCT_NAMES = {
    "fashion":     "Fashion Seasonal Demo Catalog",
    "electronics": "Electronics Core Demo Catalog",
    "pharma":      "Pharma Essential Demo Catalog",
    "agrocenter":  "Agrocenter Demo Catalog",
    "hardware":    "Hardware Demo Catalog",
}

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path   = os.path.join(script_dir, "..", "data", "sanket_sales_history.csv")

    print("Connecting to Postgres…")
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # ── 1. Get tenant_id ──────────────────────────────────────────────────────
    cur.execute("SELECT id FROM tenants LIMIT 1")
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No tenant found – run seeds first.")
    tenant_id = row[0]
    print(f"  tenant_id = {tenant_id}")

    # ── 2. Upsert one product per industry ───────────────────────────────────
    industry_product = {}
    for industry, pname in PRODUCT_NAMES.items():
        ext_id = f"demo-{industry}"
        cur.execute("""
            INSERT INTO products (tenant_id, industry, external_id, name, category, status)
            VALUES (%s, %s, %s, %s, %s, 'active')
            ON CONFLICT (tenant_id, external_id) WHERE external_id IS NOT NULL
            DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """, (tenant_id, industry, ext_id, pname, industry.capitalize()))
        product_id = cur.fetchone()[0]
        industry_product[industry] = product_id
        print(f"  product [{industry}] = {product_id}")
    conn.commit()

    # ── 3. Upsert all SKUs ───────────────────────────────────────────────────
    sku_id_map = {}  # sku_code -> uuid
    for sku_code, meta in SKU_META.items():
        product_id = industry_product[meta["industry"]]
        cur.execute("""
            INSERT INTO skus (tenant_id, product_id, industry, sku_code, description,
                              unit_price, currency, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, 'USD', true)
            ON CONFLICT (tenant_id, sku_code) DO UPDATE SET unit_price = EXCLUDED.unit_price
            RETURNING id
        """, (tenant_id, product_id, meta["industry"], sku_code,
              meta["name"], meta["unit_price"]))
        sku_id = cur.fetchone()[0]
        sku_id_map[sku_code] = sku_id
    conn.commit()
    print(f"  {len(sku_id_map)} SKUs upserted")

    # ── 4. Delete existing historical_sales for this tenant (clean slate) ────
    cur.execute("DELETE FROM historical_sales WHERE tenant_id = %s", (tenant_id,))
    deleted = cur.rowcount
    print(f"  Deleted {deleted} existing sales rows")
    conn.commit()

    # ── 5. Read CSV and bulk-insert historical_sales ──────────────────────────
    rows_to_insert = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku_code = row["SKU"]
            if sku_code not in sku_id_map:
                continue
            sku_id   = sku_id_map[sku_code]
            meta     = SKU_META[sku_code]
            industry = meta["industry"]
            qty      = int(row["Quantity"])
            price    = float(row["Selling Price"])
            channel  = row.get("Channel", "online") or "online"
            region   = row.get("Region")  or None
            date_str = row["Date"]
            # Parse date → timestamp at noon UTC
            sale_dt  = datetime.fromisoformat(date_str).replace(
                hour=12, minute=0, second=0, tzinfo=timezone.utc
            )
            gross_rev = round(qty * price, 4)
            rows_to_insert.append((
                str(uuid.uuid4()),  # id
                str(tenant_id),     # tenant_id
                str(sku_id),        # sku_id
                industry,           # industry
                sale_dt,            # sale_time
                channel,            # channel
                region,             # region
                qty,                # units_sold
                gross_rev,          # gross_revenue
                gross_rev,          # net_revenue
                0,                  # returns
                False,              # promo_flag
                0,                  # markdown_pct
                True,               # in_stock
            ))

    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO historical_sales
            (id, tenant_id, sku_id, industry, sale_time, channel, region,
             units_sold, gross_revenue, net_revenue, returns, promo_flag,
             markdown_pct, in_stock)
        VALUES %s
        """,
        rows_to_insert,
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        page_size=500,
    )
    conn.commit()
    print(f"  ✓ Inserted {len(rows_to_insert)} historical_sales rows")

    # ── 6. Verify ─────────────────────────────────────────────────────────────
    cur.execute("""
        SELECT industry, COUNT(*), MIN(sale_time)::date, MAX(sale_time)::date
        FROM historical_sales
        WHERE tenant_id = %s
        GROUP BY industry
        ORDER BY industry
    """, (tenant_id,))
    print("\n  Sales in DB:")
    for r in cur.fetchall():
        print(f"    {r[0]:12s}  {r[1]:4d} rows  {r[2]} → {r[3]}")

    cur.close()
    conn.close()
    print("\nDone! All historical sales loaded.")

if __name__ == "__main__":
    main()
