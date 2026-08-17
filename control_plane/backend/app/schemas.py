from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str
    password: str


class BootstrapRequest(LoginRequest):
    display_name: str = "Administrator"


class UserOut(ORMModel):
    id: str
    email: str
    display_name: str
    role: str


class ServerCreate(BaseModel):
    name: str
    private_ip: str
    provider: str = "existing"
    public_ip: str | None = None
    rpc_port: int = 8080
    labels: dict[str, Any] = Field(default_factory=dict)


class ServerOut(ORMModel):
    id: str
    name: str
    provider: str
    provider_server_id: str | None
    private_ip: str
    public_ip: str | None
    rpc_port: int
    status: str
    labels: dict[str, Any]
    metadata_json: dict[str, Any]


class ModelCreate(BaseModel):
    model_id: str
    display_name: str | None = None
    source: str = "huggingface"
    source_ref: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelOut(ORMModel):
    id: str
    model_id: str
    display_name: str
    source: str
    source_ref: str | None
    quantization: str | None
    context_length: int | None
    status: str
    metadata_json: dict[str, Any]


class DeploymentCreate(BaseModel):
    name: str
    model_id: str
    desired_replicas: int = Field(default=1, ge=1, le=500)
    strategy: str = "rolling"
    server_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class DeploymentOut(ORMModel):
    id: str
    name: str
    model_id: str
    desired_replicas: int
    strategy: str
    status: str
    config: dict[str, Any]
    job_id: str | None = None


class JobOut(ORMModel):
    id: str
    kind: str
    status: str
    progress: int
    message: str
    payload: dict[str, Any]
    error: str | None
    created_at: datetime
    updated_at: datetime


class ApiKeyCreate(BaseModel):
    name: str = "Panel key"


class ApiKeyOut(ORMModel):
    id: str
    name: str
    key_prefix: str
    revoked: bool
    created_at: datetime
    key: str | None = None
