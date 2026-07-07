"""Load real product / SKU / historical-sales data from a CSV or Excel file.

This is the bridge from "demo mode" (synthetic fallback in the backend) to a
real run: it populates `products`, `skus`, and `historical_sales` for a tenant
so that the ML training pipeline and the /forecast endpoints work on YOUR data.

Usage (inside the ml-api container):

    docker compose cp mydata.csv ml-api:/tmp/mydata.csv
    docker compose exec ml-api python -m scripts.load_sales_csv \
        --csv /tmp/mydata.csv \
        --tenant-slug sanket-dev \
        --industry fashion \
        --sku-col sku --date-col date --units-col units_sold \
        --product-col product_name --category-col category

Only --csv is strictly required if your columns already use the default names
(sku_code, sale_time/date, units_sold). Everything else is optional.

The script is idempotent at the product/SKU level (upsert by sku_code) and
appends sales rows. Re-running with the same file will create duplicate sales
rows, so load each file once.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from sanket_ml.config import get_ml_settings

log = structlog.get_logger(__name__)

VALID_INDUSTRIES = {"fashion", "electronics", "pharma", "agrocenter"}


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def _first_present(df: pd.DataFrame, *candidates: str) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand and cand.lower() in lower:
            return lower[cand.lower()]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Load real sales data into SANKET")
    ap.add_argument("--csv", required=True, help="Path to CSV or Excel file")
    ap.add_argument("--tenant-slug", default="sanket-dev")
    ap.add_argument("--industry", default="fashion", choices=sorted(VALID_INDUSTRIES))
    # Column mapping (case-insensitive; sensible fallbacks tried automatically)
    ap.add_argument("--sku-col", default=None, help="SKU code column")
    ap.add_argument("--date-col", default=None, help="Sale date/timestamp column")
    ap.add_argument("--units-col", default=None, help="Units sold column")
    ap.add_argument("--product-col", default=None, help="Product name column")
    ap.add_argument("--category-col", default=None, help="Category column")
    ap.add_argument("--channel-col", default=None, help="Channel column")
    ap.add_argument("--region-col", default=None, help="Region column")
    ap.add_argument("--revenue-col", default=None, help="Net revenue column")
    ap.add_argument("--price-col", default=None, help="Unit price column")
    ap.add_argument("--cost-col", default=None, help="Unit cost column")
    ap.add_argument("--dry-run", action="store_true", help="Parse + validate only")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.exists():
        log.error("load.file_missing", path=str(path))
        return 2

    df = _read_table(path)
    log.info("load.read", rows=len(df), cols=list(df.columns))

    sku_col = args.sku_col or _first_present(df, "sku_code", "sku", "sku_id", "item", "item_id")
    date_col = args.date_col or _first_present(df, "sale_time", "date", "ds", "timestamp", "week", "period")
    units_col = args.units_col or _first_present(df, "units_sold", "units", "qty", "quantity", "sales", "demand", "y")

    missing = [n for n, c in [("sku", sku_col), ("date", date_col), ("units", units_col)] if c is None]
    if missing:
        log.error("load.missing_required_columns", missing=missing, available=list(df.columns))
        print(
            f"\nERROR: could not find columns for: {', '.join(missing)}.\n"
            f"Available columns: {list(df.columns)}\n"
            f"Pass them explicitly, e.g. --sku-col <name> --date-col <name> --units-col <name>\n"
        )
        return 2

    product_col = args.product_col or _first_present(df, "product_name", "product", "name", "title")
    category_col = args.category_col or _first_present(df, "category", "cat", "department")
    channel_col = args.channel_col or _first_present(df, "channel", "sales_channel")
    region_col = args.region_col or _first_present(df, "region", "country", "market")
    revenue_col = args.revenue_col or _first_present(df, "net_revenue", "revenue", "sales_value", "amount")
    price_col = args.price_col or _first_present(df, "unit_price", "price")
    cost_col = args.cost_col or _first_present(df, "unit_cost", "cost")

    # Normalise into a working frame
    work = pd.DataFrame()
    work["sku_code"] = df[sku_col].astype(str).str.strip()
    work["sale_time"] = pd.to_datetime(df[date_col], errors="coerce")
    work["units_sold"] = pd.to_numeric(df[units_col], errors="coerce")
    work["product_name"] = df[product_col].astype(str).str.strip() if product_col else work["sku_code"]
    work["category"] = df[category_col].astype(str).str.strip() if category_col else "uncategorized"
    work["channel"] = df[channel_col].astype(str).str.strip() if channel_col else "unknown"
    work["region"] = df[region_col].astype(str).str.strip() if region_col else None
    work["net_revenue"] = pd.to_numeric(df[revenue_col], errors="coerce") if revenue_col else None
    work["unit_price"] = pd.to_numeric(df[price_col], errors="coerce") if price_col else None
    work["unit_cost"] = pd.to_numeric(df[cost_col], errors="coerce") if cost_col else None

    before = len(work)
    work = work.dropna(subset=["sku_code", "sale_time", "units_sold"])
    work = work[work["units_sold"] >= 0]
    dropped = before - len(work)
    if dropped:
        log.warning("load.dropped_invalid_rows", dropped=dropped)

    if work.empty:
        log.error("load.no_valid_rows")
        return 2

    n_skus = work["sku_code"].nunique()
    span = (work["sale_time"].min(), work["sale_time"].max())
    log.info("load.parsed", valid_rows=len(work), skus=n_skus, span=[str(span[0]), str(span[1])])

    # Per-SKU observation counts after weekly bucketing (the loader drops <12)
    weekly = work.assign(wk=work["sale_time"].dt.to_period("W")).groupby("sku_code")["wk"].nunique()
    thin = weekly[weekly < 12]
    if len(thin):
        log.warning(
            "load.thin_series",
            count=int(len(thin)),
            note="SKUs with <12 weekly buckets will be skipped by the trainer",
        )

    if args.dry_run:
        print("\nDRY RUN — no rows written.")
        print(f"  industry      : {args.industry}")
        print(f"  tenant slug   : {args.tenant_slug}")
        print(f"  valid rows    : {len(work)}")
        print(f"  distinct SKUs : {n_skus}")
        print(f"  date span     : {span[0]}  ->  {span[1]}")
        print(f"  trainable SKUs: {int((weekly >= 12).sum())} of {n_skus} (>=12 weekly buckets)")
        return 0

    settings = get_ml_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    industry = args.industry

    with engine.begin() as conn:
        tenant_id = conn.execute(
            text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": args.tenant_slug}
        ).scalar()
        if tenant_id is None:
            log.error("load.tenant_not_found", slug=args.tenant_slug)
            print(f"\nERROR: tenant '{args.tenant_slug}' not found. Seed it first (004_seed.sql).")
            return 2
        tenant_id = str(tenant_id)
        conn.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": tenant_id})

        # ---- products: one per (product_name, category) ----
        prod_keys = work[["product_name", "category"]].drop_duplicates()
        product_ids: dict[tuple[str, str], str] = {}
        for _, r in prod_keys.iterrows():
            pid = conn.execute(
                text(
                    """
                    INSERT INTO products (tenant_id, industry, name, category, external_id)
                    VALUES (:tid, CAST(:ind AS industry_code), :name, :cat, :ext)
                    ON CONFLICT (tenant_id, external_id) WHERE external_id IS NOT NULL
                    DO UPDATE SET updated_at = now()
                    RETURNING id
                    """
                ),
                {
                    "tid": tenant_id,
                    "ind": industry,
                    "name": r["product_name"],
                    "cat": r["category"],
                    "ext": f"{r['category']}::{r['product_name']}",
                },
            ).scalar()
            product_ids[(r["product_name"], r["category"])] = str(pid)

        # ---- skus: one per sku_code ----
        sku_meta = work.sort_values("sale_time").groupby("sku_code").agg(
            product_name=("product_name", "last"),
            category=("category", "last"),
            unit_price=("unit_price", "last"),
            unit_cost=("unit_cost", "last"),
        ).reset_index()
        sku_ids: dict[str, str] = {}
        for _, r in sku_meta.iterrows():
            pid = product_ids[(r["product_name"], r["category"])]
            up = None if pd.isna(r["unit_price"]) else float(r["unit_price"])
            uc = None if pd.isna(r["unit_cost"]) else float(r["unit_cost"])
            sid = conn.execute(
                text(
                    """
                    INSERT INTO skus (tenant_id, product_id, industry, sku_code, unit_price, unit_cost)
                    VALUES (:tid, :pid, CAST(:ind AS industry_code), :code, :price, :cost)
                    ON CONFLICT (tenant_id, sku_code)
                    DO UPDATE SET unit_price = COALESCE(EXCLUDED.unit_price, skus.unit_price),
                                  unit_cost  = COALESCE(EXCLUDED.unit_cost, skus.unit_cost),
                                  updated_at = now()
                    RETURNING id
                    """
                ),
                {"tid": tenant_id, "pid": pid, "ind": industry,
                 "code": r["sku_code"], "price": up, "cost": uc},
            ).scalar()
            sku_ids[r["sku_code"]] = str(sid)

        # ---- historical_sales: bulk insert ----
        rows = []
        for _, r in work.iterrows():
            rows.append({
                "tid": tenant_id,
                "sid": sku_ids[r["sku_code"]],
                "ind": industry,
                "st": r["sale_time"].to_pydatetime(),
                "ch": r["channel"] or "unknown",
                "rg": r["region"] if (r["region"] and r["region"] != "nan") else None,
                "u": int(r["units_sold"]),
                "rev": None if pd.isna(r["net_revenue"]) else float(r["net_revenue"]),
            })
        conn.execute(
            text(
                """
                INSERT INTO historical_sales
                    (tenant_id, sku_id, industry, sale_time, channel, region, units_sold, net_revenue)
                VALUES
                    (:tid, :sid, CAST(:ind AS industry_code), :st, :ch, :rg, :u, :rev)
                """
            ),
            rows,
        )

    log.info(
        "load.done",
        tenant=tenant_id,
        industry=industry,
        products=len(product_ids),
        skus=len(sku_ids),
        sales_rows=len(work),
    )
    print(
        f"\nLoaded into tenant '{args.tenant_slug}' ({industry}):\n"
        f"  products    : {len(product_ids)}\n"
        f"  SKUs        : {len(sku_ids)}\n"
        f"  sales rows  : {len(work)}\n\n"
        f"Next: docker compose exec ml-api python -m scripts.train_all {tenant_id}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
