import importlib.util
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

from test_config import settings

# app.__init__ prepends the ML tree, which also owns a package named scripts.
_spec = importlib.util.spec_from_file_location("ai_eval_cli", Path(__file__).resolve().parents[2] / "scripts/eval_llm.py")
eval_llm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_llm)


async def test_eval_refuses_without_explicit_opt_in(monkeypatch):
    execute = AsyncMock()
    monkeypatch.setattr(eval_llm, "execute_probe", execute)
    assert await eval_llm.main([]) == 2
    execute.assert_not_awaited()


async def test_eval_requires_workspace_and_actor():
    assert await eval_llm.main(["--allow-live"]) == 2


def test_eval_has_one_call_and_small_token_caps():
    config = eval_llm.probe_settings(settings())
    assert config.llm_model == "deepseek-flash"
    assert config.llm_max_retries == 0
    assert config.llm_max_output_tokens <= 256
    assert config.llm_max_input_bytes <= 2048
    assert config.llm_daily_token_limit <= 4096


async def test_eval_honest_failure_status(monkeypatch):
    monkeypatch.setattr(eval_llm, "execute_probe", AsyncMock(return_value={"state": "disabled"}))
    code = await eval_llm.main(["--allow-live", "--workspace", str(uuid.uuid4()),
                                "--actor", str(uuid.uuid4()), "--industry", "fashion"])
    assert code != 0
