"""Tests for the WhatsApp channel: number handling, provider selection, rendering.

The delivery credentials are not wired up yet, so the contract that matters most
here is that an unconfigured install *tells the truth* — it renders the message
and reports it as not sent, rather than quietly returning success.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.notifications import digest as digest_svc
from app.services.notifications import whatsapp as wa

# ── Phone numbers ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+919876543210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("98765 43210", "+919876543210"),
        ("+91 98765-43210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("+14155552671", "+14155552671"),
    ],
)
def test_indian_numbers_normalize_to_e164(raw, expected):
    assert wa.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abcd", "+0123", "12"])
def test_malformed_numbers_are_rejected_at_config_time(raw):
    with pytest.raises(wa.InvalidRecipientError):
        wa.normalize_phone(raw)


# ── Provider selection ───────────────────────────────────────────────────────


def test_unconfigured_install_falls_back_to_the_console_provider():
    provider = wa.get_provider(SimpleNamespace())
    assert provider.name == "console"


def test_meta_without_credentials_does_not_silently_become_live():
    provider = wa.get_provider(
        SimpleNamespace(whatsapp_provider="meta", whatsapp_access_token=None)
    )
    assert provider.name == "console"
    assert "WHATSAPP_ACCESS_TOKEN" in provider.reason


def test_meta_with_credentials_is_selected():
    provider = wa.get_provider(
        SimpleNamespace(
            whatsapp_provider="meta",
            whatsapp_access_token="tok",  # noqa: S106 - fixture, not a credential
            whatsapp_phone_number_id="123",
        )
    )
    assert provider.name == "meta"


@pytest.mark.anyio
async def test_console_provider_reports_failure_not_fake_success():
    result = await wa.ConsoleProvider().send(
        wa.WhatsAppMessage(to="+919876543210", body="hello")
    )
    assert result.success is False
    assert result.error
    assert result.body == "hello"


@pytest.mark.anyio
async def test_bodies_are_truncated_to_the_whatsapp_limit():
    long_body = "x" * (wa.MAX_BODY_CHARS + 500)
    result = await wa.ConsoleProvider().send(
        wa.WhatsAppMessage(to="+919876543210", body=long_body)
    )
    assert len(result.body) == wa.MAX_BODY_CHARS


# ── Tenant config ────────────────────────────────────────────────────────────


def test_tenant_config_round_trips_and_drops_bad_numbers():
    config = wa.load_tenant_config(
        {
            "notifications": {
                "whatsapp": {
                    "enabled": True,
                    "send_hour": 7,
                    "recipients": [
                        {"phone": "9876543210", "name": "Owner"},
                        {"phone": "not-a-number", "name": "Broken"},
                    ],
                }
            }
        }
    )
    assert config.enabled is True
    assert config.send_hour == 7
    assert [r.phone for r in config.recipients] == ["+919876543210"]


def test_missing_config_is_disabled_by_default():
    assert wa.load_tenant_config(None).enabled is False
    assert wa.load_tenant_config({}).recipients == ()


# ── Money formatting ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (42_000, "₹42,000"),
        (7_500_000, "₹75.00 L"),
        (12_000_000, "₹1.20 Cr"),
        (500, "₹500"),
    ],
)
def test_rupees_use_lakh_and_crore(amount, expected):
    assert digest_svc.format_money(amount, "INR") == expected


def test_other_currencies_keep_plain_grouping():
    assert digest_svc.format_money(7_500_000, "USD") == "USD 7,500,000"


# ── Rendering ────────────────────────────────────────────────────────────────


def _digest(**kw) -> digest_svc.DailyDigest:
    defaults = {"tenant_name": "Sharma Distributors", "industry": "pharma"}
    return digest_svc.DailyDigest(**{**defaults, **kw})


def test_empty_queue_does_not_claim_stockout_risk_was_measured():
    body = digest_svc.render_text(_digest(empty_reason="No purchase recommendations above the confidence threshold today."))
    assert "No purchase recommendations above the confidence threshold today." in body
    assert "no stockout risks" not in body
    assert "Nothing needs your attention" not in body
    assert "coverage" in body.lower()


def test_empty_digest_reports_only_what_is_recorded():
    body = digest_svc.render_text(_digest())
    assert "No purchase recommendations or open alerts are recorded." in body
    assert "Sharma Distributors" in body


def test_digest_leads_with_the_action_not_the_forecast():
    d = _digest(
        items=[
            digest_svc.DigestItem(
                sku_code="PARA-500-10",
                urgency="critical",
                headline="Raise a purchase order for 1,500 units",
                units=1500,
                value=42_000,
                value_label="protects",
                days_of_cover=8.0,
                confidence=88,
                reason="stock runs out in 8 days, supplier takes 21",
            )
        ],
        total_units=1500,
        total_value=42_000,
    )
    body = digest_svc.render_text(d)
    assert "PARA-500-10" in body
    assert "Order 1,500 units" in body
    assert "₹42,000" in body
    assert "8 days" in body
    # No percentiles or model jargon on a phone screen.
    assert "p50" not in body
    assert "p90" not in body


def test_low_confidence_items_carry_a_warning():
    d = _digest(
        items=[
            digest_svc.DigestItem(
                sku_code="NEW-1", urgency="high", headline="Order", units=100,
                value=1000, value_label="protects", days_of_cover=None,
                confidence=41, reason="forecast demand exceeds stock on hand",
            )
        ]
    )
    assert "confidence only 41%" in digest_svc.render_text(d)


def test_overflow_items_are_summarised_not_dumped():
    d = _digest(
        items=[
            digest_svc.DigestItem(
                sku_code=f"S{i}", urgency="normal", headline="Order", units=10,
                value=100, value_label="protects", days_of_cover=None,
                confidence=90, reason="demand exceeds stock",
            )
            for i in range(3)
        ],
        more_count=17,
    )
    assert "…and 17 more in the app." in digest_svc.render_text(d)


def test_rendered_digest_fits_a_whatsapp_message():
    d = _digest(
        items=[
            digest_svc.DigestItem(
                sku_code=f"SKU-{i:03d}", urgency="critical",
                headline="Raise a purchase order", units=9999,
                value=1_234_567, value_label="protects", days_of_cover=3.0,
                confidence=40, reason="stock runs out in 3 days, supplier takes 30",
            )
            for i in range(20)
        ],
        open_alerts=12,
        total_units=199_980,
        total_value=24_691_340,
    )
    assert len(digest_svc.render_text(d)) <= wa.MAX_BODY_CHARS
