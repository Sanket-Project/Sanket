"""Unit tests for the dev-fallback path of FirebaseVerifier.

These run without a Firebase project (firebase_enabled is False because no
FIREBASE_* env is set), exercising the local HS256 dev-token path.
"""
from __future__ import annotations

import os

import jwt
import pytest

from app.config import Settings
from app.core.firebase_auth import FirebaseVerifier, TokenVerificationError


def _settings() -> Settings:
    os.environ.setdefault("JWT_SECRET", "test-secret-min-32-chars-please-rotate-1234")
    return Settings()


def test_dev_mode_is_active_without_firebase() -> None:
    s = _settings()
    assert s.firebase_enabled is False


def test_mint_and_verify_roundtrip() -> None:
    v = FirebaseVerifier(_settings())
    token, expires_in = v.mint_dev_token(
        uid="u1", puid="11111111-1111-1111-1111-111111111111",
        email="a@b.com", tid="22222222-2222-2222-2222-222222222222",
        role="admin", ind="fashion",
    )
    assert expires_in > 0
    identity = v.verify(token)
    assert identity["uid"] == "u1"
    assert identity["puid"] == "11111111-1111-1111-1111-111111111111"
    assert identity["role"] == "admin"
    assert identity["ind"] == "fashion"


def test_token_carries_no_plural_industries_claim() -> None:
    """A workspace has one industry, so no plural claim can exist to be trusted.

    The claim was not merely redundant: the middleware authorized industry
    switching against it, and signup filled it with all five verticals, so it
    was the mechanism by which every tenant could reach every industry.
    """
    import base64
    import json

    v = FirebaseVerifier(_settings())
    token, _ = v.mint_dev_token(
        uid="u1", puid="p1", email="a@b.com", tid="t1", role="admin", ind="pharma",
    )
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))

    assert payload["ind"] == "pharma"
    assert "industries" not in payload
    assert "industries" not in v.verify(token)


def test_mint_dev_token_refuses_a_plural_industries_argument() -> None:
    """Callers that still pass the old argument must fail loudly, not silently."""
    v = FirebaseVerifier(_settings())
    with pytest.raises(TypeError):
        v.mint_dev_token(
            uid="u1", puid="p1", email=None, tid="t1", role="admin",
            ind="fashion", industries=["fashion", "pharma"],
        )


def test_an_unexpired_legacy_token_still_carrying_industries_is_ignored() -> None:
    """The real staleness case: a token minted *before* the claim was removed.

    Asserting that a freshly minted token lacks the claim proves nothing — it
    never had one. What matters is a token issued by the old code, still inside
    its lifetime, whose `industries: [all five]` was the very thing the old
    middleware authorized switching against. Verification must drop it.
    """
    from datetime import UTC, datetime, timedelta

    import jwt

    from app.core.firebase_auth import DEV_IDENTITY_MARKER

    settings = _settings()
    now = datetime.now(tz=UTC)
    legacy = jwt.encode(
        {
            "sub": "u1", "uid": "u1", "puid": "p1", "email": "a@b.com",
            "tid": "t1", "role": "admin", "ind": "fashion",
            # Minted by the old code path.
            "industries": ["fashion", "electronics", "pharma", "agrocenter", "hardware"],
            "iat": now,
            "exp": now + timedelta(minutes=30),
            DEV_IDENTITY_MARKER: True,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )

    identity = FirebaseVerifier(settings).verify(legacy)
    assert identity["ind"] == "fashion"
    assert "industries" not in identity, (
        "a legacy claim must not survive verification — the middleware used to "
        "authorize industry switching against exactly this list"
    )


def test_verify_rejects_tampered_token() -> None:
    v = FirebaseVerifier(_settings())
    token, _ = v.mint_dev_token(
        uid="u1", puid="p1", email=None, tid="t1", role="admin", ind="fashion",
    )
    with pytest.raises(TokenVerificationError):
        v.verify(token + "x")


def test_verify_rejects_token_signed_with_wrong_secret() -> None:
    v = FirebaseVerifier(_settings())
    forged = jwt.encode(
        {"sub": "u1", "uid": "u1", "puid": "p1", "tid": "t1", "role": "admin",
         "ind": "fashion", "iat": 0, "exp": 9999999999, "dev_identity": True},
        "a-different-secret-that-is-at-least-32-chars",
        algorithm="HS256",
    )
    with pytest.raises(TokenVerificationError):
        v.verify(forged)


def test_verify_requires_dev_marker() -> None:
    v = FirebaseVerifier(_settings())
    no_marker = jwt.encode(
        {"sub": "u1", "uid": "u1", "puid": "p1", "tid": "t1", "role": "admin",
         "ind": "fashion", "iat": 0, "exp": 9999999999},
        _settings().jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(TokenVerificationError):
        v.verify(no_marker)


def test_verify_requires_tenant_claims() -> None:
    v = FirebaseVerifier(_settings())
    missing = jwt.encode(
        {"sub": "u1", "uid": "u1", "iat": 0, "exp": 9999999999, "dev_identity": True},
        _settings().jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(TokenVerificationError):
        v.verify(missing)
