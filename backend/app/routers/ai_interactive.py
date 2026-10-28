"""User-initiated read-only AI flows; gated with the same business entitlement."""
import asyncio
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IndustryCode
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.services.llm.errors import AIError
from app.services.llm.facts import Language
from app.services.llm.policy import AIContext

router = APIRouter(prefix="/ai", tags=["ai"])


class InteractiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=1500)
    language: Language = "en"


async def _until_disconnect(request, operation):
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return {"state": "cancelled", "blocks": []}
            await asyncio.wait({task}, timeout=0.1)
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def _run(feature, body, request, response, tenant_id, user_id, industry):
    from app.services.llm.interactive_service import answer, interpret
    response.headers["Cache-Control"] = "no-store"
    ctx = AIContext(tenant_id, user_id, IndustryCode(industry.code), feature)
    try:
        operation = interpret if feature == "scenario_interpretation" else answer
        return await _until_disconnect(request, operation(request, getattr(request.app.state, "ai", None), ctx, body.text, body.language))
    except AIError as exc:
        raise HTTPException(403 if exc.code == "invalid_context" else 400, exc.code) from None
    except ValueError:
        raise HTTPException(422, "Use explicit supported assumptions or a read-only workspace data question") from None
    except TimeoutError:
        return {"state": "unavailable", "reason": "timeout", "blocks": []}


@router.post("/scenarios/interpret")
async def interpret_scenario(body: InteractiveBody, request: Request, response: Response,
                             tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    return await _run("scenario_interpretation", body, request, response, tenant_id, user_id, industry)


@router.post("/data-qa")
async def data_qa(body: InteractiveBody, request: Request, response: Response,
                  tenant_id: TenantId, user_id: UserId, industry: ActiveIndustry):
    return await _run("data_qa_plan", body, request, response, tenant_id, user_id, industry)
