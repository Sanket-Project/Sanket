"""Direct SQL source connectors (PostgreSQL, MySQL).

Design mirrors the CSV/Excel importer rather than Shopify: there is no vendor
API to model, just a customer-supplied read-only connection string plus one
``SELECT`` per canonical feed (sales / inventory / products). Whatever columns
that query returns are matched against the exact same alias table the
upload importer uses (``app.services.integrations.file_import``), so

    SELECT sku, qty AS quantity, sale_date AS timestamp FROM orders

lands in the canonical schema exactly like an uploaded spreadsheet would —
``import_rows`` already takes ``(headers, records)`` regardless of where they
came from, so a DB pull only needs to *produce* that shape.

Safety
------
* Only ``SELECT`` / ``WITH`` statements are accepted, and the query is wrapped
  in a derived table (``SELECT * FROM (<query>) AS sanket_src``) so it always
  executes as a single read. This is a speed bump against accidental misuse,
  not a security boundary — the DSN should point at a read-only role.
* A semicolon anywhere but a single trailing one is rejected (blocks stacked
  statements).
* Results are capped at ``_MAX_ROWS`` and the whole pull is bounded by
  ``_QUERY_TIMEOUT_S`` to protect both SANKET and the customer's database.
* Each pull opens a fresh engine and disposes it afterwards — no pooled
  connection to a customer's database is held between syncs.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.enums import IndustryCode
from app.services.integrations.file_import import import_rows

log = structlog.get_logger(__name__)

_MAX_ROWS = 200_000
_QUERY_TIMEOUT_S = 60

# provider key -> (sqlalchemy async drivername, schemes accepted from the
# customer's DSN). Customers naturally write "postgres://" or "mysql://"; we
# rewrite to the async driver SANKET actually uses.
_DRIVERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "postgres": ("postgresql+asyncpg", ("postgres", "postgresql", "postgresql+asyncpg")),
    "mysql": ("mysql+aiomysql", ("mysql", "mysql+aiomysql", "mysql+pymysql")),
}

FEED_QUERY_KEYS: dict[str, str] = {
    "sales": "sales_query",
    "inventory": "inventory_query",
    "products": "products_query",
}

_READ_ONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

_EMPTY_STATS: dict[str, Any] = {
    "rows_total": 0,
    "rows_imported": 0,
    "rows_skipped": 0,
    "products_created": 0,
    "skus_created": 0,
    "inventory_rows": 0,
    "sales_rows": 0,
    "errors": [],
}


class SqlSourceError(ValueError):
    """A configuration, validation, or connectivity problem — message is
    surfaced to the API caller / UI as-is, so keep it user-facing."""


def normalize_dsn(provider: str, dsn: str) -> str:
    """Rewrite a customer-supplied DSN onto SANKET's async driver, after
    checking the scheme actually matches the chosen provider."""
    drivers = _DRIVERS.get(provider)
    if drivers is None:
        raise SqlSourceError(f"Unsupported SQL provider: {provider}")
    drivername, accepted = drivers
    try:
        url = make_url(dsn)
    except Exception as exc:  # noqa: BLE001 - any parse failure is a user input error
        raise SqlSourceError(f"Could not parse connection string: {exc}") from exc
    if url.drivername not in accepted:
        raise SqlSourceError(
            f"{provider} expects a {'/'.join(accepted)} connection string, got {url.drivername!r}"
        )
    return url.set(drivername=drivername).render_as_string(hide_password=False)


def _assert_safe_query(query: str) -> str:
    q = (query or "").strip()
    if not q:
        raise SqlSourceError("Query is empty")
    if not _READ_ONLY_RE.match(q):
        raise SqlSourceError("Only SELECT / WITH queries are allowed")
    bare = q[:-1] if q.endswith(";") else q
    if ";" in bare:
        raise SqlSourceError("Only a single statement is allowed per query")
    return bare


async def _open(provider: str, dsn: str):
    normalized = normalize_dsn(provider, dsn)
    return create_async_engine(normalized, pool_pre_ping=True, pool_size=1, max_overflow=0)


async def validate_connection(provider: str, dsn: str) -> None:
    """Open a connection and run ``SELECT 1`` — same spirit as Shopify's
    pre-persist token check. Raises SqlSourceError on any failure."""
    engine = await _open(provider, dsn)
    try:

        async def _ping() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_ping(), timeout=_QUERY_TIMEOUT_S)
    except SqlSourceError:
        raise
    except TimeoutError as exc:
        raise SqlSourceError(f"Connection to {provider} timed out") from exc
    except Exception as exc:  # noqa: BLE001 - surface the driver error to the user
        raise SqlSourceError(f"Could not connect: {exc}") from exc
    finally:
        await engine.dispose()


async def fetch_rows(provider: str, dsn: str, query: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Run one customer-supplied SELECT and return (headers, row dicts)."""
    safe_query = _assert_safe_query(query)
    engine = await _open(provider, dsn)
    try:

        async def _run() -> tuple[list[str], list[dict[str, Any]]]:
            wrapped = text(f"SELECT * FROM ({safe_query}) AS sanket_src LIMIT {_MAX_ROWS}")  # noqa: S608
            async with engine.connect() as conn:
                result = await conn.execute(wrapped)
                headers = list(result.keys())
                rows = result.fetchall()
            return headers, [dict(zip(headers, row, strict=True)) for row in rows]

        return await asyncio.wait_for(_run(), timeout=_QUERY_TIMEOUT_S)
    except SqlSourceError:
        raise
    except TimeoutError as exc:
        raise SqlSourceError(f"Query timed out after {_QUERY_TIMEOUT_S}s") from exc
    except Exception as exc:  # noqa: BLE001 - surface the driver error to the user
        raise SqlSourceError(f"Query failed: {exc}") from exc
    finally:
        await engine.dispose()


async def run_sql_sync(
    *,
    db,
    tenant_id: uuid.UUID,
    provider: str,
    industry: IndustryCode,
    dsn: str,
    queries: dict[str, str | None],
) -> dict[str, Any]:
    """Pull each configured feed query and import it into the canonical schema.

    Returns a per-feed stats dict (same shape ``import_rows`` returns) plus a
    ``synced_at`` timestamp; raises SqlSourceError if nothing is configured.
    """
    stats: dict[str, Any] = {}
    configured = False
    for kind, key in FEED_QUERY_KEYS.items():
        query = queries.get(key)
        if not query:
            continue
        configured = True
        headers, records = await fetch_rows(provider, dsn, query)
        if records:
            stats[kind] = await import_rows(
                db=db,
                tenant_id=tenant_id,
                industry=industry,
                kind=kind,
                headers=headers,
                records=records,
            )
        else:
            stats[kind] = dict(_EMPTY_STATS)
        log.info(
            "sql_source.feed.synced",
            provider=provider,
            kind=kind,
            tenant=str(tenant_id),
            imported=stats[kind]["rows_imported"],
        )

    if not configured:
        raise SqlSourceError(
            "No feed queries configured (sales_query / inventory_query / products_query)"
        )
    stats["synced_at"] = datetime.now(tz=UTC).isoformat()
    return stats
