from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LlamaGrid Control Plane"
    environment: str = "development"
    secret_key: str = "change-me-before-production"
    cookie_name: str = "llamagrid_session"
    cookie_secure: bool = False
    frontend_origin: str = "http://localhost:3000"
    database_url: str = "postgresql+asyncpg://llamagrid:llamagrid@localhost:5432/llamagrid"
    redis_url: str = "redis://localhost:6379/0"
    dispatcher_url: str = "http://localhost:18080"
    dispatcher_api_key: str = ""
    public_model_id: str = "default-model"
    public_model_display_name: str = "Configured model"
    public_model_context_length: int = Field(default=0, ge=0, le=1_048_576)
    public_model_quantization: str = "auto"
    huggingface_base_url: str = "https://huggingface.co"
    hetzner_base_url: str = "https://api.hetzner.cloud/v1"
    default_backend_ips: str = ""
    default_backend_port: int = Field(default=8080, ge=1, le=65_535)
    auto_create_schema: bool = False
    seed_existing_cluster: bool = True
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def backend_ips(self) -> list[str]:
        return [item.strip() for item in self.default_backend_ips.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
