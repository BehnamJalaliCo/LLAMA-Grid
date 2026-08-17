from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import api_key_digest, generate_api_key
from app.db.models import ApiKey, User
from app.db.session import get_session
from app.schemas import ApiKeyCreate, ApiKeyOut

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[ApiKey]:
    return list((await session.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()))).all())


@router.post("", response_model=ApiKeyOut, status_code=201)
async def create_api_key(payload: ApiKeyCreate, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> ApiKeyOut:
    raw = generate_api_key()
    key = ApiKey(name=payload.name, key_prefix=raw[:12], key_digest=api_key_digest(raw))
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return ApiKeyOut.model_validate(key).model_copy(update={"key": raw})


@router.post("/{key_id}/revoke", response_model=ApiKeyOut)
async def revoke_api_key(key_id: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> ApiKey:
    key = await session.get(ApiKey, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked = True
    await session.commit()
    await session.refresh(key)
    return key
