"""The connector catalog — every external data source SANKET exposes.

This is intentionally declarative data, not code: each :class:`ConnectorSpec`
describes one provider (its category, the credentials it needs, whether the sync
adapter is live yet, and presentation hints). The Integrations Hub API serves
this list and the frontend renders it, so the full breadth of integrations is
"available" the moment a provider is added here.

Availability tiers
------------------
* ``live``      — a working sync/ingest adapter exists; connecting actually
                  moves data into the canonical schema today.
* ``beta``      — functional but rough / limited; surfaced but flagged.
* ``planned``   — no sync adapter yet. Connecting stores the (encrypted)
                  credentials and records a connection request so the adapter
                  can be enabled later without any UI or data-model change.

Everything normalizes into the same canonical schema (products / skus /
inventory_levels / historical_sales) before it reaches forecasting — see
``app.services.integrations.file_import`` for the reference implementation.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ConnectorCategory(enum.StrEnum):
    sales = "sales"  # e-commerce + marketplaces
    pos = "pos"  # point of sale
    erp = "erp"  # ERP / inventory systems of record
    wms = "wms"  # warehouse management
    streaming = "streaming"  # event streams / webhooks
    warehouse = "warehouse"  # cloud data warehouses
    file = "file"  # file upload (CSV / Excel)
    database = "database"  # direct DB connections
    api = "api"  # generic REST / push


CATEGORY_LABELS: dict[ConnectorCategory, str] = {
    ConnectorCategory.sales: "Sales & E-commerce",
    ConnectorCategory.pos: "Point of Sale",
    ConnectorCategory.erp: "ERP & Inventory",
    ConnectorCategory.wms: "Warehouse Management",
    ConnectorCategory.streaming: "Streaming",
    ConnectorCategory.warehouse: "Data Warehouses",
    ConnectorCategory.file: "Files",
    ConnectorCategory.database: "Databases",
    ConnectorCategory.api: "Developer / API",
}

# Order categories are presented in the Hub (highest forecasting value first).
CATEGORY_ORDER: list[ConnectorCategory] = [
    ConnectorCategory.file,
    ConnectorCategory.sales,
    ConnectorCategory.pos,
    ConnectorCategory.erp,
    ConnectorCategory.wms,
    ConnectorCategory.streaming,
    ConnectorCategory.warehouse,
    ConnectorCategory.database,
    ConnectorCategory.api,
]


class ConnectorAvailability(enum.StrEnum):
    live = "live"
    beta = "beta"
    planned = "planned"


@dataclass(frozen=True)
class AuthField:
    """One credential/config input the provider's connect form should render."""

    key: str
    label: str
    type: str = "text"  # text | password | url | select | textarea
    required: bool = True
    placeholder: str | None = None
    help: str | None = None
    options: tuple[str, ...] | None = None  # for type == "select"
    # Whether this value is a secret (encrypted at rest, never returned).
    secret: bool = False


@dataclass(frozen=True)
class ConnectorSpec:
    key: str
    name: str
    category: ConnectorCategory
    availability: ConnectorAvailability
    summary: str
    # What canonical feeds this source provides, e.g. "sales", "inventory".
    feeds: tuple[str, ...] = ()
    auth_fields: tuple[AuthField, ...] = ()
    docs_url: str | None = None
    # Presentation hints consumed by the frontend.
    icon: str = "plug"  # lucide icon key (frontend maps string → component)
    accent: str = "from-slate-500 to-slate-600"  # tailwind gradient pair


# ── Reusable auth-field bundles ──────────────────────────────────────────────
_API_KEY = AuthField(
    key="api_key",
    label="API key",
    type="password",
    placeholder="••••••••••••",
    secret=True,
    help="Found in your provider's developer / API settings.",
)
_BASE_URL = AuthField(
    key="base_url",
    label="Instance / base URL",
    type="url",
    placeholder="https://your-instance.example.com",
)

# Direct-database connectors (postgres, mysql): one optional read-only SELECT
# per canonical feed. At least one is required; validated in the hub router
# since that's a cross-field rule the declarative AuthField can't express.
_SALES_QUERY = AuthField(
    key="sales_query",
    label="Sales query",
    type="textarea",
    required=False,
    placeholder="SELECT sku, quantity, sale_date AS timestamp, ... FROM orders",
    help="A read-only SELECT. Columns are matched the same way CSV headers are "
    "(e.g. sku/quantity/timestamp, with common aliases).",
)
_INVENTORY_QUERY = AuthField(
    key="inventory_query",
    label="Inventory query",
    type="textarea",
    required=False,
    placeholder="SELECT sku, available_stock, warehouse FROM stock_levels",
)
_PRODUCTS_QUERY = AuthField(
    key="products_query",
    label="Products query",
    type="textarea",
    required=False,
    placeholder="SELECT sku, name, brand, category FROM products",
)


def _request_only(reason: str) -> tuple[AuthField, ...]:
    """Auth bundle for `planned` providers: capture enough to scope the
    connection request and reach the customer's integration owner."""
    return (
        AuthField(
            key="account_ref",
            label="Account / instance identifier",
            placeholder="e.g. tenant id, instance URL, or account name",
            required=False,
        ),
        AuthField(
            key="contact_email",
            label="Integration contact email",
            type="text",
            required=False,
            placeholder="ops@yourcompany.com",
            help=reason,
        ),
    )


# ── The catalog ──────────────────────────────────────────────────────────────
CATALOG: list[ConnectorSpec] = [
    # ── Files (live, universal) ──────────────────────────────────────────────
    ConnectorSpec(
        key="csv_upload",
        name="CSV Upload",
        category=ConnectorCategory.file,
        availability=ConnectorAvailability.live,
        summary="Upload sales, inventory, or product files as CSV. The fastest "
        "way to get any dataset into SANKET.",
        feeds=("sales", "inventory", "products"),
        icon="file-text",
        accent="from-violet-500 to-purple-600",
    ),
    ConnectorSpec(
        key="excel_upload",
        name="Excel Upload",
        category=ConnectorCategory.file,
        availability=ConnectorAvailability.live,
        summary="Upload .xlsx workbooks of sales, inventory, or products. "
        "Columns are auto-mapped to the canonical schema.",
        feeds=("sales", "inventory", "products"),
        icon="file-spreadsheet",
        accent="from-emerald-500 to-green-600",
    ),
    # ── Developer / API (live) ───────────────────────────────────────────────
    ConnectorSpec(
        key="rest_api",
        name="REST API / Push",
        category=ConnectorCategory.api,
        availability=ConnectorAvailability.beta,
        summary="Push canonical sale events to SANKET from any system via a "
        "token-authenticated HTTPS endpoint. Ideal for custom backends.",
        feeds=("sales",),
        icon="webhook",
        accent="from-sky-500 to-blue-600",
    ),
    ConnectorSpec(
        key="webhooks",
        name="Generic Webhooks",
        category=ConnectorCategory.streaming,
        availability=ConnectorAvailability.beta,
        summary="Receive real-time sale events from any webhook source via a "
        "token-authenticated push endpoint.",
        feeds=("sales",),
        icon="webhook",
        accent="from-cyan-500 to-teal-600",
    ),
    # ── Sales & e-commerce ───────────────────────────────────────────────────
    ConnectorSpec(
        key="shopify",
        name="Shopify",
        category=ConnectorCategory.sales,
        availability=ConnectorAvailability.live,
        summary="Sync products, variants, inventory and order history. "
        "Real-time sales via webhooks.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(
                key="shop_domain", label="Store domain", placeholder="my-store.myshopify.com"
            ),
            AuthField(
                key="access_token",
                label="Admin API access token",
                type="password",
                placeholder="shpat_••••",
                secret=True,
            ),
        ),
        docs_url="https://help.shopify.com/en/manual/apps/app-types/custom-apps",
        icon="shopping-bag",
        accent="from-emerald-500 to-green-600",
    ),
    ConnectorSpec(
        key="woocommerce",
        name="WooCommerce",
        category=ConnectorCategory.sales,
        availability=ConnectorAvailability.live,
        summary="WordPress / WooCommerce store orders, products and stock.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            _BASE_URL,
            AuthField(key="consumer_key", label="Consumer key", secret=True, type="password"),
            AuthField(key="consumer_secret", label="Consumer secret", secret=True, type="password"),
        ),
        icon="shopping-cart",
        accent="from-purple-500 to-indigo-600",
    ),
    ConnectorSpec(
        key="magento",
        name="Magento",
        category=ConnectorCategory.sales,
        availability=ConnectorAvailability.planned,
        summary="Adobe Commerce / Magento order and catalog sync.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(_BASE_URL, _API_KEY),
        icon="shopping-cart",
        accent="from-orange-500 to-red-600",
    ),
    ConnectorSpec(
        key="bigcommerce",
        name="BigCommerce",
        category=ConnectorCategory.sales,
        availability=ConnectorAvailability.planned,
        summary="BigCommerce storefront orders, products and inventory.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(key="store_hash", label="Store hash"),
            AuthField(key="access_token", label="Access token", secret=True, type="password"),
        ),
        icon="shopping-cart",
        accent="from-slate-600 to-slate-800",
    ),
    ConnectorSpec(
        key="amazon",
        name="Amazon Seller",
        category=ConnectorCategory.sales,
        availability=ConnectorAvailability.planned,
        summary="Amazon Selling Partner API — orders, FBA inventory and settlement data.",
        feeds=("sales", "inventory"),
        auth_fields=(
            AuthField(key="seller_id", label="Seller ID"),
            AuthField(key="refresh_token", label="LWA refresh token", secret=True, type="password"),
        ),
        icon="package",
        accent="from-amber-500 to-orange-600",
    ),
    ConnectorSpec(
        key="flipkart",
        name="Flipkart Seller",
        category=ConnectorCategory.sales,
        availability=ConnectorAvailability.planned,
        summary="Flipkart Seller Hub orders and listings.",
        feeds=("sales", "inventory"),
        auth_fields=(
            AuthField(key="application_id", label="Application ID"),
            AuthField(
                key="application_secret", label="Application secret", secret=True, type="password"
            ),
        ),
        icon="package",
        accent="from-yellow-500 to-amber-600",
    ),
    # ── Point of sale ────────────────────────────────────────────────────────
    ConnectorSpec(
        key="square",
        name="Square",
        category=ConnectorCategory.pos,
        availability=ConnectorAvailability.planned,
        summary="Square POS transactions, catalog and inventory counts.",
        feeds=("sales", "inventory"),
        auth_fields=(
            AuthField(key="access_token", label="Access token", secret=True, type="password"),
        ),
        icon="credit-card",
        accent="from-slate-700 to-black",
    ),
    ConnectorSpec(
        key="lightspeed",
        name="Lightspeed",
        category=ConnectorCategory.pos,
        availability=ConnectorAvailability.planned,
        summary="Lightspeed Retail sales and inventory.",
        feeds=("sales", "inventory"),
        auth_fields=(_API_KEY,),
        icon="credit-card",
        accent="from-red-500 to-rose-600",
    ),
    ConnectorSpec(
        key="toast",
        name="Toast",
        category=ConnectorCategory.pos,
        availability=ConnectorAvailability.planned,
        summary="Toast restaurant POS orders and menu items.",
        feeds=("sales",),
        auth_fields=_request_only("We'll reach out to provision Toast partner API access."),
        icon="credit-card",
        accent="from-orange-500 to-amber-600",
    ),
    ConnectorSpec(
        key="clover",
        name="Clover",
        category=ConnectorCategory.pos,
        availability=ConnectorAvailability.planned,
        summary="Clover POS payments, orders and inventory.",
        feeds=("sales", "inventory"),
        auth_fields=(AuthField(key="merchant_id", label="Merchant ID"), _API_KEY),
        icon="credit-card",
        accent="from-green-600 to-emerald-700",
    ),
    # ── ERP & inventory ──────────────────────────────────────────────────────
    ConnectorSpec(
        key="sap",
        name="SAP S/4HANA",
        category=ConnectorCategory.erp,
        availability=ConnectorAvailability.planned,
        summary="SAP S/4HANA / Business One — sales orders, stock, purchase "
        "orders and material master.",
        feeds=("sales", "inventory", "purchase_orders"),
        auth_fields=(
            _BASE_URL,
            AuthField(key="client_id", label="Client ID"),
            AuthField(key="client_secret", label="Client secret", secret=True, type="password"),
        ),
        icon="building-2",
        accent="from-blue-600 to-indigo-700",
    ),
    ConnectorSpec(
        key="oracle_erp",
        name="Oracle ERP",
        category=ConnectorCategory.erp,
        availability=ConnectorAvailability.planned,
        summary="Oracle ERP Cloud — order management, inventory and procurement.",
        feeds=("sales", "inventory", "purchase_orders"),
        auth_fields=(
            _BASE_URL,
            AuthField(key="username", label="Username"),
            AuthField(key="password", label="Password", secret=True, type="password"),
        ),
        icon="building-2",
        accent="from-red-600 to-rose-700",
    ),
    ConnectorSpec(
        key="dynamics365",
        name="Microsoft Dynamics 365",
        category=ConnectorCategory.erp,
        availability=ConnectorAvailability.planned,
        summary="Dynamics 365 Finance & Supply Chain — sales, stock and POs.",
        feeds=("sales", "inventory", "purchase_orders"),
        auth_fields=(
            _BASE_URL,
            AuthField(key="tenant_id", label="Azure tenant ID"),
            AuthField(key="client_secret", label="Client secret", secret=True, type="password"),
        ),
        icon="building-2",
        accent="from-sky-600 to-blue-700",
    ),
    ConnectorSpec(
        key="netsuite",
        name="Oracle NetSuite",
        category=ConnectorCategory.erp,
        availability=ConnectorAvailability.planned,
        summary="NetSuite ERP — transactions, item records and inventory.",
        feeds=("sales", "inventory", "purchase_orders"),
        auth_fields=(
            AuthField(key="account_id", label="Account ID"),
            AuthField(key="token_secret", label="Token secret", secret=True, type="password"),
        ),
        icon="building-2",
        accent="from-blue-500 to-cyan-600",
    ),
    ConnectorSpec(
        key="odoo",
        name="Odoo",
        category=ConnectorCategory.erp,
        availability=ConnectorAvailability.planned,
        summary="Odoo ERP sales, inventory and purchase modules.",
        feeds=("sales", "inventory", "purchase_orders"),
        auth_fields=(
            _BASE_URL,
            AuthField(key="database", label="Database name"),
            AuthField(key="api_key", label="API key", secret=True, type="password"),
        ),
        icon="building-2",
        accent="from-violet-600 to-purple-700",
    ),
    # ── Warehouse management ─────────────────────────────────────────────────
    ConnectorSpec(
        key="manhattan",
        name="Manhattan Associates",
        category=ConnectorCategory.wms,
        availability=ConnectorAvailability.planned,
        summary="Manhattan WMS — bins, pick times, lead times and stock by location.",
        feeds=("inventory", "warehouse"),
        auth_fields=_request_only("We'll coordinate Manhattan Active integration access."),
        icon="warehouse",
        accent="from-amber-600 to-orange-700",
    ),
    ConnectorSpec(
        key="blue_yonder",
        name="Blue Yonder",
        category=ConnectorCategory.wms,
        availability=ConnectorAvailability.planned,
        summary="Blue Yonder (JDA) warehouse and fulfillment data.",
        feeds=("inventory", "warehouse"),
        auth_fields=_request_only("We'll coordinate Blue Yonder integration access."),
        icon="warehouse",
        accent="from-blue-600 to-sky-700",
    ),
    ConnectorSpec(
        key="infor",
        name="Infor WMS",
        category=ConnectorCategory.wms,
        availability=ConnectorAvailability.planned,
        summary="Infor CloudSuite WMS stock, locations and movements.",
        feeds=("inventory", "warehouse"),
        auth_fields=_request_only("We'll coordinate Infor ION integration access."),
        icon="warehouse",
        accent="from-rose-600 to-red-700",
    ),
    ConnectorSpec(
        key="fishbowl",
        name="Fishbowl",
        category=ConnectorCategory.wms,
        availability=ConnectorAvailability.planned,
        summary="Fishbowl inventory and warehouse management.",
        feeds=("inventory", "warehouse"),
        auth_fields=(
            _BASE_URL,
            AuthField(key="username", label="Username"),
            AuthField(key="password", label="Password", secret=True, type="password"),
        ),
        icon="warehouse",
        accent="from-teal-600 to-emerald-700",
    ),
    # ── Streaming ────────────────────────────────────────────────────────────
    ConnectorSpec(
        key="kafka",
        name="Apache Kafka",
        category=ConnectorCategory.streaming,
        availability=ConnectorAvailability.planned,
        summary="Consume sale/inventory events from Kafka topics.",
        feeds=("sales", "inventory"),
        auth_fields=(
            AuthField(
                key="bootstrap_servers",
                label="Bootstrap servers",
                placeholder="broker1:9092,broker2:9092",
            ),
            AuthField(key="topic", label="Topic"),
            AuthField(
                key="sasl_password",
                label="SASL password",
                secret=True,
                type="password",
                required=False,
            ),
        ),
        icon="radio",
        accent="from-slate-700 to-zinc-800",
    ),
    ConnectorSpec(
        key="rabbitmq",
        name="RabbitMQ",
        category=ConnectorCategory.streaming,
        availability=ConnectorAvailability.planned,
        summary="Consume events from RabbitMQ queues.",
        feeds=("sales", "inventory"),
        auth_fields=(
            AuthField(key="amqp_url", label="AMQP URL", type="url", secret=True),
            AuthField(key="queue", label="Queue"),
        ),
        icon="radio",
        accent="from-orange-600 to-amber-700",
    ),
    ConnectorSpec(
        key="kinesis",
        name="AWS Kinesis",
        category=ConnectorCategory.streaming,
        availability=ConnectorAvailability.planned,
        summary="Consume records from Amazon Kinesis data streams.",
        feeds=("sales", "inventory"),
        auth_fields=(
            AuthField(key="stream_name", label="Stream name"),
            AuthField(key="region", label="AWS region", placeholder="us-east-1"),
            AuthField(
                key="secret_access_key", label="Secret access key", secret=True, type="password"
            ),
        ),
        icon="radio",
        accent="from-yellow-600 to-orange-700",
    ),
    ConnectorSpec(
        key="pubsub",
        name="Google Pub/Sub",
        category=ConnectorCategory.streaming,
        availability=ConnectorAvailability.planned,
        summary="Consume messages from Google Cloud Pub/Sub topics.",
        feeds=("sales", "inventory"),
        auth_fields=(
            AuthField(key="project_id", label="GCP project ID"),
            AuthField(key="subscription", label="Subscription"),
            AuthField(
                key="service_account_json",
                label="Service account JSON",
                type="textarea",
                secret=True,
            ),
        ),
        icon="radio",
        accent="from-blue-500 to-red-500",
    ),
    # ── Data warehouses ──────────────────────────────────────────────────────
    ConnectorSpec(
        key="snowflake",
        name="Snowflake",
        category=ConnectorCategory.warehouse,
        availability=ConnectorAvailability.planned,
        summary="Query sales/inventory tables directly from your Snowflake warehouse.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(key="account", label="Account identifier", placeholder="xy12345.us-east-1"),
            AuthField(key="warehouse", label="Warehouse"),
            AuthField(key="password", label="Password / key", secret=True, type="password"),
        ),
        icon="database",
        accent="from-sky-500 to-cyan-600",
    ),
    ConnectorSpec(
        key="databricks",
        name="Databricks",
        category=ConnectorCategory.warehouse,
        availability=ConnectorAvailability.planned,
        summary="Read curated tables from your Databricks lakehouse.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(key="host", label="Workspace host", type="url"),
            AuthField(key="http_path", label="SQL warehouse HTTP path"),
            AuthField(key="token", label="Access token", secret=True, type="password"),
        ),
        icon="database",
        accent="from-red-500 to-orange-600",
    ),
    ConnectorSpec(
        key="bigquery",
        name="Google BigQuery",
        category=ConnectorCategory.warehouse,
        availability=ConnectorAvailability.planned,
        summary="Query sales/inventory datasets from BigQuery.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(key="project_id", label="GCP project ID"),
            AuthField(key="dataset", label="Dataset"),
            AuthField(
                key="service_account_json",
                label="Service account JSON",
                type="textarea",
                secret=True,
            ),
        ),
        icon="database",
        accent="from-blue-500 to-indigo-600",
    ),
    ConnectorSpec(
        key="redshift",
        name="Amazon Redshift",
        category=ConnectorCategory.warehouse,
        availability=ConnectorAvailability.planned,
        summary="Read from your Amazon Redshift cluster.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(key="host", label="Cluster endpoint", type="url"),
            AuthField(key="database", label="Database"),
            AuthField(key="password", label="Password", secret=True, type="password"),
        ),
        icon="database",
        accent="from-indigo-600 to-blue-700",
    ),
    ConnectorSpec(
        key="synapse",
        name="Azure Synapse",
        category=ConnectorCategory.warehouse,
        availability=ConnectorAvailability.planned,
        summary="Read from Azure Synapse Analytics.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(key="server", label="Server", type="url"),
            AuthField(key="database", label="Database"),
            AuthField(key="password", label="Password", secret=True, type="password"),
        ),
        icon="database",
        accent="from-cyan-600 to-sky-700",
    ),
    # ── Direct databases (live) ──────────────────────────────────────────────
    # Both connect to a customer-supplied read-only DSN and run up to three
    # customer-supplied SELECT queries (one per feed). Columns returned by each
    # query are matched against the same alias table the CSV/Excel importer
    # uses — see app.services.integrations.sql_source.
    ConnectorSpec(
        key="postgres",
        name="PostgreSQL",
        category=ConnectorCategory.database,
        availability=ConnectorAvailability.live,
        summary="Connect a read-only PostgreSQL source. Provide a SELECT per "
        "feed; columns are auto-mapped to the canonical schema.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(
                key="dsn",
                label="Connection string (DSN)",
                type="password",
                secret=True,
                placeholder="postgresql://user:pass@host:5432/db",
                help="A read-only role is strongly recommended.",
            ),
            _SALES_QUERY,
            _INVENTORY_QUERY,
            _PRODUCTS_QUERY,
        ),
        docs_url="https://www.postgresql.org/docs/current/sql-select.html",
        icon="database",
        accent="from-blue-600 to-sky-700",
    ),
    ConnectorSpec(
        key="mysql",
        name="MySQL",
        category=ConnectorCategory.database,
        availability=ConnectorAvailability.live,
        summary="Connect a read-only MySQL source. Provide a SELECT per feed; "
        "columns are auto-mapped to the canonical schema.",
        feeds=("sales", "inventory", "products"),
        auth_fields=(
            AuthField(
                key="dsn",
                label="Connection string (DSN)",
                type="password",
                secret=True,
                placeholder="mysql://user:pass@host:3306/db",
                help="A read-only user is strongly recommended.",
            ),
            _SALES_QUERY,
            _INVENTORY_QUERY,
            _PRODUCTS_QUERY,
        ),
        docs_url="https://dev.mysql.com/doc/refman/8.0/en/select.html",
        icon="database",
        accent="from-orange-600 to-amber-700",
    ),
]

_BY_KEY: dict[str, ConnectorSpec] = {c.key: c for c in CATALOG}


def get_spec(key: str) -> ConnectorSpec | None:
    """Return the catalog entry for ``key`` (provider id), or None."""
    return _BY_KEY.get(key)


@dataclass
class CategoryGroup:
    category: ConnectorCategory
    label: str
    connectors: list[ConnectorSpec] = field(default_factory=list)


def grouped_catalog() -> list[CategoryGroup]:
    """The catalog grouped by category, in presentation order."""
    groups: dict[ConnectorCategory, CategoryGroup] = {
        cat: CategoryGroup(category=cat, label=CATEGORY_LABELS[cat]) for cat in CATEGORY_ORDER
    }
    for spec in CATALOG:
        groups[spec.category].connectors.append(spec)
    return [groups[cat] for cat in CATEGORY_ORDER if groups[cat].connectors]
