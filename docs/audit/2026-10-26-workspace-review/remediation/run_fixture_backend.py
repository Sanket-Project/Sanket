"""Run the backend against the isolated review fixture database only.

Sets the environment in-process (shell `set` chains proved unreliable under the
preview launcher, which silently fell back to backend/.env) and refuses to start
unless every stateful dependency points at isolated or disabled targets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"

ISOLATED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://sanket_app:changeme@localhost:5432/sanket_review_fixture",
    # Port 9 refuses connections: no ML service, Redis or third-party fetches.
    "ML_API_URL": "http://127.0.0.1:9",
    "REDIS_URL": "",
    "SIGNAL_PIPELINE_ENABLED": "false",
    "SHOPIFY_POLL_ENABLED": "false",
    "WHATSAPP_DIGEST_WORKER_ENABLED": "false",
    "WEBHOOK_RETRY_WORKER_ENABLED": "false",
}


def main() -> None:
    os.environ.update(ISOLATED_ENV)
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))

    from app.config import get_settings

    settings = get_settings()
    assert settings.database_url.endswith("/sanket_review_fixture"), settings.database_url
    assert not settings.redis_url, "Redis must be disabled for the fixture stack"
    assert not settings.signal_pipeline_enabled and not settings.shopify_poll_enabled
    assert not settings.webhook_retry_worker_enabled

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8010)


if __name__ == "__main__":
    main()
