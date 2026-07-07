"""Thin async WooCommerce REST API client.

Built on httpx so it can share the app's connection pool.
Uses WooCommerce REST API v3 (standard under WordPress /wp-json/wc/v3).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

_MAX_RETRIES = 5
_PAGE_LIMIT = 100  # WooCommerce REST API max per_page is typically 100


class WooCommerceError(Exception):
    """Raised when the WooCommerce API returns an unrecoverable error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_base_url(url: str) -> str:
    """Normalize user input to a fully-qualified URL without trailing slash."""
    url = url.strip()
    if not url:
        raise WooCommerceError("Base URL is required")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")


class WooCommerceClient:
    def __init__(
        self,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        self._key = consumer_key.strip()
        self._secret = consumer_secret.strip()
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> WooCommerceClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @property
    def _auth(self) -> tuple[str, str]:
        return (self._key, self._secret)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET request with standard retries for transient 5xx or rate limit issues."""
        assert self._client is not None
        # Ensure path starts with /wp-json/wc/v3/
        subpath = path.lstrip("/")
        if not subpath.startswith("wp-json/"):
            full_url = f"{self.base_url}/wp-json/wc/v3/{subpath}"
        else:
            full_url = f"{self.base_url}/{subpath}"

        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(full_url, auth=self._auth, params=params)
            except httpx.RequestError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise WooCommerceError(f"HTTP request failed: {exc}") from exc
                await asyncio.sleep(1.0 * (attempt + 1))
                continue

            if resp.status_code == 429:
                # Retry-After header might be present, default to 2 seconds
                retry_after = float(resp.headers.get("Retry-After", "2"))
                log.warning("woocommerce.rate_limited", retry_after=retry_after, attempt=attempt)
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code in (401, 403):
                raise WooCommerceError(
                    "WooCommerce rejected credentials (check consumer key and secret)",
                    status_code=resp.status_code,
                )

            if resp.status_code == 404:
                raise WooCommerceError(
                    "WooCommerce API endpoint not found (verify base URL)", status_code=404
                )

            if resp.status_code >= 500:
                if attempt == _MAX_RETRIES - 1:
                    raise WooCommerceError(
                        f"WooCommerce server error {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )
                await asyncio.sleep(1.5 * (attempt + 1))
                continue

            if resp.status_code >= 400:
                raise WooCommerceError(
                    f"WooCommerce API error {resp.status_code}: {resp.text[:200]}",
                    status_code=resp.status_code,
                )

            return resp

        raise WooCommerceError("WooCommerce API: exceeded retry budget")

    async def validate_credentials(self) -> None:
        """Verify the store credentials by requesting the general settings list."""
        # This is a safe read-only endpoint that does not return massive payloads
        await self._get("settings/general")

    async def _paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict]:
        """Page through WooCommerce REST resource."""
        page = 1
        query_params = dict(params or {})
        query_params["per_page"] = _PAGE_LIMIT

        while True:
            query_params["page"] = page
            resp = await self._get(path, params=query_params)
            data = resp.json()
            if not isinstance(data, list) or not data:
                break

            for item in data:
                yield item

            # Check if we've reached the total pages from header
            total_pages_header = resp.headers.get("X-WP-TotalPages") or resp.headers.get(
                "x-wp-totalpages"
            )
            if total_pages_header:
                try:
                    if page >= int(total_pages_header):
                        break
                except ValueError:
                    pass

            page += 1

    def get_products(self) -> AsyncIterator[dict]:
        """Iterate all WooCommerce products."""
        return self._paginate("products")

    async def get_product_variations(self, product_id: int) -> list[dict]:
        """Fetch all variations of a variable product."""
        variations = []
        async for variation in self._paginate(f"products/{product_id}/variations"):
            variations.append(variation)
        return variations

    def get_orders(self, since_date: datetime | None = None) -> AsyncIterator[dict]:
        """Iterate orders created or modified after a given date.

        Uses ISO8601 string in the store's timezone or GMT.
        """
        params = {}
        if since_date:
            # WooCommerce expects date in format YYYY-MM-DDTHH:MM:SS
            # We filter by `after` which matches order date_created_gmt
            params["after"] = since_date.isoformat().split("+")[0]
        return self._paginate("orders", params=params)
