"""Connector framework: the catalog of external data sources SANKET can connect
to, plus the canonical-schema import path that every source normalizes into.

The catalog (``catalog.py``) is the single source of truth for which providers
exist, how they're grouped, what credentials they need, and whether the sync
adapter is live yet. The frontend Integrations Hub renders straight from it, so
adding a provider is a one-line catalog edit — no UI change required.
"""

from app.connectors.catalog import (
    CATALOG,
    AuthField,
    ConnectorAvailability,
    ConnectorCategory,
    ConnectorSpec,
    get_spec,
    grouped_catalog,
)

__all__ = [
    "CATALOG",
    "AuthField",
    "ConnectorAvailability",
    "ConnectorCategory",
    "ConnectorSpec",
    "get_spec",
    "grouped_catalog",
]
