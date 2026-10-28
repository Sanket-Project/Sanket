"""Operator configured TLS SMTP; bodies and recipients are never logged."""

import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage

from email_validator import EmailNotValidError, validate_email


@dataclass(frozen=True)
class EmailConfig:
    host: str = ""
    port: int = 587
    sender: str = ""
    username: str = ""
    password: str = field(default="", repr=False)

    @property
    def configured(self):
        return bool(self.host and self.sender)

    @classmethod
    def from_settings(cls, settings):
        secret = getattr(settings, "smtp_password", None)
        return cls(
            getattr(settings, "smtp_host", ""),
            getattr(settings, "smtp_port", 587),
            getattr(settings, "smtp_sender", ""),
            getattr(settings, "smtp_username", ""),
            secret.get_secret_value() if secret else "",
        )


def address(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("Invalid email header")
    try:
        return validate_email(value, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError:
        raise ValueError("Invalid email address") from None


def send_email(
    config: EmailConfig,
    recipient: str,
    subject: str,
    body: str,
    attachment: bytes | None = None,
    before_dispatch=None,
) -> str:
    recipient = address(recipient)
    if "\r" in subject or "\n" in subject or not 1 <= len(subject) <= 200 or len(body) > 40000:
        raise ValueError("Invalid email content")
    if not config.configured:
        return "unavailable"
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = address(config.sender), recipient, subject
    message.set_content(body)
    if attachment:
        message.add_attachment(
            attachment, maintype="application", subtype="pdf", filename="sanket-roi.pdf"
        )
    dispatched = False
    try:
        with smtplib.SMTP(config.host, config.port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            if config.username:
                smtp.login(config.username, config.password)
            if before_dispatch is not None:
                before_dispatch()
            dispatched = True
            refused = smtp.send_message(message)
            return "failed" if refused else "sent"
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        return "failed"
    except (OSError, smtplib.SMTPException):
        return "ambiguous" if dispatched else "failed"
