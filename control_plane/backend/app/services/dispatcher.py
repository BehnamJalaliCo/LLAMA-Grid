from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.dispatcher_api_key:
        headers["Authorization"] = f"Bearer {settings.dispatcher_api_key}"
    return headers


async def proxy_openai(path: str, body: dict[str, Any]) -> tuple[dict[str, str], AsyncIterator[bytes]]:
    client = httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=10.0))
    request = client.build_request(
        "POST", f"{settings.dispatcher_url}{path}", json=body, headers=_headers()
    )
    response = await client.send(request, stream=True)

    async def stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_raw():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    headers = {"content-type": response.headers.get("content-type", "application/json")}
    if "text/event-stream" in headers["content-type"]:
        headers.update({"cache-control": "no-cache", "x-accel-buffering": "no"})
    if response.status_code >= 400:
        body_bytes = await response.aread()
        await response.aclose()
        await client.aclose()
        return {"content-type": response.headers.get("content-type", "application/json"), "x-error": "1"}, _one(body_bytes)
    return headers, stream()


async def proxy_chat(body: dict[str, Any]) -> tuple[dict[str, str], AsyncIterator[bytes]]:
    return await proxy_openai("/v1/chat/completions", body)


async def _one(value: bytes) -> AsyncIterator[bytes]:
    yield value
