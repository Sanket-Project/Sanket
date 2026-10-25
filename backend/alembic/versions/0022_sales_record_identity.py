"""Sales record identity: make re-imports idempotent without deleting anything.

Re-uploading the same sales file used to insert every row again (audit F01,
2026-10-25: 459 → 918 rows, units doubled). Rows had no identity, so neither
the importer nor Data Quality could tell a replay from a genuine sale.

This migration adds:

* ``historical_sales.record_key`` — the tenant-scoped identity computed by
  ``app.services.sales_identity`` (order line, row fingerprint or period total,
  plus the in-file occurrence). Indexed per tenant for replay lookups.
* ``historical_sales.location`` — the store/warehouse a sale happened at, so
  stock cover can be computed per location only where sales say where they
  happened.

and backfills ``record_key`` for rows that came from file uploads, using SQL
that mirrors the Python canonical form exactly. **No row is deleted or
altered beyond the new column.** Copies created by earlier replays end up
sharing a key; Data Quality then reports them as confirmed duplicates and the
repair is the user's explicit, previewed choice.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirrors app.services.sales_identity.base_key + assign_record_keys for
# metadata.source = 'upload'. concat_ws skips NULL arguments, so every nullable
# field is COALESCEd to '' to keep its position in the canonical string.
BACKFILL_SQL = r"""
WITH keyed AS (
    SELECT
        id,
        sale_time,
        tenant_id,
        metadata->>'upload_id' AS upload_id,
        'upload|' || CASE
            WHEN NULLIF(metadata->>'order_id', '') IS NOT NULL THEN
                'o|' || (metadata->>'order_id') || '|'
                     || COALESCE(NULLIF(metadata->>'line_id', ''), sku_id::text)
            ELSE
                'f|' || md5(concat_ws('|',
                    sku_id::text,
                    to_char(sale_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
                    channel,
                    COALESCE(region, ''),
                    COALESCE(location, ''),
                    units_sold::text,
                    COALESCE(gross_revenue::text, ''),
                    COALESCE(net_revenue::text, '')))
        END AS base
    FROM historical_sales
    WHERE record_key IS NULL
      AND metadata->>'source' = 'upload'
),
numbered AS (
    SELECT
        id,
        sale_time,
        base || '#' || row_number() OVER (
            PARTITION BY tenant_id, upload_id, base ORDER BY id
        ) AS record_key
    FROM keyed
)
UPDATE historical_sales AS h
   SET record_key = n.record_key
  FROM numbered AS n
 WHERE h.id = n.id
   AND h.sale_time = n.sale_time
"""


def upgrade() -> None:
    op.execute(
        "ALTER TABLE historical_sales "
        "ADD COLUMN IF NOT EXISTS record_key TEXT, "
        "ADD COLUMN IF NOT EXISTS location TEXT"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hsales_tenant_record_key "
        "ON historical_sales (tenant_id, record_key) WHERE record_key IS NOT NULL"
    )
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_hsales_tenant_record_key")
    op.execute(
        "ALTER TABLE historical_sales DROP COLUMN IF EXISTS location, "
        "DROP COLUMN IF EXISTS record_key"
    )
