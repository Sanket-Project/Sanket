"""Secrets preflight audit — run before any deploy (and in CI).

Loads the effective settings and reports weak/default/missing secrets. Exits
non-zero if any CRITICAL finding is present so a pipeline can block the deploy.

    python -m app.scripts.audit_secrets            # audit current env
    APP_ENV=production python -m app.scripts.audit_secrets

This complements the fail-closed validators in app.config: those abort the app
at startup in production; this gives operators a readable report (and works for
staging/dev where the validators only warn) without booting the whole app.
"""

from __future__ import annotations

import sys

from app.config import _WEAK_JWT_SECRETS, get_settings

CRITICAL = "CRITICAL"
WARN = "WARN"
OK = "OK"


def audit() -> list[tuple[str, str, str]]:
    """Return (severity, check, detail) rows."""
    s = get_settings()
    prod = s.is_production
    rows: list[tuple[str, str, str]] = []

    def add(cond_bad: bool, name: str, detail: str, sev_if_bad: str) -> None:
        rows.append((sev_if_bad if cond_bad else OK, name, detail if cond_bad else "ok"))

    add(s.jwt_secret in _WEAK_JWT_SECRETS, "JWT_SECRET", "known-weak/default value", CRITICAL)
    add(len(s.jwt_secret) < 48, "JWT_SECRET length", "shorter than 48 chars (prefer 64)", WARN)
    add(":changeme@" in s.database_url, "DATABASE_URL", "default 'changeme' password", CRITICAL)
    add(
        s.metrics_enabled and not s.metrics_token,
        "METRICS_TOKEN",
        "unset while metrics enabled",
        CRITICAL if prod else WARN,
    )
    add(
        not s.ml_service_token,
        "ML_SERVICE_TOKEN",
        "unset — falls back to JWT_SECRET (no separation of duties)",
        CRITICAL if prod else WARN,
    )
    add(
        not s.integration_encryption_key,
        "INTEGRATION_ENCRYPTION_KEY",
        "unset — derives key from JWT_SECRET",
        CRITICAL if prod else WARN,
    )
    add(
        prod and not s.firebase_enabled,
        "FIREBASE",
        "not configured in production (dev-login fallback would be disabled)",
        CRITICAL,
    )
    add(
        not s.firebase_check_revoked,
        "FIREBASE_CHECK_REVOKED",
        "token revocation checks are disabled",
        WARN,
    )
    return rows


def main() -> int:
    rows = audit()
    width = max(len(name) for _, name, _ in rows)
    criticals = 0
    print(f"Secrets audit (APP_ENV={get_settings().app_env})\n" + "-" * 60)
    for sev, name, detail in rows:
        if sev == CRITICAL:
            criticals += 1
        marker = {OK: "  ", WARN: "! ", CRITICAL: "X "}[sev]
        print(f"{marker}{sev:<8} {name:<{width}}  {detail}")
    print("-" * 60)
    if criticals:
        print(f"FAILED: {criticals} critical finding(s). Fix before deploying.")
        return 1
    print("PASSED: no critical findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
