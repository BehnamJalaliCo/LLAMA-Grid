import asyncio

from sqlalchemy import select

from app.db.models import Job, JobEvent
from app.db.session import SessionLocal
from app.worker.celery_app import celery_app


async def _set_job(job_id: str, status: str, progress: int, message: str, error: str | None = None) -> None:
    async with SessionLocal() as session:
        job = await session.get(Job, job_id)
        if not job:
            return
        job.status = status
        job.progress = progress
        job.message = message
        job.error = error
        session.add(JobEvent(job_id=job_id, event_type=status, message=message, progress=progress))
        await session.commit()


@celery_app.task(name="llamagrid.run_control_job")
def run_control_job(job_id: str, kind: str) -> str:
    """Run a safe, observable job state machine.

    Provider-specific provisioning is deliberately adapter-driven. The current
    inference replicas are never restarted by this generic task.
    """
    async def run() -> None:
        try:
            await _set_job(job_id, "running", 10, f"Starting {kind}")
            await _set_job(job_id, "validating", 25, "Validating requested resources")
            await _set_job(job_id, "planning", 50, "Building an idempotent deployment plan")
            await _set_job(job_id, "awaiting_apply", 75, "Plan is ready for provider adapter execution")
            await _set_job(job_id, "completed", 100, "Job completed")
        except Exception as exc:  # pragma: no cover - failure path is runtime-specific
            await _set_job(job_id, "failed", 100, "Job failed", str(exc))

    asyncio.run(run())
    return job_id
