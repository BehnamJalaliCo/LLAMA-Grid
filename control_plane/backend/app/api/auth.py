from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import hash_password, issue_session, verify_password
from app.db.models import User
from app.db.session import get_session
from app.schemas import BootstrapRequest, LoginRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
async def auth_status(session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    return {"bootstrap_required": (await session.scalar(select(func.count(User.id))) or 0) == 0}


@router.post("/bootstrap", response_model=UserOut, status_code=201)
async def bootstrap(payload: BootstrapRequest, response: Response, session: AsyncSession = Depends(get_session)) -> User:
    count = await session.scalar(select(func.count(User.id))) or 0
    if count:
        raise HTTPException(status_code=409, detail="An administrator already exists")
    if len(payload.password) < 14:
        raise HTTPException(status_code=422, detail="Use a password of at least 14 characters")
    user = User(email=payload.email.lower().strip(), password_hash=hash_password(payload.password), display_name=payload.display_name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    response.set_cookie(settings.cookie_name, issue_session(user.id), httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=604800)
    return user


@router.post("/login", response_model=UserOut)
async def login(payload: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)) -> User:
    user = await session.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    response.set_cookie(settings.cookie_name, issue_session(user.id), httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=604800)
    return user


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(settings.cookie_name)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
