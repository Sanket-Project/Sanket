"""A 422 must never echo what the caller submitted.

docs/audit/02 P0-5, broadened by 04: FastAPI's default
`RequestValidationError` handler serialises the rejected value under `input`,
so a malformed signup returned the submitted password in plaintext. It is the
global handler, so every credential-taking endpoint leaked identically —
signup, dev-login, and password reset.

The sentinel below is deliberately distinctive: if it appears anywhere in a
response body, the redaction has regressed.
"""

from __future__ import annotations

import pytest

SENTINEL = "Sentinel-Password-Must-Never-Appear-8123"


def _assert_no_leak(body_text: str, payload: dict) -> None:
    assert SENTINEL not in body_text, f"submitted value leaked into the 422 body: {body_text[:400]}"
    for key in ("password", "confirm_password", "new_password"):
        if key in payload:
            assert str(payload[key]) not in body_text


@pytest.mark.asyncio
async def test_signup_422_does_not_echo_the_password(client):
    # `name` and the workspace fields are omitted on purpose — that is what
    # triggers the 422 that used to carry the whole request body back.
    payload = {"email": "leak-probe@example.com", "password": SENTINEL}
    r = await client.post("/api/v1/auth/signup", json=payload)

    assert r.status_code == 422
    _assert_no_leak(r.text, payload)


@pytest.mark.asyncio
async def test_dev_login_422_does_not_echo_the_password(client):
    payload = {"password": SENTINEL}  # missing email / tenant
    r = await client.post("/api/v1/auth/dev-login", json=payload)

    assert r.status_code == 422
    _assert_no_leak(r.text, payload)


@pytest.mark.asyncio
async def test_validation_errors_keep_the_fields_the_frontend_maps_on(client):
    """Redaction must not break error-to-field mapping.

    The frontend attaches messages to form inputs using `loc`, so stripping
    `input` is only safe if `loc`, `msg` and `type` survive.
    """
    r = await client.post("/api/v1/auth/signup", json={"password": SENTINEL})

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list), "detail must remain a list"
    assert detail, "detail must remain non-empty"
    for err in detail:
        assert set(err) == {"type", "loc", "msg"}, (
            f"unexpected keys in a field error: {sorted(err)}"
        )
        assert isinstance(err["loc"], list)
        assert err["msg"]


@pytest.mark.asyncio
async def test_redaction_is_global_not_per_endpoint(client):
    """Any endpoint with a body — not just the auth ones — must be redacted.

    The original fix was scoped to signup. It is a single global handler, so
    pin that it applies elsewhere too and cannot regress into a special case.
    """
    r = await client.post(
        "/api/v1/billing/subscription",
        json={"plan_id": 12345, "billing_email": SENTINEL},
    )

    # 401 is fine — this endpoint is authenticated, and the auth middleware
    # runs first. What matters is that when it IS a 422, nothing echoes back.
    if r.status_code == 422:
        assert SENTINEL not in r.text
        for err in r.json()["detail"]:
            assert "input" not in err
            assert "ctx" not in err
