from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Deployment, Job, JobEvent, Model, Replica, Server, User
from app.db.session import get_session
from app.schemas import DeploymentCreate, DeploymentOut, JobOut
from app.worker.tasks import run_control_job

router = APIRouter(prefix="/api/deployments", tags=["deployments"])


@router.get("", response_model=list[DeploymentOut])
async def list_deployments(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[Deployment]:
    return list((await session.scalars(select(Deployment).order_by(Deployment.created_at.desc()))).all())


@router.post("", response_model=DeploymentOut, status_code=201)
async def create_deployment(payload: DeploymentCreate, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Deployment:
    model = await session.get(Model, payload.model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    deployment = Deployment(
        name=payload.name,
        model_id=payload.model_id,
        desired_replicas=payload.desired_replicas,
        strategy=payload.strategy,
        config=payload.config,
        status="planning",
    )
    session.add(deployment)
    await session.flush()
    job = Job(kind="deployment.apply", status="queued", payload={"deployment_id": deployment.id})
    session.add(job)
    await session.flush()
    session.add(JobEvent(job_id=job.id, event_type="queued", message="Deployment queued", progress=0))
    selected = payload.server_ids
    if not selected:
        selected = [item.id for item in (await session.scalars(select(Server).where(Server.status.in_(["healthy", "reachable", "unknown"])).limit(payload.desired_replicas))).all()]
    for server_id in selected[: payload.desired_replicas]:
        if await session.get(Server, server_id):
            session.add(Replica(deployment_id=deployment.id, server_id=server_id, status="planned"))
    await session.commit()
    try:
        run_control_job.delay(job.id, "deployment.apply")
    except Exception:
        # The API remains usable while Redis/Celery is being started; operators can retry the job.
        job.message = "Queued; worker will process when Redis is available"
        await session.commit()
    await session.refresh(deployment)
    result = DeploymentOut.model_validate(deployment).model_dump()
    result["job_id"] = job.id
    return result


@router.get("/{deployment_id}", response_model=DeploymentOut)
async def get_deployment(deployment_id: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Deployment:
    deployment = await session.get(Deployment, deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment
