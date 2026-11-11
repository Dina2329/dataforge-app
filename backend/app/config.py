from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://dataforge:dataforge@postgres:5432/dataforge"
    # SQLAlchemy's defaults (5 pooled + 10 overflow = 15 concurrent connections)
    # are sized for light dev use, not ~20 concurrent editors in one base — the
    # API and the arq worker each hold their own separate pool of this size, so
    # bump both here rather than per-engine to keep them in sync.
    db_pool_size: int = 20
    db_max_overflow: int = 20
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    # Dev-only default — a valid Fernet key, but obviously not secret since it's
    # committed here. Production deployments MUST set a real DATAFORGE_MASTER_KEY.
    encryption_key: str = "srwh6PTBi-4C85jpTkZjLPP4MOofRM8ETtY_vxRV3PI="
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    # Includes the host's LAN IP so colleagues on the same network can reach
    # the dev server too, not just requests originating from this machine.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://172.27.137.39:5173"]
    # Local-disk object storage for attachment fields — swappable behind
    # StorageService for a future S3/MinIO-backed implementation, same pattern
    # as SecretsService for credentials.
    attachments_dir: str = "./data/attachments"


settings = Settings()
