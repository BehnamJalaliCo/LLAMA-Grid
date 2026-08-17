from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import api_key_digest
from app.db.models import ApiKey
from app.db.models import User
from app.db.session import get_session
from app.core.security import read_session


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    user_id = read_session(request.cookies.get(settings.cookie_name))
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user


async def get_public_api_key(
    request: Request, session: AsyncSession = Depends(get_session)
) -> ApiKey:
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer API key required")
    key = await session.scalar(select(ApiKey).where(ApiKey.key_digest == api_key_digest(value), ApiKey.revoked.is_(False)))
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return key
