"""Tests for the connector catalog — the registry that powers the Hub."""

from __future__ import annotations

from app.connectors import CATALOG, ConnectorAvailability, get_spec, grouped_catalog


def test_catalog_keys_are_unique():
    keys = [c.key for c in CATALOG]
    assert len(keys) == len(set(keys)), "duplicate connector keys in catalog"


def test_expected_live_providers_present():
    live = {c.key for c in CATALOG if c.availability == ConnectorAvailability.live}
    assert {"shopify", "csv_upload", "excel_upload"} <= live


def test_get_spec_roundtrip_and_miss():
    assert get_spec("shopify").name == "Shopify"
    assert get_spec("does-not-exist") is None


def test_grouped_catalog_covers_every_connector():
    grouped = grouped_catalog()
    total = sum(len(g.connectors) for g in grouped)
    assert total == len(CATALOG)
    # Files group is presented first (highest ingest value, zero setup).
    assert grouped[0].category.value == "file"


def test_secret_fields_are_flagged():
    # Every provider that takes an access token / key / secret marks it secret so
    # the Hub renders a password field and the backend encrypts it at rest.
    for spec in CATALOG:
        for field in spec.auth_fields:
            looks_secret = any(w in field.key for w in ("token", "secret", "password", "key", "dsn", "json"))
            if looks_secret and field.key not in ("client_id", "application_id", "account_id"):
                assert field.secret, f"{spec.key}.{field.key} should be marked secret"
