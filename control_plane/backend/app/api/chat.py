import time
import uuid

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import User
from app.services.dispatcher import proxy_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = structlog.get_logger("llamagrid.chat")


@router.post("/completions")
async def chat_completions(request: Request, _: User = Depends(get_current_user)) -> StreamingResponse:
    body = await request.json()
    body.setdefault("model", settings.public_model_id)
    headers, stream = await proxy_chat(body)
    request_id = f"cp-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()

    async def logged_stream():
        try:
            async for chunk in stream:
                yield chunk
        finally:
            logger.info("chat_request", request_id=request_id, latency_ms=round((time.perf_counter() - started) * 1000, 2))

    status_code = 502 if headers.get("x-error") else 200
    return StreamingResponse(logged_stream(), status_code=status_code, headers={k: v for k, v in headers.items() if k != "x-error"}, media_type=None)
