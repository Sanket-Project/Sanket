from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from sanket_ml.config import MLSettings, get_ml_settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TimeSeriesPanel:
    """A long-format panel of historical sales."""
    data: pd.DataFrame   # cols: unique_id, ds, y, [+ exogenous]
    tenant_id: uuid.UUID
    industry: str
    freq: str
    start: pd.Timestamp
    end: pd.Timestamp

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
        if isinstance(tenant_id, str):
            tenant_id = uuid.UUID(tenant_id)

        if end is None:
            end = date.today()
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

        params: dict = {
            "tenant_id": str(tenant_id),
            "industry": industry,
            "start": start,
            "end": end,
            "bucket": bucket,
        }
        sku_filter = ""
        channel_filter = ""
        if sku_ids:
            params["sku_ids"] = [str(s) for s in sku_ids]
            sku_filter = "AND sku_id = ANY(:sku_ids ::uuid[])"
        if channels:
            params["channels"] = channels
            channel_filter = "AND channel = ANY(:channels)"

        # Set RLS tenant before query
        with self._engine.begin() as conn:
            conn.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})
            # B608 false positive: sku_filter/channel_filter are static literal SQL
            # fragments chosen by server-side branches; every user-supplied value
            # (tenant_id, industry, dates, sku_ids, channels) is passed via bound
            # parameters, never string-interpolated. nosec is on the closing quote.
            query = text(
                f"""
                SELECT
                    sku_id::text AS unique_id,
                    date_trunc(:bucket, sale_time)::timestamp AS ds,
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
                GROUP BY sku_id, date_trunc(:bucket, sale_time)
                ORDER BY unique_id, ds
                """  # nosec B608 - see note above; all values are bound parameters
            )
            df = pd.read_sql(query, conn, params=params)

        if df.empty:
            log.warning("sales.load.empty", tenant=str(tenant_id))
            return TimeSeriesPanel(
                data=df.assign(unique_id=[], ds=[], y=[]) if df.empty else df,
                tenant_id=tenant_id,
                industry=industry,
                freq=freq,
                start=pd.Timestamp(start),
                end=pd.Timestamp(end),
            )

        df["ds"] = pd.to_datetime(df["ds"])

        # Filter out series with insufficient history
        counts = df.groupby("unique_id").size()
        keep = counts[counts >= min_observations].index
        df = df[df["unique_id"].isin(keep)].copy()

        # Reindex each series to a complete date range so that gaps become NaN
        df = _reindex_panel(df, freq)

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


def _reindex_panel(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for uid, g in df.groupby("unique_id", sort=False):
        eff_freq = _anchored_freq(freq, g["ds"].min())
        full_index = pd.date_range(g["ds"].min(), g["ds"].max(), freq=eff_freq)
        g2 = (
            g.set_index("ds")
             .reindex(full_index)
             .rename_axis("ds")
             .reset_index()
        )
        g2["unique_id"] = uid
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
