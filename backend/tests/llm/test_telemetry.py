import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.billing import MeterKind
from app.services import audit, usage


@pytest.mark.parametrize("service", ["audit", "usage"])
async def test_strict_recording(service):
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("recording failed")
    args = {"tenant_id": uuid.uuid4()}
    fn = audit.record
    if service == "audit":
        args.update(action="ai.test", entity_type="llm")
    else:
        fn = usage.record
        args.update(meter=MeterKind.api_request, quantity=1)
    await fn(session, **args)
    with pytest.raises(RuntimeError, match="recording failed"):
        await fn(session, strict=True, **args)
