import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response

from app.api import api_keys, auth, chat, dashboard, deployments, jobs, models, providers, public_api, servers
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.models import Model, Server
from app.db.session import SessionLocal, engine
from sqlalchemy import select

REQUESTS = Counter("llamagrid_control_plane_requests_total", "Control-plane requests", ["path", "method"])


async def seed_inventory() -> None:
    if not settings.seed_existing_cluster:
        return
    async with SessionLocal() as session:
        for index, ip in enumerate(settings.backend_ips, start=1):
            if not await session.scalar(select(Server).where(Server.private_ip == ip)):
                session.add(
                    Server(
                        name=f"Worker-{index:02d}",
                        private_ip=ip,
                        rpc_port=settings.default_backend_port,
                        status="unknown",
                        provider="existing",
                        labels={"role": "inference", "managed": "existing"},
                    )
                )
        if settings.public_model_id and not await session.scalar(
            select(Model).where(Model.model_id == settings.public_model_id)
        ):
            session.add(
                Model(
                    model_id=settings.public_model_id,
                    display_name=settings.public_model_display_name,
                    source="existing-cluster",
                    status="deployed",
                    context_length=settings.public_model_context_length or None,
                    quantization=settings.public_model_quantization,
                    metadata_json={"replicas": len(settings.backend_ips)},
                )
            )
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    app.state.logger = logging.getLogger("llamagrid.control-plane")
    if settings.auto_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    if settings.seed_existing_cluster:
        await seed_inventory()
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan, docs_url="/api/docs", redoc_url="/api/redoc")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def count_requests(request, call_next):
    response = await call_next(request)
    REQUESTS.labels(request.url.path, request.method).inc()
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "llamagrid-control-plane"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.exec_driver_sql("SELECT 1")
    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(servers.router)
app.include_router(models.router)
app.include_router(deployments.router)
app.include_router(jobs.router)
app.include_router(chat.router)
app.include_router(api_keys.router)
app.include_router(providers.router)
app.include_router(public_api.router)
