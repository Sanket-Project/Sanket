"""The synthetic E2E fixture must never point at a developer database."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "seed_remediation_fixture", Path(__file__).resolve().parents[1] / "scripts/seed_remediation_fixture.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
validate_target = module.validate_target


@pytest.mark.parametrize("url,port", [
    ("postgresql://sanket_app:x@localhost:55432/sanket", 55433),
    ("postgresql://postgres:x@localhost:55433/sanket", 55433),
    ("postgresql://sanket_app:x@remote:55433/sanket", 55433),
    ("postgresql://sanket_app:x@localhost:55432/sanket", 55432),
])
def test_refuses_other_database_or_privileged_role(url, port):
    with pytest.raises(ValueError):
        validate_target(url, port)


def test_accepts_explicit_isolated_application_connection():
    validate_target("postgresql://sanket_app:x@127.0.0.1:55433/sanket", 55433)
