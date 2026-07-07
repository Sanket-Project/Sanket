from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request

from app.models.demo_request import DemoRequest
from app.schemas.demo_request import DemoRequestCreate, DemoRequestOut

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/demo-requests", tags=["demo-requests"])


@router.post("", response_model=DemoRequestOut, status_code=201)
async def create_demo_request(
    body: DemoRequestCreate,
    request: Request,
) -> Any:
    db = request.app.state.db

    async with db.session_no_rls() as session:
        new_lead = DemoRequest(
            name=body.name,
            email=body.email,
            company=body.company,
            industry=body.industry,
            tier=body.tier,
            message=body.message,
        )
        session.add(new_lead)
        await session.flush()

    log.info("demo_request.created", lead_id=str(new_lead.id), email=new_lead.email)
    return new_lead
