"""Generate and download Firebase Service Account Credentials JSON.

Uses the local Firebase CLI's OAuth2 refresh token to authenticate, calls the
Google Cloud IAM REST API to generate a new private key for the Admin SDK service
account, decodes it, and writes it locally.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx
import structlog

log = structlog.get_logger(__name__)

# Firebase CLI "installed application" OAuth client. Per RFC 8252 §8.5 a native
# app's client secret is NOT confidential — this is the well-known public client
# shipped in the open-source firebase-tools package, not a private credential.
# It is still sourced from the environment (with the published default) so no
# secret-shaped literal lives in the repo and operators can override it.
CLIENT_ID = os.environ.get(
    "FIREBASE_CLI_CLIENT_ID",
    "563584335869-fgrhgmd47bqnekij5i8b5pr03ho849e6.apps.googleusercontent.com",
)
CLIENT_SECRET = os.environ["FIREBASE_CLI_CLIENT_SECRET"]
# B105 false positive: bandit matches the "token" substring in the name; this is
# Google's public OAuth2 token *endpoint URL*, not a credential.
TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105


def get_gcp_access_token() -> str:
    """Retrieve and refresh access token from the local Firebase CLI configuration."""
    config_path = Path(os.path.expanduser("~/.config/configstore/firebase-tools.json"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Firebase CLI config not found at {config_path}. Please run 'firebase login' first."
        )

    with open(config_path, encoding="utf-8") as f:
        config_data = json.load(f)

    tokens = config_data.get("tokens", {})
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise ValueError("No refresh token found in Firebase CLI config.")

    log.info(
        "firebase_credentials.refreshing_token", email=config_data.get("user", {}).get("email")
    )

    # Refresh OAuth token
    r = httpx.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def generate_service_account_key(project_id: str, sa_email: str, output_path: Path) -> None:
    """Request a new private key for the service account via GCP IAM API and save it."""
    access_token = get_gcp_access_token()

    url = f"https://iam.googleapis.com/v1/projects/{project_id}/serviceAccounts/{sa_email}/keys"
    log.info("firebase_credentials.requesting_key", project_id=project_id, service_account=sa_email)

    r = httpx.post(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15.0,
    )
    r.raise_for_status()

    key_data_b64 = r.json()["privateKeyData"]
    key_bytes = base64.b64decode(key_data_b64)
    key_json = json.loads(key_bytes.decode("utf-8"))

    # Write to destination file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(key_json, f, indent=2)

    log.info("firebase_credentials.key_saved", path=str(output_path))


def main() -> None:
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if not project_id:
        raise SystemExit(
            "FIREBASE_PROJECT_ID is not set. Set it to your Firebase project ID "
            "(e.g. export FIREBASE_PROJECT_ID=sanket-live-xxxx) before running this script."
        )
    sa_email = f"firebase-adminsdk-fbsvc@{project_id}.iam.gserviceaccount.com"

    # Resolve backend root path
    backend_dir = Path(__file__).resolve().parents[2]
    output_path = backend_dir / "firebase-credentials.json"

    try:
        generate_service_account_key(project_id, sa_email, output_path)
        print(
            f"\n[SUCCESS] Successfully generated service-account key and saved to: {output_path}\n"
        )
    except Exception as e:
        log.error("firebase_credentials.failed", error=str(e))
        print(f"\n[ERROR] Failed to generate service-account key: {e}\n")
        raise e


if __name__ == "__main__":
    main()
