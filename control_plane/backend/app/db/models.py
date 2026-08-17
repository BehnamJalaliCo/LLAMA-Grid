import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


def new_id() -> str:
    return str(uuid.uuid4())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(120), default="Administrator")
    role: Mapped[str] = mapped_column(String(40), default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Server(TimestampMixin, Base):
    __tablename__ = "servers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="existing")
    provider_server_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    private_ip: Mapped[str] = mapped_column(String(64), unique=True)
    public_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rpc_port: Mapped[int] = mapped_column(Integer, default=8080)
    status: Mapped[str] = mapped_column(String(40), default="unknown")
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    replicas: Mapped[list["Replica"]] = relationship(back_populates="server")


class Model(TimestampMixin, Base):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_id: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(40), default="huggingface")
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantization: Mapped[str | None] = mapped_column(String(80), nullable=True)
    context_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="catalog")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Deployment(TimestampMixin, Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"))
    desired_replicas: Mapped[int] = mapped_column(Integer, default=1)
    strategy: Mapped[str] = mapped_column(String(40), default="rolling")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model: Mapped[Model] = relationship()
    replicas: Mapped[list["Replica"]] = relationship(back_populates="deployment")


class Replica(TimestampMixin, Base):
    __tablename__ = "replicas"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deployment_id: Mapped[str] = mapped_column(ForeignKey("deployments.id"))
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id"))
    endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    health: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    deployment: Mapped[Deployment] = relationship(back_populates="replicas")
    server: Mapped[Server] = relationship(back_populates="replicas")


class ProviderCredential(TimestampMixin, Base):
    __tablename__ = "provider_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(40))
    encrypted_secret: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="Queued")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobEvent(TimestampMixin, Base):
    __tablename__ = "job_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(500))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    key_prefix: Mapped[str] = mapped_column(String(32))
    key_digest: Mapped[str] = mapped_column(String(64), unique=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
