"""Migration credentials are scoped to one subprocess, never the whole session."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace


async def test_schema_setup_scopes_both_database_urls(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location("ai_test_root_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture_url = "postgresql+asyncpg://fixture:fixture@127.0.0.1:9/test-only"
    previous_url = "postgresql+asyncpg://other:other@127.0.0.1:9/not-the-test-database"
    monkeypatch.setenv("DATABASE_URL", fixture_url)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", previous_url)
    observed = []

    def run(*args, **kwargs):
        observed.append(kwargs["env"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", run)
    await module.setup_schema.__wrapped__(None)
    assert observed[0]["MIGRATION_DATABASE_URL"] == fixture_url
    import os
    assert os.environ["MIGRATION_DATABASE_URL"] == previous_url
