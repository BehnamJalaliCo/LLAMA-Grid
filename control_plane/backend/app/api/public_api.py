import time
import uuid

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_public_api_key
from app.core.config import settings
from app.db.models import ApiKey, Model
from app.db.session import get_session
from app.services.dispatcher import proxy_openai

router = APIRouter(prefix="/v1", tags=["openai-compatible"])
logger = structlog.get_logger("llamagrid.public-api")


@router.get("/models")
async def public_models(_: ApiKey = Depends(get_public_api_key), session: AsyncSession = Depends(get_session)) -> dict:
    rows = list((await session.scalars(select(Model).where(Model.status.in_(["catalog", "deployed"])).order_by(Model.model_id))).all())
    return {"object": "list", "data": [{"id": row.model_id, "object": "model", "created": int(row.created_at.timestamp()) if row.created_at else 0, "owned_by": "llamagrid"} for row in rows]}


@router.post("/chat/completions")
async def public_chat(request: Request, _: ApiKey = Depends(get_public_api_key)) -> StreamingResponse:
    return await _proxy("/v1/chat/completions", request)


@router.post("/completions")
async def public_completions(request: Request, _: ApiKey = Depends(get_public_api_key)) -> StreamingResponse:
    return await _proxy("/v1/completions", request)


async def _proxy(path: str, request: Request) -> StreamingResponse:
    body = await request.json()
    body.setdefault("model", settings.public_model_id)
    headers, stream = await proxy_openai(path, body)
    request_id = f"public-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()

    async def logged_stream():
        try:
            async for chunk in stream:
                yield chunk
        finally:
            logger.info("public_api_request", request_id=request_id, path=path, latency_ms=round((time.perf_counter() - started) * 1000, 2))

    return StreamingResponse(logged_stream(), status_code=502 if headers.get("x-error") else 200, headers={k: v for k, v in headers.items() if k != "x-error"}, media_type=None)
