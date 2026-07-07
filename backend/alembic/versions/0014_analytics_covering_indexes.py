"""Index audit: covering index for the sales-analytics aggregate hot path.

Audit findings on ``historical_sales`` (see docs/PERFORMANCE.md):

* The analytics endpoints (``/analytics/sales/summary``, ``/timeseries``,
  ``/top-products``) all filter on ``(tenant_id, industry, sale_time)`` and then
  ``SUM(units_sold, gross_revenue, net_revenue, returns)``. The existing
  ``idx_hsales_industry (tenant_id, industry, sale_time DESC)`` satisfies the
  *filter* but not the *aggregation*: every matching row still requires a heap
  fetch to read the summed columns. On a wide partition that heap traffic
  dominates the query.

* Fix: a covering index that keeps the same leading key columns and ``INCLUDE``s
  the summed measures, so the aggregation is served by an **index-only scan**
  (no heap access) once the partition is vacuumed.

* ``idx_hsales_industry`` then becomes redundant — the new index shares its exact
  key prefix (btree can scan backwards, so the ``DESC`` ordering is still served)
  and additionally covers the payload. We drop it to reclaim write amplification
  and storage.

NOTE on rollout: ``CREATE INDEX`` on a partitioned parent cascades to every
partition and takes ``SHARE`` locks. On an already-large production table build
the per-partition indexes ``CONCURRENTLY`` first, then ``ATTACH`` them and create
the parent index ``ONLY`` — see the runbook. This migration uses the plain form,
which is correct for fresh installs and modest tables.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hsales_agg_covering
        ON historical_sales (tenant_id, industry, sale_time)
        INCLUDE (units_sold, gross_revenue, net_revenue, returns)
        """
    )
    # Superseded by the covering index above (same key prefix + payload).
    op.execute("DROP INDEX IF EXISTS idx_hsales_industry")


def downgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hsales_industry
        ON historical_sales (tenant_id, industry, sale_time DESC)
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_hsales_agg_covering")
