from typing import Any

import httpx

from app.core.config import settings


class HetznerClient:
    def __init__(self, token: str):
        self.client = httpx.AsyncClient(
            base_url=settings.hetzner_base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

    async def list_servers(self) -> list[dict[str, Any]]:
        response = await self.client.get("/servers")
        response.raise_for_status()
        return response.json().get("servers", [])

    async def create_server(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.post("/servers", json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()
