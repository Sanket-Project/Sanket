"""Supervised local stack; owns only its child processes, never existing data."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def tie_services_to_launcher() -> None:
    """Make every process started from here die with this launcher, however it ends.

    Windows keeps children running when their parent dies, and closing the console
    window ends this process without running ``finally`` — which left the services
    holding their ports. A kill-on-close job object covers that, and Task Manager too.
    """
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("per_process_user_time", ctypes.c_int64),
            ("per_job_user_time", ctypes.c_int64),
            ("limit_flags", wintypes.DWORD),
            ("minimum_working_set", ctypes.c_size_t),
            ("maximum_working_set", ctypes.c_size_t),
            ("active_process_limit", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority_class", wintypes.DWORD),
            ("scheduling_class", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimits),
            ("io_counters", ctypes.c_uint64 * 6),
            ("process_memory_limit", ctypes.c_size_t),
            ("job_memory_limit", ctypes.c_size_t),
            ("peak_process_memory", ctypes.c_size_t),
            ("peak_job_memory", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    limits = ExtendedLimits()
    # Kill on close; breakaway is allowed only for start_outside_launcher.
    limits.basic.limit_flags = 0x2000 | 0x800
    job = kernel32.CreateJobObjectW(None, None)
    if not (
        job
        and kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        and kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
    ):
        print(
            f"Warning: services will outlive this window (Windows error {ctypes.get_last_error()}). "
            "Stop them with Ctrl+C or scripts\\stop-dev.bat.",
            file=sys.stderr,
        )
    # The job handle stays open on purpose; Windows closes it when this process ends.


def start_outside_launcher(command: list[str]) -> subprocess.Popen:
    """Start a process that must outlive the launcher, such as the user's browser."""
    flags = (
        subprocess.CREATE_BREAKAWAY_FROM_JOB | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    )
    return subprocess.Popen(command, creationflags=flags)  # noqa: S603 — fixed local argv


def open_local_app(port: int) -> None:
    url = f"http://127.0.0.1:{port}/"
    if os.name != "nt":
        webbrowser.open(url)
        return
    try:
        # A browser launched from inside the job would close along with the launcher.
        start_outside_launcher(["cmd.exe", "/d", "/c", "start", "", url])
    except OSError:
        webbrowser.open(url)


def require_free_ports(ports: list[int]) -> None:
    for port in ports:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(
                    f"Port {port} is occupied. If SANKET is already running, use that window or run "
                    "scripts\\stop-dev.bat; otherwise stop the port's owner or select another port. "
                    "No process was killed."
                ) from exc


def service_environment(settings, *, api_port: int, ml_port: int) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "DATABASE_URL": settings.database_url,
            "ML_DATABASE_URL": settings.database_url.replace(
                "postgresql+asyncpg://", "postgresql://"
            ),
            "ML_DATABASE_ASYNC_URL": settings.database_url,
            "ML_API_URL": f"http://127.0.0.1:{ml_port}",
            "ML_SERVICE_TOKEN": settings.ml_service_token_effective,
            "ML_REQUIRE_AUTH": "true",
            "ML_DEVICE": "cpu",
            "ML_CHRONOS_REPO": "amazon/chronos-t5-small",
            "MLFLOW_ALLOW_FILE_STORE": "true",
            "PUBLIC_SIGNUP_ENABLED": "false",
            "SANDBOX_ENABLED": "false",
            "REDIS_URL": settings.redis_url or "redis://127.0.0.1:6379/0",
            "VITE_API_BASE_URL": "/api/v1",
            "VITE_PROXY_TARGET": f"http://127.0.0.1:{api_port}",
            "VITE_WS_BASE_URL": f"ws://127.0.0.1:{api_port}",
            "SIGNAL_PIPELINE_ENABLED": "false",
            "SHOPIFY_POLL_ENABLED": "false",
            "WHATSAPP_DIGEST_WORKER_ENABLED": "false",
        }
    )
    return env


def wait_ready(url: str, process: subprocess.Popen, seconds: int = 180) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited before {url} became ready. See tmp/dev-stack logs.")
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Readiness timed out: {url}. See tmp/dev-stack logs.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8010)
    parser.add_argument("--ml-port", type=int, default=8001)
    parser.add_argument("--web-port", type=int, default=5173)
    parser.add_argument("--open-browser", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    children = []
    handles = []
    try:
        tie_services_to_launcher()
        from app.config import get_settings

        settings = get_settings()
        if settings.is_production:
            raise RuntimeError(
                "This is a local development launcher. Use the production deployment runbook for production."
            )
        require_free_ports([args.api_port, args.ml_port, args.web_port])
        ml_python = (
            ROOT / "backend/ml/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        if not ml_python.exists():
            raise RuntimeError(
                "ML runtime missing. Install backend/ml dependencies in its .venv first."
            )
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm or not (ROOT / "frontend/node_modules").exists():
            raise RuntimeError("Frontend dependencies missing. Run npm ci in frontend first.")
        docker = shutil.which("docker")
        if not docker:
            raise RuntimeError(
                "Docker is not installed. Install/start Docker Desktop before retrying."
            )
        if subprocess.run([docker, "info"], capture_output=True).returncode:  # noqa: S603 — installed executable, fixed arguments
            raise RuntimeError(
                "Docker engine is unavailable. Start Docker Desktop, wait until ready, and retry."
            )
        subprocess.run(  # noqa: S603 — installed Docker, fixed local infrastructure services
            [docker, "compose", "up", "-d", "--wait", "postgres", "redis"], cwd=ROOT, check=True
        )
        env = service_environment(settings, api_port=args.api_port, ml_port=args.ml_port)

        async def verify_database():
            from app.core.database import Database

            db = Database(settings)
            try:
                if not await db.healthcheck() or not await db.check_migration_version():
                    raise RuntimeError(
                        "Database is unavailable or migrations are incomplete. Back up data, then run Alembic with MIGRATION_DATABASE_URL before restarting."
                    )
                await db.assert_tenant_isolation_enforced(strict=True)
            finally:
                await db.close()

        asyncio.run(verify_database())
        log_dir = ROOT / "tmp/dev-stack"
        log_dir.mkdir(parents=True, exist_ok=True)
        specs = [
            (
                "backend",
                ROOT / "backend",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.api_port),
                ],
                f"http://127.0.0.1:{args.api_port}/health",
            ),
            (
                "ml",
                ROOT / "backend/ml",
                [
                    str(ml_python),
                    "-m",
                    "uvicorn",
                    "sanket_ml.inference.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.ml_port),
                ],
                f"http://127.0.0.1:{args.ml_port}/health",
            ),
            (
                "worker",
                ROOT / "backend",
                [sys.executable, "-m", "arq", "app.workers.forecast_worker.WorkerSettings"],
                None,
            ),
            (
                "frontend",
                ROOT / "frontend",
                [
                    npm,
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(args.web_port),
                    "--strictPort",
                ],
                f"http://127.0.0.1:{args.web_port}",
            ),
        ]
        for name, cwd, command, url in specs:
            handle = (log_dir / f"{name}.log").open("w", encoding="utf-8")
            handles.append(handle)
            child = subprocess.Popen(  # noqa: S603 — fixed local service argv; no shell/input commands
                command,
                cwd=cwd,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            children.append(child)
            if url:
                wait_ready(url, child)
            print(f"{name}: started", flush=True)
        print(
            f"SANKET local app: http://127.0.0.1:{args.web_port} | API :{args.api_port} | ML :{args.ml_port}\nKeep this process open. Ctrl+C stops its services. Logs: {log_dir}",
            flush=True,
        )
        if args.open_browser:
            open_local_app(args.web_port)
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError("A service stopped. See tmp/dev-stack logs.")
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(
            str(exc)
            if isinstance(exc, RuntimeError)
            else f"Startup failed ({type(exc).__name__}). Inspect local logs/configuration.",
            file=sys.stderr,
        )
        return 1
    finally:
        for child in reversed(children):
            if child.poll() is None:
                if os.name == "nt":
                    subprocess.run(  # noqa: S603 — only a child PID returned by Popen
                        [
                            str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                            "/PID",
                            str(child.pid),
                            "/T",
                            "/F",
                        ],
                        capture_output=True,
                    )
                else:
                    child.terminate()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
