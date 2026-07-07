"""Thin async Shopify Admin REST API client.

Scope is deliberately small — just what the MVP sync needs: validate the token,
and page through products, locations, inventory levels, and orders. Built on
httpx so it can share the app's connection pool.

Handles the two things that bite every Shopify integration:
  * cursor pagination via the ``Link`` header (page_info), and
  * the leaky-bucket rate limit (HTTP 429 + ``Retry-After``).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


def verify_webhook_hmac(secret: str, raw_body: bytes, hmac_header: str | None) -> bool:
    """Verify a Shopify webhook's HMAC-SHA256 signature (base64) against the
    app's shared secret. Constant-time comparison."""
    if not secret or not hmac_header:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(computed, hmac_header)


_LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')
_MAX_RETRIES = 5
_PAGE_LIMIT = 250  # Shopify REST max page size


class ShopifyError(Exception):
    """Raised when the Shopify API returns an unrecoverable error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_shop_domain(raw: str) -> str:
    """Normalize user input to a ``<store>.myshopify.com`` host.

    Accepts ``mystore``, ``mystore.myshopify.com``, or a full URL.
    """
    host = raw.strip().lower()
    host = re.sub(r"^https?://", "", host)
    host = host.split("/")[0].strip()
    if not host:
        raise ShopifyError("Shop domain is required")
    if "." not in host:
        host = f"{host}.myshopify.com"
    return host


class ShopifyClient:
    def __init__(
        self,
        shop_domain: str,
        access_token: str,
        *,
        api_version: str = "2024-10",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.shop_domain = normalize_shop_domain(shop_domain)
        self._token = access_token
        self._api_version = api_version
        self._base = f"https://{self.shop_domain}/admin/api/{api_version}"
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> ShopifyClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Shopify-Access-Token": self._token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET with rate-limit-aware retry. ``url`` may be absolute (pagination)
        or a path fragment like ``/products.json``."""
        assert self._client is not None
        full = url if url.startswith("http") else f"{self._base}{url}"
        for attempt in range(_MAX_RETRIES):
            resp = await self._client.get(full, headers=self._headers, params=params)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "2"))
                log.warning("shopify.rate_limited", retry_after=retry_after, attempt=attempt)
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code in (401, 403):
                raise ShopifyError(
                    "Shopify rejected the access token (check the token and its scopes)",
                    status_code=resp.status_code,
                )
            if resp.status_code == 404:
                raise ShopifyError("Shop not found — check the store domain", status_code=404)
            if resp.status_code >= 500:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise ShopifyError(
                    f"Shopify API error {resp.status_code}: {resp.text[:200]}",
                    status_code=resp.status_code,
                )
            return resp
        raise ShopifyError("Shopify API: exceeded retry budget (rate limited / 5xx)")

    @staticmethod
    def _next_url(resp: httpx.Response) -> str | None:
        link = resp.headers.get("Link") or resp.headers.get("link")
        if not link:
            return None
        m = _LINK_NEXT_RE.search(link)
        return m.group(1) if m else None

    async def _paginate(
        self, path: str, root_key: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict]:
        """Yield items from a paginated list endpoint following Link headers."""
        # First page carries the filter params; subsequent pages encode state in
        # the page_info cursor, so params must NOT be re-sent with the next URL.
        resp = await self._get(path, params={"limit": _PAGE_LIMIT, **(params or {})})
        while True:
            payload = resp.json()
            for item in payload.get(root_key, []):
                yield item
            nxt = self._next_url(resp)
            if not nxt:
                return
            resp = await self._get(nxt)

    # ── Public API ───────────────────────────────────────────────────────────
    async def get_shop(self) -> dict[str, Any]:
        """Validate the token and return basic shop info (name, currency, ...)."""
        resp = await self._get("/shop.json")
        return resp.json().get("shop", {})

    def iter_products(self) -> AsyncIterator[dict]:
        return self._paginate("/products.json", "products")

    async def get_locations(self) -> list[dict]:
        resp = await self._get("/locations.json")
        return resp.json().get("locations", [])

    def iter_inventory_levels(self, location_ids: list[int]) -> AsyncIterator[dict]:
        ids = ",".join(str(i) for i in location_ids)
        return self._paginate("/inventory_levels.json", "inventory_levels", {"location_ids": ids})

    def iter_orders(self, created_at_min: str | None = None) -> AsyncIterator[dict]:
        params: dict[str, Any] = {"status": "any", "order": "created_at asc"}
        if created_at_min:
            params["created_at_min"] = created_at_min
        return self._paginate("/orders.json", "orders", params)

    async def list_webhooks(self) -> list[dict]:
        resp = await self._get("/webhooks.json")
        return resp.json().get("webhooks", [])

    async def create_webhook(self, topic: str, address: str) -> dict:
        """Register a webhook subscription (idempotent on Shopify's side per
        topic+address). Uses POST, so it doesn't go through the GET retry path."""
        assert self._client is not None
        resp = await self._client.post(
            f"{self._base}/webhooks.json",
            headers=self._headers,
            json={"webhook": {"topic": topic, "address": address, "format": "json"}},
        )
        if resp.status_code == 422:
            # Already exists for this topic+address — treat as success.
            return {"topic": topic, "address": address, "status": "exists"}
        if resp.status_code >= 400:
            raise ShopifyError(
                f"Failed to register webhook {topic}: {resp.status_code} {resp.text[:160]}",
                status_code=resp.status_code,
            )
        return resp.json().get("webhook", {})
