from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import IndustryCode
from app.schemas.onboarding import OnboardingState

# Reused by both signup paths. Required, with no default: a workspace whose
# industry was picked for it is the bug this replaces -- signup used to stamp
# every new tenant `fashion` and grant all five verticals alongside it.
_INDUSTRY_FIELD = Field(
    description=(
        "The workspace's single industry. Chosen once, when the workspace is "
        "created; every member inherits it, and it locks as soon as setup "
        "completes or real data arrives."
    )
)


class SessionInfo(BaseModel):
    """Identity + tenant context returned to the client after authentication.

    The bearer token itself is a Firebase ID token (prod) or a dev token
    (local); this payload only carries the non-secret session metadata the SPA
    needs to render.
    """

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    active_industry: str
    email: str
    full_name: str
    # Setup readiness — lets the SPA route a fresh tenant into the onboarding
    # wizard without a second round-trip. Absent for legacy/demo tenants
    # (treated as complete by the loader).
    onboarding: OnboardingState | None = None


class DevLoginRequest(BaseModel):
    """Local dev-fallback login (only available when Firebase is not configured)."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    tenant_slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")


class DevLoginResponse(SessionInfo):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SandboxSessionResponse(SessionInfo):
    """Server-side response for the public demo sandbox.

    Two shapes, distinguished by ``mode``:
    * ``dev``  — ``access_token`` is a short-lived dev identity token the SPA
      uses as a bearer directly (Firebase not configured).
    * ``firebase`` — ``custom_token`` is a Firebase custom token the SPA
      exchanges for an ID token via ``signInWithCustomToken``.

    No password is ever involved, so nothing secret reaches the browser.
    """

    mode: str  # "dev" | "firebase"
    access_token: str | None = None
    custom_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None


class FirebaseConfig(BaseModel):
    """Non-secret Firebase web config surfaced to the SPA (safe to expose)."""

    enabled: bool
    project_id: str | None = None
    api_key: str | None = None


class SignUpRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    tenant_slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
    industry: IndustryCode = _INDUSTRY_FIELD


class GoogleSignUpRequest(BaseModel):
    """Provision a new SANKET account for a Google-authenticated user.

    The caller must supply the Firebase ID token obtained from
    ``signInWithPopup`` / ``getIdToken`` so the backend can verify the Google
    identity without trusting a client-supplied email. No password is required
    or accepted — Firebase is the authenticator.
    """

    id_token: str = Field(description="Firebase ID token from signInWithPopup")
    workspace_slug: str = Field(
        min_length=2,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
        description="Desired workspace slug (unique across all tenants)",
    )
    name: str = Field(min_length=2, max_length=100, description="User's display name")
    industry: IndustryCode = _INDUSTRY_FIELD


class AcceptInviteRequest(BaseModel):
    """Redeem a one-time invite link.

    Deliberately accepts no workspace, no role and no industry. All three come
    from the invite record an owner or admin created; a client able to name its
    own role would be a plain privilege-escalation path, and one able to name
    its own industry would defeat the point of scoping a workspace at all.
    """

    token: str = Field(min_length=16, max_length=256)
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)
