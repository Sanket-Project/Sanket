"""WhatsApp delivery — provider-agnostic, so the API can be plugged in later.

The business API credentials are not wired up yet, and that is deliberately not
a blocker: everything except the final HTTP call is real. The digest is built
from live data, rendered, validated, and recorded; the only thing the provider
swap changes is whether the last hop hits Meta's Cloud API, Twilio, or the log.

Providers
---------
``meta``    — WhatsApp Business Cloud API (graph.facebook.com). Needs a phone
              number id and a permanent access token.
``twilio``  — Twilio's WhatsApp channel. Needs an account SID, auth token and a
              ``whatsapp:+…`` sender.
``console`` — the default until credentials exist. Renders and logs the exact
              payload that *would* be sent and reports success=False with a
              clear reason, so nothing silently pretends to have delivered.

Numbers are validated to E.164 before anything is queued: a malformed number is
a configuration bug we can catch now rather than a delivery failure later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx
import structlog

log = structlog.get_logger(__name__)

ProviderName = Literal["meta", "twilio", "console"]

#: E.164: a leading +, a non-zero country digit, then up to 14 more digits.
E164 = re.compile(r"^\+[1-9]\d{7,14}$")

#: WhatsApp hard-caps a text body at 4096 characters.
MAX_BODY_CHARS = 4096


class InvalidRecipientError(ValueError):
    pass


def normalize_phone(raw: str, *, default_country_code: str = "91") -> str:
    """Coerce a user-entered number into E.164, or raise.

    Indian SME users type ``98765 43210``, ``098765-43210`` and
    ``+91 98765 43210`` interchangeably; all three are the same number and all
    three should work.
    """
    cleaned = re.sub(r"[^\d+]", "", raw or "")
    if not cleaned:
        raise InvalidRecipientError("Phone number is empty")
    if not cleaned.startswith("+"):
        cleaned = cleaned.lstrip("0")
        if not cleaned.startswith(default_country_code):
            cleaned = default_country_code + cleaned
        cleaned = "+" + cleaned
    if not E164.match(cleaned):
        raise InvalidRecipientError(f"'{raw}' is not a valid phone number")
    return cleaned


@dataclass(frozen=True, slots=True)
class Recipient:
    phone: str  # E.164
    name: str | None = None
    role: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"phone": self.phone, "name": self.name, "role": self.role}


@dataclass(frozen=True, slots=True)
class WhatsAppConfig:
    """Per-tenant delivery settings, stored in ``Tenant.settings['notifications']``."""

    enabled: bool = False
    recipients: tuple[Recipient, ...] = ()
    #: Local hour (0–23) the daily digest should go out.
    send_hour: int = 8
    timezone: str = "Asia/Kolkata"
    #: Only surface decisions at or above this confidence in the message.
    min_confidence: int = 50
    #: How many recommendations to include before "…and N more".
    max_items: int = 5
    include_alerts: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "recipients": [r.as_dict() for r in self.recipients],
            "send_hour": self.send_hour,
            "timezone": self.timezone,
            "min_confidence": self.min_confidence,
            "max_items": self.max_items,
            "include_alerts": self.include_alerts,
        }


def load_tenant_config(settings: dict | None) -> WhatsAppConfig:
    raw = ((settings or {}).get("notifications") or {}).get("whatsapp") or {}
    base = WhatsAppConfig()
    recipients: list[Recipient] = []
    for r in raw.get("recipients") or []:
        try:
            recipients.append(
                Recipient(
                    phone=normalize_phone(str(r.get("phone", ""))),
                    name=r.get("name"),
                    role=r.get("role"),
                )
            )
        except InvalidRecipientError:
            # A bad number saved earlier should not break the whole config read.
            log.warning("whatsapp.recipient.invalid", raw=r)
    try:
        return WhatsAppConfig(
            enabled=bool(raw.get("enabled", base.enabled)),
            recipients=tuple(recipients),
            send_hour=int(raw.get("send_hour", base.send_hour)),
            timezone=str(raw.get("timezone", base.timezone)),
            min_confidence=int(raw.get("min_confidence", base.min_confidence)),
            max_items=int(raw.get("max_items", base.max_items)),
            include_alerts=bool(raw.get("include_alerts", base.include_alerts)),
        )
    except (TypeError, ValueError):
        log.warning("whatsapp.config.invalid", raw=raw)
        return base


@dataclass(frozen=True, slots=True)
class WhatsAppMessage:
    to: str  # E.164
    body: str
    #: Meta requires an approved template for messages outside the 24-hour
    #: customer-service window, which a scheduled 8am digest always is.
    template_name: str | None = None
    template_language: str = "en"
    template_params: tuple[str, ...] = ()

    def truncated_body(self) -> str:
        if len(self.body) <= MAX_BODY_CHARS:
            return self.body
        return self.body[: MAX_BODY_CHARS - 1] + "…"


@dataclass
class WhatsAppResult:
    to: str
    success: bool
    provider: ProviderName
    provider_message_id: str | None = None
    error: str | None = None
    sent_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: The exact rendered body, kept so the console provider and the preview
    #: endpoint return something inspectable.
    body: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "to": self.to,
            "success": self.success,
            "provider": self.provider,
            "provider_message_id": self.provider_message_id,
            "error": self.error,
            "sent_at": self.sent_at.isoformat(),
            "body": self.body,
        }


class WhatsAppProvider(Protocol):
    name: ProviderName

    async def send(self, message: WhatsAppMessage) -> WhatsAppResult: ...


class ConsoleProvider:
    """Renders and logs, never transmits.

    Reports ``success=False`` on purpose. A no-op that claims success is how you
    end up believing a customer got their stockout warning.
    """

    name: ProviderName = "console"

    def __init__(self, reason: str = "No WhatsApp credentials configured") -> None:
        self.reason = reason

    async def send(self, message: WhatsAppMessage) -> WhatsAppResult:
        body = message.truncated_body()
        log.info("whatsapp.console.render", to=message.to, chars=len(body), body=body)
        return WhatsAppResult(
            to=message.to,
            success=False,
            provider=self.name,
            error=self.reason,
            body=body,
        )


class MetaCloudProvider:
    """WhatsApp Business Cloud API."""

    name: ProviderName = "meta"

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        api_base: str = "https://graph.facebook.com",
        api_version: str = "v21.0",
        timeout_s: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = access_token
        self._phone_number_id = phone_number_id
        self._url = f"{api_base.rstrip('/')}/{api_version}/{phone_number_id}/messages"
        self._timeout = timeout_s
        self._client = client

    def _payload(self, message: WhatsAppMessage) -> dict[str, Any]:
        if message.template_name:
            return {
                "messaging_product": "whatsapp",
                "to": message.to,
                "type": "template",
                "template": {
                    "name": message.template_name,
                    "language": {"code": message.template_language},
                    "components": (
                        [
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": p}
                                    for p in message.template_params
                                ],
                            }
                        ]
                        if message.template_params
                        else []
                    ),
                },
            }
        return {
            "messaging_product": "whatsapp",
            "to": message.to,
            "type": "text",
            "text": {"preview_url": False, "body": message.truncated_body()},
        }

    async def send(self, message: WhatsAppMessage) -> WhatsAppResult:
        headers = {"Authorization": f"Bearer {self._token}"}
        body = message.truncated_body()
        try:
            if self._client is not None:
                r = await self._client.post(
                    self._url,
                    json=self._payload(message),
                    headers=headers,
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    r = await client.post(
                        self._url, json=self._payload(message), headers=headers
                    )
            r.raise_for_status()
            data = r.json()
            mid = (data.get("messages") or [{}])[0].get("id")
            return WhatsAppResult(
                to=message.to,
                success=True,
                provider=self.name,
                provider_message_id=mid,
                body=body,
            )
        except httpx.HTTPStatusError as exc:
            # Never log the token; the response body can carry the recipient
            # number, so keep it short.
            detail = exc.response.text[:200]
            log.warning("whatsapp.meta.http_error", status=exc.response.status_code)
            return WhatsAppResult(
                to=message.to,
                success=False,
                provider=self.name,
                error=f"{exc.response.status_code}: {detail}",
                body=body,
            )
        except httpx.HTTPError as exc:
            log.warning("whatsapp.meta.unreachable", error=str(exc))
            return WhatsAppResult(
                to=message.to, success=False, provider=self.name, error=str(exc), body=body
            )


class TwilioProvider:
    """Twilio's WhatsApp channel — form-encoded, basic auth."""

    name: ProviderName = "twilio"

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        api_base: str = "https://api.twilio.com",
        timeout_s: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._sid = account_sid
        self._token = auth_token
        self._from = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
        self._url = f"{api_base.rstrip('/')}/2010-04-01/Accounts/{account_sid}/Messages.json"
        self._timeout = timeout_s
        self._client = client

    async def send(self, message: WhatsAppMessage) -> WhatsAppResult:
        body = message.truncated_body()
        data = {"From": self._from, "To": f"whatsapp:{message.to}", "Body": body}
        auth = (self._sid, self._token)
        try:
            if self._client is not None:
                r = await self._client.post(
                    self._url, data=data, auth=auth, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    r = await client.post(self._url, data=data, auth=auth)
            r.raise_for_status()
            return WhatsAppResult(
                to=message.to,
                success=True,
                provider=self.name,
                provider_message_id=r.json().get("sid"),
                body=body,
            )
        except httpx.HTTPStatusError as exc:
            log.warning("whatsapp.twilio.http_error", status=exc.response.status_code)
            return WhatsAppResult(
                to=message.to,
                success=False,
                provider=self.name,
                error=f"{exc.response.status_code}: {exc.response.text[:200]}",
                body=body,
            )
        except httpx.HTTPError as exc:
            log.warning("whatsapp.twilio.unreachable", error=str(exc))
            return WhatsAppResult(
                to=message.to, success=False, provider=self.name, error=str(exc), body=body
            )


def get_provider(settings: Any, client: httpx.AsyncClient | None = None) -> WhatsAppProvider:
    """Pick a provider from app settings, falling back to the console renderer.

    ``settings`` is the app ``Settings`` object; accessed with ``getattr`` so
    this module stays importable (and testable) without the full config loaded.
    """
    provider = (getattr(settings, "whatsapp_provider", None) or "console").lower()

    if provider == "meta":
        token = getattr(settings, "whatsapp_access_token", None)
        phone_id = getattr(settings, "whatsapp_phone_number_id", None)
        if token and phone_id:
            return MetaCloudProvider(
                access_token=token,
                phone_number_id=phone_id,
                api_base=getattr(settings, "whatsapp_api_base", "https://graph.facebook.com"),
                api_version=getattr(settings, "whatsapp_api_version", "v21.0"),
                client=client,
            )
        return ConsoleProvider("WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID are not set")

    if provider == "twilio":
        sid = getattr(settings, "whatsapp_twilio_account_sid", None)
        token = getattr(settings, "whatsapp_twilio_auth_token", None)
        sender = getattr(settings, "whatsapp_from_number", None)
        if sid and token and sender:
            return TwilioProvider(
                account_sid=sid, auth_token=token, from_number=sender, client=client
            )
        return ConsoleProvider("Twilio WhatsApp credentials are not set")

    return ConsoleProvider()


async def send_all(
    provider: WhatsAppProvider,
    *,
    recipients: tuple[Recipient, ...],
    body: str,
    template_name: str | None = None,
) -> list[WhatsAppResult]:
    results: list[WhatsAppResult] = []
    for r in recipients:
        results.append(
            await provider.send(
                WhatsAppMessage(to=r.phone, body=body, template_name=template_name)
            )
        )
    return results
