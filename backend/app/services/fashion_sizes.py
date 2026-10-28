"""Apparel size labels: one canonical spelling per size, extended sizes included.

Retail catalogues spell the same size several ways (``XXXL``, ``3XL``,
``3 xl``), and Indian ethnic wear routinely runs to 4XL and 5XL. Every label is
normalised to one canonical form so size curves and variant identity do not
split a size in two — but a label we do not recognise is never guessed into
one: it is returned as unknown and the caller rejects it.
"""

from __future__ import annotations

import re

#: Smallest to largest. ``FREE`` (free / one size) sorts last.
CANONICAL_SIZES: tuple[str, ...] = (
    "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL", "6XL", "FREE",
)

_FREE = {"FREE", "FREESIZE", "FS", "ONESIZE", "OS", "FR", "FRE"}
_NUMERIC_XL = re.compile(r"([2-6])XL")
_REPEATED_XL = re.compile(r"(X{2,6})L")


def normalize_size(raw: object) -> str | None:
    """Canonical size for ``raw``, or ``None`` when it is not a known apparel size."""
    if raw is None:
        return None
    token = re.sub(r"[\s_.\-]+", "", str(raw)).upper()
    if not token:
        return None
    if token in CANONICAL_SIZES:
        return token
    if token in _FREE:
        return "FREE"
    if re.fullmatch(r"[1-6]X", token):
        n = int(token[0])
        return "XL" if n == 1 else "XXL" if n == 2 else f"{n}XL"
    numeric = _NUMERIC_XL.fullmatch(token)
    if numeric:
        n = int(numeric.group(1))
        return "XXL" if n == 2 else f"{n}XL"
    repeated = _REPEATED_XL.fullmatch(token)
    if repeated:
        n = len(repeated.group(1))
        return "XXL" if n == 2 else f"{n}XL"
    return None


def size_meaning(raw: str) -> str:
    """Explain import codes without forcing numeric sizes or ranges into a letter enum."""
    canonical = normalize_size(raw)
    if canonical:
        return "Free / one size" if canonical == "FREE" else f"Letter size: {canonical}"
    token = re.sub(r"\s+", "", raw).upper()
    if re.fullmatch(r"[1-9][0-9]", token):
        return f"Numeric clothing size: {token}"
    parts = token.split("TO")
    if len(parts) == 2:
        start, end = (normalize_size(p) for p in parts)
        if start and end and start != "FREE" and end != "FREE" and size_rank(start) <= size_rank(end):
            return f"Size range: {start} to {end}"
    return "Source-specific code — review required"


def size_rank(label: str) -> int:
    """Sort key: canonical order, unknown labels after every known size."""
    canonical = normalize_size(label)
    return CANONICAL_SIZES.index(canonical) if canonical else len(CANONICAL_SIZES)
