import importlib.util
import os
import signal
import socket
import subprocess
import sys
import time
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
REPO = Path(__file__).resolve().parents[2]

# A stand-in service: holds a port and records "<pid> <port>" in argv[1].
LISTENER = (
    "import os, socket, sys, time\n"
    "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen()\n"
    "open(sys.argv[1], 'w').write(f'{os.getpid()} {s.getsockname()[1]}')\n"
    "time.sleep(120)\n"
)

# A stand-in launcher: starts one service the way main() does and one process
# the way the browser is opened, then waits to be killed.
LAUNCHER = """
import importlib.util, os, subprocess, sys, time
spec = importlib.util.spec_from_file_location("dev_stack", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.tie_services_to_launcher()
listener, out = sys.argv[2], sys.argv[3]
subprocess.Popen([sys.executable, "-c", listener, out + "/service"], creationflags=subprocess.CREATE_NO_WINDOW)
module.start_outside_launcher([sys.executable, "-c", listener, out + "/outside"])
print(os.getpid(), flush=True)
time.sleep(120)
"""


def _wait_for_listener(record: Path) -> tuple[int, int]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if record.exists() and (text := record.read_text()):
            pid, port = text.split()
            return int(pid), int(port)
        time.sleep(0.1)
    raise AssertionError(f"{record.name} listener never started")


def _port_frees(port: int, seconds: float = 10) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            require_free_ports([port])
            return True
        except RuntimeError:
            time.sleep(0.2)
    return False


@pytest.fixture
def killed_launcher(tmp_path):
    """Kill a launcher the way a closed console window does: no ``finally`` runs."""
    script = tmp_path / "launcher.py"
    script.write_text(LAUNCHER)
    launcher = subprocess.Popen(  # noqa: S603 — this interpreter running a test script
        [sys.executable, str(script), spec.origin, LISTENER, str(tmp_path)],
        stdout=subprocess.PIPE,
        text=True,
    )
    launcher_pid = int(launcher.stdout.readline())
    service = _wait_for_listener(tmp_path / "service")
    outside = _wait_for_listener(tmp_path / "outside")
    os.kill(launcher_pid, signal.SIGTERM)  # TerminateProcess on Windows
    launcher.wait(10)
    yield service, outside
    for pid, _ in (service, outside):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


@pytest.mark.skipif(os.name != "nt", reason="Windows does not stop orphaned children")
def test_services_stop_when_the_launcher_window_is_closed(killed_launcher):
    (_, service_port), _ = killed_launcher
    assert _port_frees(service_port), "a service kept its port after its launcher died"


@pytest.mark.skipif(os.name != "nt", reason="Windows does not stop orphaned children")
def test_browser_opened_by_the_launcher_outlives_it(killed_launcher):
    (_, service_port), (_, outside_port) = killed_launcher
    assert _port_frees(service_port)
    with pytest.raises(RuntimeError):
        require_free_ports([outside_port])


def test_double_clicked_launcher_keeps_a_failure_on_screen():
    script = (REPO / "Start_SANKET.bat").read_text().lower()
    assert "if errorlevel 1 pause" in script


def test_stop_script_stops_the_supervised_launcher():
    script = (REPO / "scripts/stop-dev.bat").read_text()
    assert "scripts.dev_stack" in script
    assert "WINDOWTITLE" not in script


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
    monkeypatch.setattr(module, "start_outside_launcher", lambda command: calls.append(command[-1]))
    module.open_local_app(5173)
    assert calls == ["http://127.0.0.1:5173/"]
