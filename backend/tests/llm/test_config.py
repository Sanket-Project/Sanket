import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings


def settings(**kwargs):
    return Settings(_env_file=None, jwt_secret="test-only-secret-please-never-use-in-prod", **kwargs)  # noqa: S106


async def test_network_guard():
    async with httpx.AsyncClient() as client:
        with pytest.raises(AssertionError, match="Unmocked model network"):
            await client.get("https://model-network-must-not-run.invalid")


def test_defaults(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config = settings()
    assert config.llm_base_url == "https://api.deepseek.com"
    assert config.llm_model == "deepseek-flash"
    assert config.deepseek_api_key is None
    secret = settings(deepseek_api_key="test-secret-must-be-hidden")
    assert "test-secret-must-be-hidden" not in repr(secret)
    assert "test-secret-must-be-hidden" not in secret.model_dump_json()


@pytest.mark.parametrize(("field", "value"), [
    ("llm_deadline_s", 0), ("llm_max_retries", 2), ("llm_cache_ttl_s", 0),
    ("llm_requests_per_minute", -1), ("llm_requests_per_day", 0),
    ("llm_daily_token_limit", 0), ("llm_max_input_bytes", 0),
    ("llm_max_output_tokens", 0), ("llm_max_response_bytes", 0),
    ("llm_breaker_failures", 0), ("llm_breaker_cooldown_s", 0),
    ("llm_base_url", "https://user:secret@example.test/v1"),
    ("llm_base_url", "file:///tmp/key"), ("llm_base_url", "https://example.test?key=secret"),
    ("llm_model", ""), ("llm_compatibility", "unsupported"),
])
def test_invalid_values(field, value):
    with pytest.raises(ValidationError):
        settings(**{field: value})


def test_operator_override():
    config = settings(llm_base_url="http://localhost:9000/v1/", llm_model="local-model",
                      llm_compatibility="openai_compatible")
    assert config.llm_base_url == "http://localhost:9000/v1"
    assert config.llm_model == "local-model"
