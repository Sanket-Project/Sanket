from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.services.notifications.email import EmailConfig, send_email
from app.services.notifications.preferences import Preferences, delivery_key, next_delivery


def test_preferences_are_explicit_and_timezone_validated():
    prefs = Preferences()
    assert prefs.language == "en"
    assert not prefs.weekly_enabled
    with pytest.raises(ValidationError):
        Preferences(timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        Preferences(language="fr")


def test_next_delivery_is_monday_in_selected_zone_and_dst_safe():
    now = datetime(2026, 10, 27, 12, tzinfo=UTC)
    assert next_delivery(now, "Asia/Kolkata", 8) == datetime(2026, 11, 2, 2, 30, tzinfo=UTC)
    assert next_delivery(now, "America/New_York", 8) == datetime(2026, 11, 2, 13, tzinfo=UTC)
    assert delivery_key(datetime(2026, 11, 2, 2, 30, tzinfo=UTC), "Asia/Kolkata") == "2026-11-02"


def test_mail_refuses_missing_transport_and_header_injection():
    config = EmailConfig()
    assert send_email(config, "qa@example.test", "Review", "Facts") == "unavailable"
    with pytest.raises(ValueError, match="header"):
        send_email(config, "qa@example.test\r\nBcc: victim@example.test", "Review", "Facts")


def test_transport_configuration_does_not_expose_password_in_repr():
    assert "synthetic-password" not in repr(EmailConfig(password="synthetic-password"))  # noqa: S106 -- synthetic fixture


def test_mail_uses_tls_and_reports_acceptance_not_fake_success():
    config = EmailConfig(host="smtp.example.test", sender="sanket@example.test")
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.send_message.return_value = {}
    with patch("smtplib.SMTP", return_value=connection):
        assert send_email(config, "qa@example.test", "Review", "Facts") == "sent"
    connection.starttls.assert_called_once()
    connection.send_message.assert_called_once()


def test_mail_timeout_after_dispatch_is_ambiguous_never_auto_retry():
    config = EmailConfig(host="smtp.example.test", sender="sanket@example.test")
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.send_message.side_effect = TimeoutError()
    with patch("smtplib.SMTP", return_value=connection):
        assert send_email(config, "qa@example.test", "Review", "Facts") == "ambiguous"
