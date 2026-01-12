from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore")

    # App
    env: str = "dev"
    service_name: str = "hub-api"

    # Database
    database_url: str = "postgresql+asyncpg://hub:hub@localhost:5432/hub"

    # Broker / Cache
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672//"
    redis_url: str = "redis://localhost:6379/0"

    # Security
    api_key_pepper: SecretStr = SecretStr("IN_ENV")

    # bootstrap protection (temporary)
    internal_admin_key: str = "IN_ENV"

    # Telemetry
    otlp_endpoint: str = "http://localhost:4318"  # Jaeger OTLP HTTP

    # Encryption
    credentials_encryption_key: SecretStr = SecretStr("IN_ENV")


settings = Settings()
