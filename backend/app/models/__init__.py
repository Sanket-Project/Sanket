"""Side-effect imports — ensures every ORM model registers with Base.metadata
on app startup so SQLAlchemy + Alembic see the full schema."""

from app.models.alert import AlertRule, ShortageAlert
from app.models.audit import AuditLog
from app.models.billing import Plan, Subscription, UsageEvent
from app.models.demo_request import DemoRequest
from app.models.forecast import ForecastResult, ForecastRun
from app.models.industry import Industry, IndustryProfile
from app.models.integration import IntegrationConnection
from app.models.inventory import InventoryLevel
from app.models.invite import Invite
from app.models.pharma import PharmaBatch
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.models.signal import ExternalSignal, SignalCluster
from app.models.tenant import RefreshToken, Tenant, User
from app.models.trend import HybridForecastRun, TrendSignal
from app.models.webhook import WebhookDelivery, WebhookEndpoint

__all__ = [
    "AlertRule",
    "AuditLog",
    "DemoRequest",
    "ExternalSignal",
    "ForecastResult",
    "ForecastRun",
    "HistoricalSale",
    "HybridForecastRun",
    "Industry",
    "IndustryProfile",
    "IntegrationConnection",
    "Invite",
    "InventoryLevel",
    "PharmaBatch",
    "Plan",
    "Product",
    "RefreshToken",
    "ShortageAlert",
    "SignalCluster",
    "Sku",
    "Subscription",
    "Tenant",
    "TrendSignal",
    "UsageEvent",
    "User",
    "WebhookDelivery",
    "WebhookEndpoint",
]
