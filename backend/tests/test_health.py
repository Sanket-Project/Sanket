"""The running build must be identifiable from outside.

Regression cover for the process failure behind docs/audit/03 liability 4:
two rounds of payment fixes were reviewed and signed off as shipped while the
running backend predated all of them. Nothing the reviewer could query would
have contradicted that. `git_sha` is what makes the claim falsifiable, so it
is tested like any other contract.
"""

from __future__ import annotations

import pytest

from app.config import Settings


@pytest.mark.asyncio
async def test_health_reports_the_build_it_is_running(client):
    """/health must be answerable without a token — deploy smoke tests have none."""
    r = await client.get("/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "git_sha" in body, "/health must expose the commit it was built from"
    assert isinstance(body["git_sha"], str)
    assert body["git_sha"], "git_sha must never be empty — use 'unknown' instead"


@pytest.mark.asyncio
async def test_api_health_is_authenticated_despite_its_docstring(client):
    """`/api/v1/health` sits behind the auth middleware like everything under /api/v1.

    Its docstring calls it an endpoint "for external smoke testing", which it
    is not — an unauthenticated caller gets 401. Pinning the real behaviour so
    the discrepancy is visible rather than discovered during an incident. The
    SPA reads this variant (through the Vite proxy, with a token); external
    smoke tests must use `/health`.
    """
    r = await client.get("/api/v1/health")

    assert r.status_code == 401


def test_git_sha_defaults_to_unknown_not_to_a_plausible_looking_value():
    """An unset GIT_SHA must be obviously absent, never mistakable for a real commit.

    A default like "0000000" or "" would render in the UI as though provenance
    were known. "unknown" is the honest answer and the frontend styles it as a
    warning.
    """
    assert Settings(git_sha="unknown").git_sha == "unknown"
    assert Settings().git_sha == "unknown"
