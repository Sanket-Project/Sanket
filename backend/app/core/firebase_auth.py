"""Firebase Authentication — request-path token verification.

This module is the single authority for turning an inbound bearer token into a
trusted identity. It supports two modes, selected at runtime by whether real
Firebase credentials are configured (``settings.firebase_enabled``):

* **Firebase mode (prod/staging).** The bearer is a Firebase ID token signed by
  Google. We verify it with the Admin SDK (``verify_id_token``) which checks the
  signature against Google's rotating public keys, the audience/issuer, and
  expiry. Tenant/role/industry are read from the user's *custom claims*
  (``tid`` / ``role`` / ``ind``) set at provisioning time, so the hot path needs
  no database round-trip.

* **Dev-fallback mode (local).** No Firebase project required. The bearer is a
  short-lived HS256 token minted by ``POST /auth/dev-login`` and signed with
  ``settings.jwt_secret``. It carries the same claim shape as a verified Firebase
  token plus a ``dev_identity`` marker so it can never be confused with a real
  one. This keeps the full login → session → API flow working end-to-end before
  any Firebase setup.

The production fallback is fenced off in ``app.config`` (``require_firebase_in_
production``) so dev tokens can never be accepted in a production deployment.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import structlog

from app.config import Settings, get_settings

log = structlog.get_logger(__name__)
_admin_lock = threading.Lock()

# Bound the revocation cache so a flood of distinct uids can't grow it without
# limit. Evicted entries simply force a fresh revocation check.
_REVOCATION_CACHE_MAX = 50_000

# Marker claim that distinguishes a locally-minted dev token from a real
# Firebase ID token. Real Firebase tokens never contain this key.
DEV_IDENTITY_MARKER = "dev_identity"
_DEV_TOKEN_TTL_MINUTES_DEFAULT = 60


class TokenVerificationError(Exception):
    """Raised when a bearer token cannot be verified. Message is safe to log,
    never returned verbatim to the client."""


class NormalizedIdentity(dict):
    """A verified identity. Dict-like for convenience; required keys:
    ``uid`` (Firebase UID), ``puid`` (SANKET ``users.id``), ``tid``, ``role``,
    ``ind``. ``email`` and ``industries`` (list, used to authorize industry
    switching) are optional."""


class FirebaseVerifier:
    """Lazily-initialised verifier. Safe to import at module load — the
    firebase_admin SDK is only touched the first time a real token is verified.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._app: Any = None
        self._initialized = False
        # uid -> monotonic timestamp of the last successful revocation check.
        # Lets us honour `firebase_check_revoked` without a Firebase round-trip
        # on every request (we re-check at most once per cache TTL per user).
        self._revocation_checked_at: dict[str, float] = {}

    # ── Initialisation ───────────────────────────────────────────────────────
    def _ensure_admin(self) -> None:
        """Initialise the firebase_admin app exactly once (real mode only).

        Credential resolution order (first match wins):
          1. FIREBASE_CREDENTIALS_JSON env var — base64-encoded service-account JSON.
             Preferred for Cloud Run / Kubernetes where no filesystem path is stable.
             Generate: base64 -w0 firebase-credentials.json
          2. FIREBASE_CREDENTIALS_PATH — filesystem path (local dev only).
             Must be an absolute path that actually exists at runtime.
          3. Application Default Credentials — workload identity, gcloud auth, etc.
        """
        if self._initialized:
            return
        with _admin_lock:
            if self._initialized:
                return
            import base64
            import json
            import os

            import firebase_admin
            from firebase_admin import credentials

            if not firebase_admin._apps:
                project_id = self._settings.firebase_project_id
                cred: credentials.Base | None = None

                # Option 1: inline JSON via env var (production / Cloud Run preferred)
                creds_json_b64 = getattr(
                    self._settings, "firebase_credentials_json", None
                ) or os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
                if creds_json_b64:
                    try:
                        creds_dict = json.loads(base64.b64decode(creds_json_b64).decode("utf-8"))
                        cred = credentials.Certificate(creds_dict)
                        log.info(
                            "firebase_auth.init", method="credentials_json_env", project=project_id
                        )
                    except Exception as exc:
                        log.error("firebase_auth.init.credentials_json_failed", error=str(exc))
                        raise RuntimeError(
                            "FIREBASE_CREDENTIALS_JSON is set but could not be decoded"
                        ) from exc

                # Option 2: filesystem path (local dev only)
                if cred is None:
                    cred_path = self._settings.firebase_credentials_path
                    if cred_path:
                        if not os.path.isabs(cred_path):
                            log.warning(
                                "firebase_auth.init.relative_path",
                                path=cred_path,
                                note="FIREBASE_CREDENTIALS_PATH should be an absolute path",
                            )
                        if os.path.exists(cred_path):
                            cred = credentials.Certificate(cred_path)
                            log.info("firebase_auth.init", method="file_path", project=project_id)
                        else:
                            log.warning(
                                "firebase_auth.init.file_not_found",
                                path=cred_path,
                                note="FIREBASE_CREDENTIALS_PATH set but file does not exist; falling back to ADC",
                            )

                # Option 3: Application Default Credentials (workload identity, gcloud)
                if cred is None:
                    if project_id:
                        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                    log.info("firebase_auth.init", method="application_default", project=project_id)

                init_kwargs = {"projectId": project_id} if project_id else {}
                if cred is not None:
                    self._app = firebase_admin.initialize_app(cred, init_kwargs)
                else:
                    self._app = firebase_admin.initialize_app(options=init_kwargs)
            else:
                self._app = firebase_admin.get_app()
            self._initialized = True

    # ── Verification (hot path) ──────────────────────────────────────────────
    def verify(self, token: str) -> NormalizedIdentity:
        """Verify a bearer token and return a normalized identity.

        Used on the request hot path: requires the full set of tenant claims
        (``tid``/``role``/``ind``/``puid``). Raises ``TokenVerificationError``
        on any failure (expired, tampered, wrong signer, missing claims).
        """
        decoded = self._decode(token)
        source = "dev" if decoded.get(DEV_IDENTITY_MARKER) else "firebase"
        return self._normalize(decoded, source=source)

    def verify_identity(self, token: str) -> dict[str, Any]:
        """Verify signature/expiry only and return the raw decoded claims.

        Does NOT require tenant claims — used by ``POST /auth/session`` to
        bootstrap a freshly-created Firebase user before custom claims have
        propagated. Always contains ``uid`` and (usually) ``email``.
        """
        decoded = self._decode(token)
        decoded.setdefault("uid", decoded.get("sub"))
        return decoded

    def _decode(self, token: str) -> dict[str, Any]:
        # 1. Try dev token decode first if we are not in production
        if not self._settings.is_production:
            try:
                decoded = jwt.decode(
                    token,
                    self._settings.jwt_secret,
                    algorithms=["HS256"],
                    options={"require": ["sub", "exp", "iat"]},
                )
                if decoded.get(DEV_IDENTITY_MARKER):
                    return decoded
            except jwt.PyJWTError:
                pass  # Not a valid dev token, proceed to Firebase

        # 2. Real Firebase ID token verification
        if self._settings.firebase_enabled:
            self._ensure_admin()
            from firebase_admin import auth as fb_auth

            # Always verify signature + expiry (no network: public keys are
            # cached by firebase_admin). This also yields the uid so we can
            # consult the per-user revocation cache below.
            try:
                decoded = fb_auth.verify_id_token(token, check_revoked=False)
            except Exception as exc:  # firebase raises a variety of subclasses
                raise TokenVerificationError(f"firebase verify failed: {exc}") from exc

            # Revocation check (network: queries the user's tokensValidAfter).
            # Cached per-uid for `firebase_revocation_cache_ttl_s` so we don't
            # couple every request's latency to Firebase availability.
            if self._settings.firebase_check_revoked:
                self._check_revoked_cached(token, decoded, fb_auth)

            # A locally-minted dev token must never be accepted in real mode.
            if DEV_IDENTITY_MARKER in decoded:
                raise TokenVerificationError("dev token rejected in firebase mode")
            return decoded

        # 3. Fallback when Firebase is disabled and dev token failed to decode
        raise TokenVerificationError("Invalid token or dev fallback disabled")

    def _check_revoked_cached(self, token: str, decoded: dict[str, Any], fb_auth) -> None:
        """Enforce revocation, re-checking at most once per TTL per user.

        Raises ``TokenVerificationError`` if the token has been revoked (logout,
        password reset, admin disable). On a cache hit within the TTL we trust
        the prior result and skip the Firebase round-trip.
        """
        uid = decoded.get("uid") or decoded.get("sub")
        if not uid:
            return
        ttl = self._settings.firebase_revocation_cache_ttl_s
        now = time.monotonic()
        last = self._revocation_checked_at.get(uid)
        if ttl > 0 and last is not None and (now - last) < ttl:
            return  # within trust window — already verified not-revoked recently
        try:
            fb_auth.verify_id_token(token, check_revoked=True)
        except Exception as exc:
            # Drop any stale "ok" marker so the next request re-checks too.
            self._revocation_checked_at.pop(uid, None)
            raise TokenVerificationError(f"token revoked or invalid: {exc}") from exc
        if len(self._revocation_checked_at) >= _REVOCATION_CACHE_MAX:
            self._revocation_checked_at.clear()
        self._revocation_checked_at[uid] = now

    def invalidate_revocation_cache(self, uid: str) -> None:
        """Force the next request for ``uid`` to re-check revocation.

        Called right after we revoke a user's refresh tokens so the new state is
        enforced immediately rather than after the cache TTL elapses."""
        self._revocation_checked_at.pop(uid, None)

    @staticmethod
    def _normalize(decoded: dict[str, Any], *, source: str) -> NormalizedIdentity:
        uid = decoded.get("uid") or decoded.get("sub")
        puid = decoded.get("puid")
        tid = decoded.get("tid")
        role = decoded.get("role")
        ind = decoded.get("ind")
        if not (uid and puid and tid and role and ind):
            raise TokenVerificationError(
                "token missing required identity claims (uid/puid/tid/role/ind)"
            )
        identity = NormalizedIdentity(
            uid=str(uid),
            puid=str(puid),
            email=decoded.get("email"),
            tid=str(tid),
            role=str(role),
            ind=str(ind),
            source=source,
        )
        industries = decoded.get("industries")
        if isinstance(industries, list):
            identity["industries"] = [str(i) for i in industries]
        return identity

    # ── Dev-token minting (dev mode only) ────────────────────────────────────
    def mint_dev_token(
        self,
        *,
        uid: str,
        puid: str,
        email: str | None,
        tid: str,
        role: str,
        ind: str,
        industries: list[str] | None = None,
    ) -> tuple[str, int]:
        """Mint an HS256 dev identity token. Returns (token, expires_in_seconds).

        Only callable in dev-fallback mode; raises in Firebase mode so it can
        never be used as a backdoor in production.
        """
        if self._settings.is_production:
            raise RuntimeError("dev tokens are disabled in production")
        ttl_minutes = (
            self._settings.jwt_access_token_expire_minutes or _DEV_TOKEN_TTL_MINUTES_DEFAULT
        )
        now = datetime.now(tz=UTC)
        payload: dict[str, Any] = {
            "sub": uid,
            "uid": uid,
            "puid": puid,
            "email": email,
            "tid": tid,
            "role": role,
            "ind": ind,
            "iat": now,
            "exp": now + timedelta(minutes=ttl_minutes),
            DEV_IDENTITY_MARKER: True,
        }
        if industries:
            payload["industries"] = industries
        token = jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")
        return token, ttl_minutes * 60

    # ── Provisioning helpers (real mode only) ────────────────────────────────
    def set_user_claims(
        self,
        uid: str,
        *,
        puid: str,
        tid: str,
        role: str,
        ind: str,
        industries: list[str] | None = None,
    ) -> None:
        """Set custom claims on a Firebase user so future ID tokens carry the
        SANKET user id + tenant/role/industry without a DB lookup. No-op in dev
        mode."""
        if not self._settings.firebase_enabled:
            return
        self._ensure_admin()
        from firebase_admin import auth as fb_auth

        claims: dict[str, Any] = {"puid": puid, "tid": tid, "role": role, "ind": ind}
        if industries:
            claims["industries"] = industries
        fb_auth.set_custom_user_claims(uid, claims)

    def create_or_get_user(
        self,
        *,
        email: str,
        password: str | None,
        display_name: str | None = None,
        reset_password: bool = False,
    ) -> str:
        """Create (or fetch) a Firebase user by email; return its UID. Real mode
        only — raises in dev mode.

        If the user already exists and ``reset_password`` is True and a password
        is given, the existing user's password is overwritten. This is opt-in
        because silently resetting real users' passwords would be unsafe."""
        if not self._settings.firebase_enabled:
            raise RuntimeError("create_or_get_user requires Firebase to be configured")
        self._ensure_admin()
        from firebase_admin import auth as fb_auth

        try:
            existing = fb_auth.get_user_by_email(email)
            if reset_password and password:
                fb_auth.update_user(existing.uid, password=password)
            return existing.uid
        except fb_auth.UserNotFoundError:
            created = fb_auth.create_user(
                email=email,
                password=password,
                display_name=display_name,
                email_verified=False,
            )
            return created.uid

    def get_uid_by_email(self, email: str) -> str | None:
        """Return the Firebase UID for an email, or None if no such user. Real
        mode only — returns None in dev mode (no Firebase project)."""
        if not self._settings.firebase_enabled:
            return None
        self._ensure_admin()
        from firebase_admin import auth as fb_auth

        try:
            return fb_auth.get_user_by_email(email).uid
        except fb_auth.UserNotFoundError:
            return None

    def create_custom_token(self, uid: str, claims: dict[str, Any] | None = None) -> str:
        """Mint a Firebase custom token the SPA can exchange for a real ID token
        via ``signInWithCustomToken``. Used to start the public demo sandbox
        session without ever sending a password to the browser. Real mode only.
        """
        if not self._settings.firebase_enabled:
            raise RuntimeError("create_custom_token requires Firebase to be configured")
        self._ensure_admin()
        from firebase_admin import auth as fb_auth

        # firebase_admin returns the signed JWT as bytes.
        return fb_auth.create_custom_token(uid, developer_claims=claims).decode("utf-8")

    def revoke_refresh_tokens(self, uid: str) -> None:
        """Invalidate all of a user's refresh tokens (logout / lockout). No-op in
        dev mode since dev tokens are short-lived and stateless."""
        if not self._settings.firebase_enabled:
            return
        self._ensure_admin()
        from firebase_admin import auth as fb_auth

        fb_auth.revoke_refresh_tokens(uid)
        # Make the revocation take effect on the very next request rather than
        # after the revocation-cache TTL.
        self.invalidate_revocation_cache(uid)


# Module-level singleton. Construction is cheap (no SDK import); the admin SDK is
# only loaded on first real verification.
_verifier: FirebaseVerifier | None = None


def get_verifier() -> FirebaseVerifier:
    global _verifier
    if _verifier is None:
        _verifier = FirebaseVerifier()
    return _verifier
