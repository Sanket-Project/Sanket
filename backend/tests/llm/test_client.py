import json

import httpx
import pytest
from test_config import settings

from app.services.llm.client import ProviderClient
from app.services.llm.contracts import Column, TaskInput
from app.services.llm.errors import AIError

TASK = TaskInput(columns=[Column(id="c1", label="Qty")], allowed_fields=["quantity"])
OUTPUT = {"selections": [{"column_id": "c1", "field": "quantity", "confidence": "high"}]}


def envelope(**overrides):
    return {"model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps(OUTPUT), "reasoning_content": "must never be retained"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8}, **overrides}


async def invoke(handler, **config):
    client = ProviderClient(settings(**config), transport=httpx.MockTransport(handler))
    try:
        return await client.complete(TASK, TASK.model_dump(), system="Return json with supplied IDs only.")
    finally:
        await client.aclose()


async def test_exact_request():
    def handler(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        data = json.loads(request.content)
        assert data["model"] == "deepseek-flash"
        assert data["thinking"] == {"type": "disabled"}
        assert data["response_format"] == {"type": "json_object"}
        assert data["stream"] is False
        assert data["max_tokens"] == 4096
        assert "tools" not in data
        assert request.headers["authorization"] == "Bearer test-dummy-not-a-real-key"
        assert "test-dummy" not in request.content.decode()
        assert data["messages"][1]["role"] == "user"
        return httpx.Response(200, json=envelope())
    reply = await invoke(handler)
    assert reply.value.selections[0].field == "quantity"
    assert reply.usage.input_tokens == 12
    assert "must never" not in repr(reply)


async def test_operator_override_request():
    def handler(request):
        assert str(request.url) == "http://localhost:9000/v1/chat/completions"
        data = json.loads(request.content)
        assert data["model"] == "local-model"
        assert "thinking" not in data
        return httpx.Response(200, json=envelope())
    await invoke(handler, llm_base_url="http://localhost:9000/v1/", llm_model="local-model",
                 llm_compatibility="openai_compatible")


@pytest.mark.parametrize(("status", "code", "transient"), [
    (401, "provider_auth", False), (403, "provider_auth", False),
    (400, "provider_error", False), (302, "provider_error", False),
    (429, "provider_busy", True), (500, "provider_error", True), (503, "provider_error", True),
])
async def test_safe_failures(status, code, transient, capsys):
    with pytest.raises(AIError) as caught:
        await invoke(lambda r: httpx.Response(status, text="private customer and secret key",
                                             headers={"location": "https://other.invalid", "retry-after": "999999"}))
    assert caught.value.code == code
    assert caught.value.transient == transient
    assert caught.value.retry_after <= 2
    assert "private" not in str(caught.value)
    assert "private" not in capsys.readouterr().out


@pytest.mark.parametrize("data", [
    {}, {"choices": []}, envelope(choices=[{"finish_reason": "length", "message": {"content": "{}"}}]),
    envelope(choices=[{"finish_reason": "stop", "message": {"content": ""}}]),
    envelope(choices=[{"finish_reason": "stop", "message": {"content": "not json"}}]),
    envelope(choices=[{"finish_reason": "stop", "message": {"content": json.dumps(OUTPUT), "tool_calls": [{}]}}]),
])
async def test_invalid_responses(data):
    with pytest.raises(AIError, match="invalid_output"):
        await invoke(lambda r: httpx.Response(200, json=data))


async def test_missing_usage_is_unknown():
    reply = await invoke(lambda r: httpx.Response(200, json=envelope(usage=None)))
    assert reply.usage is None


async def test_invalid_output_keeps_actual_usage():
    with pytest.raises(AIError) as caught:
        await invoke(lambda r: httpx.Response(200, json=envelope(choices=[
            {"finish_reason": "length", "message": {"content": "partial"}}])))
    assert caught.value.usage.input_tokens == 12


async def test_response_limit():
    with pytest.raises(AIError, match="invalid_output"):
        await invoke(lambda r: httpx.Response(200, content=b"x" * 100), llm_max_response_bytes=50)


async def test_input_limit_before_network():
    called = []
    with pytest.raises(AIError, match="invalid_input"):
        await invoke(lambda r: called.append(r), llm_max_input_bytes=8)
    assert not called


@pytest.mark.parametrize(("error", "code"), [(httpx.ConnectError("private"), "provider_error"),
                                       (httpx.ReadTimeout("private"), "timeout")])
async def test_connection_failure(error, code):
    def fail(request):
        raise error
    with pytest.raises(AIError) as caught:
        await invoke(fail)
    assert caught.value.code == code
    assert caught.value.transient
