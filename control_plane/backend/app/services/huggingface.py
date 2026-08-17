from typing import Any

import httpx

from app.core.config import settings


async def search_models(query: str, limit: int = 20) -> list[dict[str, Any]]:
    params = {"search": query, "limit": min(max(limit, 1), 100), "full": "true"}
    async with httpx.AsyncClient(base_url=settings.huggingface_base_url, timeout=20) as client:
        response = await client.get("/api/models", params=params)
        response.raise_for_status()
        return response.json()
