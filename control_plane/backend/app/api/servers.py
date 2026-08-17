from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Server, User
from app.db.session import get_session
from app.schemas import ServerCreate, ServerOut

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("", response_model=list[ServerOut])
async def list_servers(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[Server]:
    return list((await session.scalars(select(Server).order_by(Server.name))).all())


@router.post("", response_model=ServerOut, status_code=201)
async def create_server(payload: ServerCreate, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Server:
    if await session.scalar(select(Server).where(Server.private_ip == payload.private_ip)):
        raise HTTPException(status_code=409, detail="A server with this private IP already exists")
    server = Server(**payload.model_dump(), status="pending")
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return server


@router.post("/{server_id}/probe", response_model=ServerOut)
async def probe_server(server_id: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Server:
    server = await session.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    endpoint = f"http://{server.private_ip}:{server.rpc_port}/health"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(endpoint)
        server.status = "healthy" if response.status_code == 200 else "degraded"
        server.metadata_json = {**server.metadata_json, "last_probe": "control-plane", "health_code": response.status_code}
    except httpx.HTTPError as exc:
        server.status = "unreachable"
        server.metadata_json = {**server.metadata_json, "last_probe": "control-plane", "probe_error": str(exc)[:200]}
    await session.commit()
    await session.refresh(server)
    return server


@router.post("/probe-all", response_model=list[ServerOut])
async def probe_all(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[Server]:
    servers = list((await session.scalars(select(Server).order_by(Server.name))).all())
    async with httpx.AsyncClient(timeout=5) as client:
        for server in servers:
            try:
                response = await client.get(f"http://{server.private_ip}:{server.rpc_port}/health")
                server.status = "healthy" if response.status_code == 200 else "degraded"
                server.metadata_json = {**server.metadata_json, "last_probe": "control-plane", "health_code": response.status_code}
            except httpx.HTTPError as exc:
                server.status = "unreachable"
                server.metadata_json = {**server.metadata_json, "last_probe": "control-plane", "probe_error": str(exc)[:200]}
    await session.commit()
    return servers
