from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int

Reason = Literal[
    "feature_disabled", "task_disabled", "sharing_disabled", "invalid_context",
    "configuration_missing", "invalid_input", "invalid_output", "provider_auth",
    "provider_error", "provider_busy", "timeout", "infrastructure_unavailable",
    "circuit_open", "request_limit", "token_limit", "accounting_unavailable",
    "policy_changed", "in_progress",
]


class AIError(Exception):
    """Only a fixed safe code may cross the provider/service boundary."""

    def __init__(self, code: Reason, *, transient: bool = False, retry_after: float = 0,
                 usage: TokenUsage | None = None):
        self.code = code
        self.transient = transient
        self.retry_after = retry_after
        self.usage = usage
        super().__init__(code)
