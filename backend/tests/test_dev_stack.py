import importlib.util
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "dev_stack", Path(__file__).resolve().parents[1] / "scripts/dev_stack.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
service_environment = module.service_environment
require_free_ports = module.require_free_ports


def test_services_share_database_and_ml_auth_without_exposing_public_signup():
    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://sanket_app:unit@localhost:5432/sanket",
        ml_service_token_effective="unit-service-token",  # noqa: S106 — synthetic unit-test secret
        redis_url="redis://localhost:6379/0",
    )
    env = service_environment(settings, api_port=8010, ml_port=8001)
    assert env["ML_DATABASE_URL"] == "postgresql://sanket_app:unit@localhost:5432/sanket"
    assert env["ML_DATABASE_ASYNC_URL"] == settings.database_url
    assert env["ML_SERVICE_TOKEN"] == "unit-service-token"
    assert env["ML_REQUIRE_AUTH"] == "true"
    assert env["PUBLIC_SIGNUP_ENABLED"] == "false"
    assert env["SANDBOX_ENABLED"] == "false"
    assert env["VITE_PROXY_TARGET"] == "http://127.0.0.1:8010"


def test_occupied_port_fails_before_starting_any_process():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match=str(port)):
            require_free_ports([port])


def test_root_launcher_uses_uv_coordinator_instead_of_unchecked_windows():
    script = (Path(__file__).resolve().parents[2] / "scripts/start-dev.bat").read_text()
    assert "scripts.dev_stack" in script
    assert "uv run" in script


@pytest.mark.asyncio
async def test_unreadable_migration_state_is_not_ready():
    from app.core.database import Database

    db = object.__new__(Database)

    class BrokenEngine:
        def connect(self):
            raise RuntimeError("alembic_version missing")

    db._engine = BrokenEngine()
    assert await db.check_migration_version() is False


def test_ready_launcher_opens_the_local_sign_in_page(monkeypatch):
    calls = []
    monkeypatch.setattr("webbrowser.open", lambda url: calls.append(url))
    module.open_local_app(5173)
    assert calls == ["http://127.0.0.1:5173/"]
