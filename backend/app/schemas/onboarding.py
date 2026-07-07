"""Onboarding readiness state.

The state lives in ``Tenant.settings["onboarding"]`` (a JSONB column — no
dedicated table) and is surfaced to the SPA both on the session payload (so the
route guard resolves on first paint) and via the dedicated ``/onboarding/state``
endpoints used by the setup wizard.

Design note — legacy/demo tenants: tenants provisioned *before* this feature have
no ``onboarding`` key. We treat their absence as **implicitly complete** so they
are never forced back into setup. Only tenants created by ``/auth/signup`` (which
seeds :func:`default_onboarding_state`) start ``in_progress``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

OnboardingStatus = Literal["in_progress", "complete", "skipped"]

# Ordered wizard steps. ``done`` is the terminal pseudo-step.
StepKey = Literal["industry", "data", "calendar", "team", "baseline", "done"]
STEP_ORDER: tuple[StepKey, ...] = ("industry", "data", "calendar", "team", "baseline")


class StepState(BaseModel):
    """Per-step completion record. ``meta`` carries small step-specific facts
    (e.g. rows ingested, invites sent) for the resume UI — never bulk data."""

    done: bool = False
    at: datetime | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class OnboardingState(BaseModel):
    status: OnboardingStatus = "in_progress"
    current_step: StepKey = "industry"
    steps: dict[str, StepState] = Field(default_factory=dict)
    completed_at: datetime | None = None


class OnboardingStateUpdate(BaseModel):
    """Partial update from the wizard. All fields optional; omitted fields are
    left unchanged. Use ``mark_step`` to flip a single step to done."""

    status: OnboardingStatus | None = None
    current_step: StepKey | None = None
    mark_step: StepKey | None = None
    step_meta: dict[str, Any] | None = None


def default_onboarding_state() -> OnboardingState:
    """Fresh state for a brand-new tenant — seeded at signup."""
    return OnboardingState(
        status="in_progress",
        current_step="industry",
        steps={k: StepState() for k in STEP_ORDER},
    )


def _implicit_complete() -> OnboardingState:
    """State returned for tenants that predate onboarding (no settings key)."""
    return OnboardingState(status="complete", current_step="done", steps={})


def load_onboarding_state(settings: dict[str, Any] | None) -> OnboardingState:
    """Parse the onboarding state out of a tenant's ``settings`` dict.

    Absent key → :func:`_implicit_complete` (legacy/demo tenants are done).
    Malformed payload → also treated as complete rather than trapping a real
    tenant in a broken wizard.
    """
    if not settings or "onboarding" not in settings:
        return _implicit_complete()
    try:
        return OnboardingState.model_validate(settings["onboarding"])
    except Exception:  # noqa: BLE001 — never let bad state block a login
        return _implicit_complete()
