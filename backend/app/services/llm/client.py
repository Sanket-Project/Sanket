from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.services.llm.contracts import MappingOutput, TaskInput, validate_output
from app.services.llm.errors import AIError, TokenUsage
from app.services.llm.tasks import as_request


@dataclass(frozen=True)
class ProviderReply:
    value: MappingOutput
    usage: TokenUsage | None


def _usage(raw) -> TokenUsage | None:
    if not isinstance(raw, dict):
        return None
    values = [raw.get("prompt_tokens"), raw.get("completion_tokens")]
    if all(type(value) is int and 0 <= value <= 100000000 for value in values):
        return TokenUsage(*values)
    return None


class ProviderClient:
    """One bounded dispatch. Retry/accounting belongs to the workspace orchestrator."""

    def __init__(self, settings: Settings, *, transport=None):
        self.settings = settings
        self.http = httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False,
                                     timeout=settings.llm_deadline_s)

    async def aclose(self):
        await self.http.aclose()

    async def complete(self, task: TaskInput, payload: dict, *, system: str,
                       timeout_s: float | None = None) -> ProviderReply:
        settings = self.settings
        if settings.deepseek_api_key is None or not settings.deepseek_api_key.get_secret_value().strip():
            raise AIError("configuration_missing")
        body = {"model": settings.llm_model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                "stream": False, "response_format": {"type": "json_object"},
                "max_tokens": settings.llm_max_output_tokens}
        if settings.llm_compatibility == "deepseek":
            body["thinking"] = {"type": "disabled"}
        content = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if len(content) > settings.llm_max_input_bytes:
            raise AIError("invalid_input")
        headers = {"Authorization": f"Bearer {settings.deepseek_api_key.get_secret_value()}",
                   "Content-Type": "application/json"}
        usage = None
        try:
            async with self.http.stream("POST", settings.llm_base_url + "/chat/completions",
                                        content=content, headers=headers,
                                        timeout=timeout_s or settings.llm_deadline_s) as response:
                if response.status_code != 200:
                    status = response.status_code
                    code = "provider_auth" if status in {401, 403} else "provider_busy" if status == 429 else "provider_error"
                    try:
                        retry_after = min(2.0, max(0.0, float(response.headers.get("retry-after", "0"))))
                    except ValueError:
                        retry_after = 0.0
                    raise AIError(code, transient=status == 429 or status >= 500, retry_after=retry_after)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > settings.llm_max_response_bytes:
                        raise AIError("invalid_output")
                    data.extend(chunk)
            raw = json.loads(data)
            usage = _usage(raw.get("usage"))
            choices = raw["choices"]
            if len(choices) != 1:
                raise ValueError("Unexpected choice count")
            choice = choices[0]
            message = choice["message"]
            if choice["finish_reason"] != "stop" or message.get("tool_calls") or message.get("function_call"):
                raise ValueError("Incomplete result or unexpected action")
            output = as_request(task).validate(message["content"])
            return ProviderReply(output, usage)
        except AIError as exc:
            if usage is not None:
                exc.usage = usage
            raise
        except httpx.TimeoutException:
            raise AIError("timeout", transient=True) from None
        except httpx.TransportError:
            raise AIError("provider_error", transient=True) from None
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            raise AIError("invalid_output", usage=usage) from None
