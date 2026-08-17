from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import Deployment, Job, Model, Server, User
from app.db.session import get_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    server_total = await session.scalar(select(func.count(Server.id))) or 0
    server_healthy = await session.scalar(select(func.count(Server.id)).where(Server.status.in_(["healthy", "reachable"]))) or 0
    model_total = await session.scalar(select(func.count(Model.id))) or 0
    deployment_total = await session.scalar(select(func.count(Deployment.id))) or 0
    running_jobs = await session.scalar(select(func.count(Job.id)).where(Job.status.not_in(["completed", "failed", "cancelled"]))) or 0
    return {
        "servers": server_total,
        "healthy_servers": server_healthy,
        "models": model_total,
        "deployments": deployment_total,
        "running_jobs": running_jobs,
        "inference": {
            "model": settings.public_model_id,
            "context_length": settings.public_model_context_length or None,
            "replicas": server_total,
        },
    }
