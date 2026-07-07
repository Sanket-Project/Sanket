from __future__ import annotations

import enum


class IndustryCode(enum.StrEnum):
    fashion = "fashion"
    electronics = "electronics"
    pharma = "pharma"
    agrocenter = "agrocenter"
    hardware = "hardware"


class TenantTier(enum.StrEnum):
    growth = "growth"
    scale = "scale"
    enterprise = "enterprise"


class TenantStatus(enum.StrEnum):
    trial = "trial"
    active = "active"
    suspended = "suspended"
    cancelled = "cancelled"


class UserRole(enum.StrEnum):
    owner = "owner"
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"
    api_service = "api_service"


class ProductStatus(enum.StrEnum):
    active = "active"
    discontinued = "discontinued"
    seasonal = "seasonal"
    clearance = "clearance"
    pre_launch = "pre_launch"


class SignalType(enum.StrEnum):
    weather = "weather"
    trend_search = "trend_search"
    social_sentiment = "social_sentiment"
    competitor_price = "competitor_price"
    macro_economic = "macro_economic"
    regulatory = "regulatory"
    supplier_lead = "supplier_lead"
    logistics_disruption = "logistics_disruption"


class SignalStatus(enum.StrEnum):
    pending = "pending"
    validated = "validated"
    rejected = "rejected"
    expired = "expired"


class GxPBatchStatus(enum.StrEnum):
    quarantine = "quarantine"
    released = "released"
    rejected = "rejected"
    recalled = "recalled"
    expired = "expired"


class ForecastRunStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class TrendSignalSource(enum.StrEnum):
    fred = "fred"
    google_trends = "google_trends"
    reddit = "reddit"
    twitter = "twitter"
    news_api = "news_api"
    rss = "rss"
    pinterest = "pinterest"
    tiktok = "tiktok"
    instagram = "instagram"
    weather = "weather"
    competitor_price = "competitor_price"
    fda = "fda"
    logistics = "logistics"
    synthetic = "synthetic"


class TrendSignalKind(enum.StrEnum):
    economic_indicator = "economic_indicator"
    social_buzz = "social_buzz"
    search_interest = "search_interest"
    news_sentiment = "news_sentiment"
    commodity_price = "commodity_price"


class AlertSeverity(enum.StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(enum.StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    suppressed = "suppressed"
