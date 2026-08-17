import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Job, JobEvent, User
from app.db.session import get_session
from app.schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[Job]:
    return list((await session.scalars(select(Job).order_by(Job.created_at.desc()).limit(100))).all())


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> Job:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/events")
async def job_events(job_id: str, _: User = Depends(get_current_user)) -> StreamingResponse:
    async def stream():
        last_seen: str | None = None
        for _ in range(300):
            async with AsyncSessionLocal() as session:
                job = await session.get(Job, job_id)
                if not job:
                    yield f"event: error\ndata: {json.dumps({'message': 'Job not found'})}\n\n"
                    return
                query = select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at)
                if last_seen:
                    previous = await session.get(JobEvent, last_seen)
                    if previous:
                        query = query.where(JobEvent.created_at > previous.created_at)
                events = list((await session.scalars(query)).all())
                for event in events:
                    last_seen = event.id
                    yield f"event: progress\ndata: {json.dumps({'status': job.status, 'progress': event.progress, 'message': event.message})}\n\n"
                if job.status in {"completed", "failed", "cancelled"}:
                    yield f"event: done\ndata: {json.dumps({'status': job.status})}\n\n"
                    return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


AsyncSessionLocal = __import__("app.db.session", fromlist=["SessionLocal"]).SessionLocal
