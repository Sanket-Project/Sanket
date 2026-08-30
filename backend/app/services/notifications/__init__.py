"""Outbound notification channels.

WhatsApp first: most SME owners will never open a dashboard, but they read
every message on their phone. The digest that goes out is the same decision
queue the web app shows, compressed to what a person can act on before their
first cup of tea.
"""

from app.services.notifications.digest import DailyDigest, build_digest, render_text
from app.services.notifications.whatsapp import (
    WhatsAppConfig,
    WhatsAppMessage,
    WhatsAppProvider,
    WhatsAppResult,
    get_provider,
    load_tenant_config,
)

__all__ = [
    "DailyDigest",
    "WhatsAppConfig",
    "WhatsAppMessage",
    "WhatsAppProvider",
    "WhatsAppResult",
    "build_digest",
    "get_provider",
    "load_tenant_config",
    "render_text",
]
