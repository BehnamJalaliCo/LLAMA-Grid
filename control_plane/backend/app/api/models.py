from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Model, User
from app.db.session import get_session
from app.schemas import ModelCreate, ModelOut
from app.services.huggingface import search_models

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelOut])
async def list_models(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[Model]:
    return list((await session.scalars(select(Model).order_by(Model.display_name))).all())


@router.get("/search")
async def search_huggingface(q: str = Query(min_length=2), _: User = Depends(get_current_user)) -> list[dict]:
    try:
        return await search_models(q)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Hugging Face search failed: {exc}") from exc


@router.post("", response_model=ModelOut, status_code=201)
async def add_model(payload: ModelCreate, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Model:
    existing = await session.scalar(select(Model).where(Model.model_id == payload.model_id))
    if existing:
        return existing
    values = payload.model_dump()
    values["display_name"] = values["display_name"] or payload.model_id.rsplit("/", 1)[-1]
    model = Model(**values, status="catalog")
    session.add(model)
    await session.commit()
    await session.refresh(model)
    return model
