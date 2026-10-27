"""The production-style Compose API receives the selected model and private key."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def test_compose_passes_operator_ai_configuration(tmp_path):
    env_file = tmp_path / "fixture.env"
    env_file.write_text("POSTGRES_PASSWORD=fixture-only\nGRAFANA_PASSWORD=fixture-only\nJWT_SECRET=fixture-only-strong-secret-at-least-32-chars\n")
    env = dict(os.environ)
    env.update(LLM_MODEL="fixture-custom-flash", LLM_BASE_URL="http://fixture-model:9000/v1",
               DEEPSEEK_API_KEY="test-dummy-not-a-real-key")
    docker = shutil.which("docker")
    assert docker is not None, "Docker is required for deployment verification"
    proc = subprocess.run([docker, "compose", "--env-file", str(env_file), "config", "--format", "json"],  # noqa: S603 - fixed command, local test fixture
                          cwd=Path(__file__).resolve().parents[3], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, "Compose configuration did not render"
    environment = json.loads(proc.stdout)["services"]["backend"]["environment"]
    assert environment.get("LLM_MODEL") == "fixture-custom-flash"
    assert environment.get("LLM_BASE_URL") == "http://fixture-model:9000/v1"
    assert environment.get("DEEPSEEK_API_KEY") == "test-dummy-not-a-real-key"


def test_kubernetes_backend_reads_the_model_key_from_a_secret():
    import yaml
    manifest = Path(__file__).resolve().parents[3] / "infra" / "kubernetes" / "base" / "backend.yaml"
    docs = [d for d in yaml.safe_load_all(manifest.read_text(encoding="utf-8")) if d and d.get("kind") == "Deployment"]
    env = {e["name"]: e for c in docs[0]["spec"]["template"]["spec"]["containers"] for e in c.get("env", [])}
    ref = env["DEEPSEEK_API_KEY"]["valueFrom"]["secretKeyRef"]
    # Optional: AI stays off (and the pod still boots) until an operator adds the key.
    assert ref == {"name": "sanket-secrets", "key": "DEEPSEEK_API_KEY", "optional": True}
