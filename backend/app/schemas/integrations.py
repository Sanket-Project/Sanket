from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import IndustryCode

# Deprecated on every request that carries it. A workspace has exactly one
# industry and the server knows it, so this field can no longer choose anything:
# omit it (the normal path), or send the workspace's own. Anything else is a
# 403 rather than a silent coercion -- a client that believes it can write into
# another industry is telling us its state is wrong.
_TARGET_INDUSTRY_FIELD = Field(
    default=None,
    description=(
        "Deprecated. The workspace's own industry is always used; supplying a "
        "different one is refused."
    ),
)


class ShopifyConnectRequest(BaseModel):
    shop_domain: str = Field(..., description="e.g. my-store or my-store.myshopify.com")
    access_token: str = Field(..., min_length=10, description="Admin API access token")
    target_industry: IndustryCode | None = _TARGET_INDUSTRY_FIELD
    # Optional: the custom app's API secret key. Needed only to verify inbound
    # webhooks (real-time sales). Stored encrypted; safe to omit for polling.
    api_secret: str | None = Field(default=None, min_length=8)
    sync_products: bool = True
    sync_inventory: bool = True
    sync_orders: bool = True


class SyncScope(BaseModel):
    sync_products: bool = True
    sync_inventory: bool = True
    sync_orders: bool = True


class IntegrationStatus(BaseModel):
    provider: str
    connected: bool
    status: str
    shop_domain: str | None = None
    target_industry: str | None = None
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_stats: dict = Field(default_factory=dict)
    error_message: str | None = None
    # Echoed shop name from the most recent validation/sync, if known.
    shop_name: str | None = None


class SyncAccepted(BaseModel):
    status: str
    detail: str


class LiveSaleRow(BaseModel):
    sale_time: datetime
    sku_code: str | None = None
    description: str | None = None
    units: int
    revenue: float | None = None
    order_id: str | None = None


class LiveSalesSummary(BaseModel):
    connected: bool
    today_units: int = 0
    today_revenue: float = 0.0
    today_orders: int = 0
    last_sale_at: datetime | None = None
    # 24 hourly unit buckets, oldest → newest.
    sparkline_hourly: list[int] = Field(default_factory=list)
    recent: list[LiveSaleRow] = Field(default_factory=list)


# ── Connector Hub (catalog of all providers) ─────────────────────────────────
class AuthFieldOut(BaseModel):
    key: str
    label: str
    type: str
    required: bool
    placeholder: str | None = None
    help: str | None = None
    options: list[str] | None = None
    secret: bool = False


class ConnectorOut(BaseModel):
    """A catalog provider plus this tenant's connection state for it."""

    key: str
    name: str
    category: str
    availability: str  # live | beta | planned
    summary: str
    feeds: list[str] = Field(default_factory=list)
    auth_fields: list[AuthFieldOut] = Field(default_factory=list)
    docs_url: str | None = None
    icon: str
    accent: str
    # ISO-3166 alpha-2 when the provider is market-specific (e.g. "IN").
    region: str | None = None
    # Per-tenant connection state (None when never connected).
    status: str = "disconnected"  # connected | syncing | error | requested | disconnected
    connected: bool = False
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    error_message: str | None = None
    # Push token, returned ONCE right after connecting a push provider
    # (rest_api / webhooks). Never persisted in plaintext or echoed again.
    push_token: str | None = None
    # Whether POST /integrations/{key}/sync is available for this provider
    # (direct-SQL connectors today; others sync automatically or push in).
    supports_sync: bool = False


class CategoryGroupOut(BaseModel):
    category: str
    label: str
    connectors: list[ConnectorOut]


class CatalogOut(BaseModel):
    groups: list[CategoryGroupOut]
    # Flat counts for the Hub header.
    total: int = 0
    live: int = 0
    connected: int = 0


class GenericConnectRequest(BaseModel):
    """Connect (or request) any catalog provider. ``credentials`` keys must match
    the provider's ``auth_fields``; secret values are encrypted at rest."""

    target_industry: IndustryCode | None = _TARGET_INDUSTRY_FIELD
    credentials: dict[str, str] = Field(default_factory=dict)


class UploadResult(BaseModel):
    provider: str
    kind: str  # sales | inventory | products
    rows_total: int
    rows_imported: int
    rows_skipped: int
    products_created: int = 0
    skus_created: int = 0
    inventory_rows: int = 0
    sales_rows: int = 0
    # Replay accounting for sales (F01). rows_imported = inserted + updated.
    rows_inserted: int = 0
    rows_unchanged: int = 0
    rows_updated: int = 0
    identity_mode: str | None = None  # "transaction" | "period" (sales only)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
