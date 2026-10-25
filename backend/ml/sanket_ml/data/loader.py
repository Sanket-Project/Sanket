from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from sanket_ml.config import MLSettings, get_ml_settings
from sanket_ml.data.calendar import period_start

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TimeSeriesPanel:
    """A long-format panel of historical sales."""
    data: pd.DataFrame   # cols: unique_id, ds, y, observed, [+ exogenous]
    tenant_id: uuid.UUID
    industry: str
    freq: str
    start: pd.Timestamp
    end: pd.Timestamp
    #: Buckets with at least one sales row, per SKU, before any filtering —
    #: what eligibility is judged on (gap-filled weeks are not observations).
    observation_counts: dict[str, int] = field(default_factory=dict)
    #: Every active SKU of the tenant/industry, sold or not, so callers can say
    #: which ones were not forecast instead of letting them vanish.
    active_sku_ids: tuple[str, ...] = ()
    #: The latest bucket with any sales for the tenant — the panel's end.
    last_week: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        required = {"unique_id", "ds", "y"}
        if not required.issubset(self.data.columns):
            missing = required - set(self.data.columns)
            raise ValueError(f"TimeSeriesPanel missing required columns: {missing}")

    @property
    def n_series(self) -> int:
        return self.data["unique_id"].nunique()

    @property
    def n_obs(self) -> int:
        return len(self.data)


def panel_bounds(*, start: date, end: date) -> tuple[datetime, datetime]:
    """``[start, end)`` as UTC instants, so a date never inherits the session zone."""
    return (
        datetime(start.year, start.month, start.day, tzinfo=UTC),
        datetime(end.year, end.month, end.day, tzinfo=UTC),
    )


def sales_panel_sql(*, by_sku: bool, by_channel: bool) -> str:
    """Bucketed sales for one tenant/industry over ``[:start, :end)``.

    Buckets are taken in UTC explicitly (see ``sanket_ml.data.calendar``).
    ``by_sku`` / ``by_channel`` add filters on ``:sku_ids`` / ``:channels``.
    """
    sku_filter = "AND sku_id = ANY(:sku_ids ::uuid[])" if by_sku else ""
    channel_filter = "AND channel = ANY(:channels)" if by_channel else ""
    # B608 false positive: the two filters are static literals chosen above;
    # every value is a bound parameter. nosec is on the closing quote.
    return f"""
        SELECT
            sku_id::text AS unique_id,
            date_trunc(:bucket, sale_time AT TIME ZONE 'UTC') AS ds,
            SUM(units_sold)::double precision AS y,
            SUM(COALESCE(net_revenue, 0))::double precision AS revenue,
            BOOL_OR(promo_flag)::int AS promo,
            AVG(COALESCE(markdown_pct, 0))::double precision AS markdown,
            -- Fraction of the bucket the SKU was in stock. NULL when no
            -- availability is recorded for any row in the bucket, so the
            -- censoring step can distinguish "in stock" from "unknown".
            AVG(in_stock::int)::double precision AS in_stock_frac
        FROM historical_sales
        WHERE tenant_id = :tenant_id
          AND industry = CAST(:industry AS industry_code)
          AND sale_time >= :start
          AND sale_time <  :end
          {sku_filter}
          {channel_filter}
        GROUP BY sku_id, date_trunc(:bucket, sale_time AT TIME ZONE 'UTC')
        ORDER BY unique_id, ds
        """  # nosec B608 - see note above; all values are bound parameters


class HistoricalSalesLoader:
    """Pulls historical_sales from PostgreSQL and aggregates into a panel
    indexed by (sku_id, period_start) at the requested frequency."""

    def __init__(self, settings: MLSettings | None = None) -> None:
        self._settings = settings or get_ml_settings()
        self._engine = create_engine(
            self._settings.database_url,
            pool_pre_ping=True,
            pool_size=10,
        )

    def load(
        self,
        tenant_id: uuid.UUID | str,
        industry: str,
        *,
        start: date | None = None,
        end: date | None = None,
        freq: str = "W",
        min_observations: int = 12,
        sku_ids: list[uuid.UUID] | None = None,
        channels: list[str] | None = None,
    ) -> TimeSeriesPanel:
        """Load complete periods of history up to (not including) ``end``.

        ``end`` defaults to the start of the current, still-incomplete period,
        so a half-finished week never enters the model looking like a slump.
        Pass a past Monday to reproduce exactly what was known at that cutoff.
        """
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)

        if end is None:
            end = period_start(freq)
        if start is None:
            start = end - timedelta(weeks=self._settings.default_history_weeks)

        log.info(
            "sales.load.start",
            tenant=str(tenant_id),
            industry=industry,
            freq=freq,
            start=str(start),
            end=str(end),
        )

        bucket = {"D": "day", "W": "week", "M": "month"}.get(freq)
        if bucket is None:
            raise ValueError(f"Unsupported freq: {freq}. Use 'D','W','M'.")

        start_ts, end_ts = panel_bounds(start=start, end=end)
        params: dict = {
            "tenant_id": str(tenant_id),
            "industry": industry,
            "start": start_ts,
            "end": end_ts,
            "bucket": bucket,
        }
        if sku_ids:
            params["sku_ids"] = [str(s) for s in sku_ids]
        if channels:
            params["channels"] = channels

        # Set RLS tenant before query
        with self._engine.begin() as conn:
            conn.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})
            query = text(sales_panel_sql(by_sku=bool(sku_ids), by_channel=bool(channels)))
            df = pd.read_sql(query, conn, params=params)
            active = tuple(
                str(r[0])
                for r in conn.execute(
                    text(
                        "SELECT id::text FROM skus WHERE tenant_id = :t "
                        "AND industry = CAST(:i AS industry_code) AND is_active"
                    ),
                    {"t": str(tenant_id), "i": industry},
                )
            )

        if df.empty:
            log.warning("sales.load.empty", tenant=str(tenant_id))
            return TimeSeriesPanel(
                data=df.assign(unique_id=[], ds=[], y=[]) if df.empty else df,
                tenant_id=tenant_id,
                industry=industry,
                freq=freq,
                start=pd.Timestamp(start),
                end=pd.Timestamp(end),
                active_sku_ids=active,
            )

        df["ds"] = pd.to_datetime(df["ds"])
        last_week = df["ds"].max()

        # Filter out series with insufficient history (counted in real buckets)
        counts = df.groupby("unique_id").size()
        keep = counts[counts >= min_observations].index
        df = df[df["unique_id"].isin(keep)].copy()

        # Every series runs to the panel's last bucket: the feed demonstrably
        # covers those weeks (other SKUs sold in them), so a SKU that stopped
        # selling carries explicit zeros instead of looking current.
        df = _reindex_panel(df, freq, end=last_week) if not df.empty else df

        log.info(
            "sales.load.done",
            n_series=df["unique_id"].nunique(),
            n_obs=len(df),
            dropped_short=int((counts < min_observations).sum()),
        )
        return TimeSeriesPanel(
            data=df,
            tenant_id=tenant_id,
            industry=industry,
            freq=freq,
            start=pd.Timestamp(start),
            end=pd.Timestamp(end),
            observation_counts={str(k): int(v) for k, v in counts.items()},
            active_sku_ids=active,
            last_week=last_week,
        )

    def load_skus_metadata(
        self, tenant_id: uuid.UUID | str, industry: str
    ) -> pd.DataFrame:
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        with self._engine.begin() as conn:
            conn.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})
            q = text(
                """
                SELECT
                    s.id::text          AS unique_id,
                    s.sku_code,
                    s.product_id::text  AS product_id,
                    s.unit_cost,
                    s.unit_price,
                    s.lead_time_days,
                    s.moq,
                    s.safety_stock,
                    s.reorder_point,
                    s.attributes,
                    p.category,
                    p.subcategory,
                    p.brand
                FROM skus s
                JOIN products p ON p.id = s.product_id
                WHERE s.tenant_id = :tenant_id
                  AND s.industry  = CAST(:industry AS industry_code)
                  AND s.is_active = TRUE
                """
            )
            return pd.read_sql(q, conn, params={"tenant_id": str(tenant_id), "industry": industry})


def _anchored_freq(freq: str, anchor_ts: pd.Timestamp) -> str:
    """Anchor a weekly frequency to the weekday of the data.

    Postgres `date_trunc('week', ...)` buckets to Monday, but pandas 'W'
    anchors to Sunday ('W-SUN'). Reindexing with the wrong anchor matches no
    dates and silently zeroes every real observation. For weekly data we
    therefore anchor to the actual weekday present in the panel.
    """
    if freq == "W":
        return f"W-{anchor_ts.strftime('%a').upper()}"  # e.g. W-MON
    return freq


def _reindex_panel(df: pd.DataFrame, freq: str, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Densify each series from its first bucket to ``end`` (default: its own last).

    Filled buckets get ``y = 0`` — no sales recorded — and ``observed = 0`` so
    they stay distinguishable from weeks that genuinely reported zero demand.
    """
    pieces: list[pd.DataFrame] = []
    for uid, g in df.groupby("unique_id", sort=False):
        eff_freq = _anchored_freq(freq, g["ds"].min())
        last = max(g["ds"].max(), end) if end is not None else g["ds"].max()
        full_index = pd.date_range(g["ds"].min(), last, freq=eff_freq)
        g2 = (
            g.assign(observed=1)
             .set_index("ds")
             .reindex(full_index)
             .rename_axis("ds")
             .reset_index()
        )
        g2["unique_id"] = uid
        g2["observed"] = g2["observed"].fillna(0).astype(int)
        g2["y"] = g2["y"].fillna(0.0)  # absence of sales = 0 units
        for c in ("revenue", "markdown"):
            if c in g2:
                g2[c] = g2[c].fillna(0.0)
        if "promo" in g2:
            g2["promo"] = g2["promo"].fillna(0).astype(int)
        pieces.append(g2)
    return pd.concat(pieces, ignore_index=True)


class ExternalSignalLoader:
    def __init__(self, settings: MLSettings | None = None) -> None:
        self._settings = settings or get_ml_settings()
        self._engine = create_engine(self._settings.database_url, pool_pre_ping=True)

    def load(
        self,
        tenant_id: uuid.UUID | str,
        industry: str,
        *,
        start: date,
        end: date,
        validated_only: bool = True,
    ) -> pd.DataFrame:
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)
        status_clause = "AND status = 'validated'" if validated_only else ""
        with self._engine.begin() as conn:
            conn.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})
            # B608 false positive: status_clause is a static literal toggled by a
            # bool flag; tenant_id/industry/dates are all passed as bound parameters.
            # nosec is on the closing quote (the line bandit attributes the issue to).
            q = text(
                f"""
                SELECT
                    signal_type::text AS signal_type,
                    effective_at      AS ds,
                    region,
                    category_tags,
                    sku_tags,
                    processed_value,
                    sentiment_score,
                    impact_weight
                FROM external_signals
                WHERE tenant_id = :tenant_id
                  AND industry  = CAST(:industry AS industry_code)
                  AND effective_at >= :start
                  AND effective_at <  :end
                  {status_clause}
                ORDER BY effective_at
                """  # nosec B608 - see note above; all values are bound parameters
            )
            df = pd.read_sql(q, conn, params={
                "tenant_id": str(tenant_id),
                "industry": industry,
                "start": start,
                "end": end,
            })
        if not df.empty:
            df["ds"] = pd.to_datetime(df["ds"])
        return df
