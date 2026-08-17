from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import ProviderCredential, Server, User
from app.db.session import get_session
from app.services.crypto import encrypt_secret
from app.services.hetzner import HetznerClient

router = APIRouter(prefix="/api/providers", tags=["providers"])


class CredentialCreate(BaseModel):
    name: str
    provider: str = "hetzner"
    token: str = Field(min_length=20)


class HetznerServerCreate(BaseModel):
    name: str
    server_type: str = "ccx23"
    image: str = "ubuntu-24.04"
    location: str | None = None
    ssh_keys: list[str] = Field(default_factory=list)
    confirm: bool = False


@router.get("/credentials")
async def list_credentials(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = list((await session.scalars(select(ProviderCredential).order_by(ProviderCredential.created_at.desc()))).all())
    return [{"id": row.id, "name": row.name, "provider": row.provider, "is_active": row.is_active} for row in rows]


@router.post("/credentials", status_code=201)
async def add_credential(payload: CredentialCreate, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    credential = ProviderCredential(name=payload.name, provider=payload.provider, encrypted_secret=encrypt_secret(payload.token))
    session.add(credential)
    await session.commit()
    return {"id": credential.id, "name": credential.name, "provider": credential.provider, "is_active": True}


@router.get("/hetzner/{credential_id}/servers")
async def hetzner_servers(credential_id: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    from app.services.crypto import decrypt_secret

    credential = await session.get(ProviderCredential, credential_id)
    if not credential or credential.provider != "hetzner":
        raise HTTPException(status_code=404, detail="Hetzner credential not found")
    client = HetznerClient(decrypt_secret(credential.encrypted_secret))
    try:
        return await client.list_servers()
    finally:
        await client.close()


@router.post("/hetzner/{credential_id}/servers", status_code=201)
async def create_hetzner_server(credential_id: str, payload: HetznerServerCreate, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    from app.services.crypto import decrypt_secret

    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to create a billable Hetzner server")
    credential = await session.get(ProviderCredential, credential_id)
    if not credential or credential.provider != "hetzner":
        raise HTTPException(status_code=404, detail="Hetzner credential not found")
    request_payload = payload.model_dump(exclude={"confirm"}, exclude_none=True)
    request_payload["start_after_create"] = True
    client = HetznerClient(decrypt_secret(credential.encrypted_secret))
    try:
        result = await client.create_server(request_payload)
    finally:
        await client.close()
    remote = result.get("server", {})
    public_ip = (remote.get("public_net") or {}).get("ipv4", {}).get("ip")
    server = Server(
        name=payload.name,
        provider="hetzner",
        provider_server_id=str(remote.get("id", "")),
        private_ip=f"pending-{remote.get('id', 'server')}",
        public_ip=public_ip,
        rpc_port=settings.default_backend_port,
        status="provisioning",
        labels={"provider": "hetzner"},
        metadata_json={"server_type": payload.server_type, "image": payload.image},
    )
    session.add(server)
    await session.commit()
    return {"server": {"id": server.id, "name": server.name, "provider": server.provider, "provider_server_id": server.provider_server_id, "public_ip": server.public_ip, "status": server.status}, "provider_response": {"action_id": (result.get("action", {}) or {}).get("id")}}
