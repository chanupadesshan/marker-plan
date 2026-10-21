"""
read settings from .env file and cache them for the lifetime of the application
"""

## functools is used to cache the settings so that they are only read from the .env file once
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

## structure of the settings is defined in the settings class, which inherits from BaseSettings. The settings are read from the .env file and cached for the lifetime of the application
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://wovens:local-dev-password@localhost:5432/wovens_bom"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "local-dev-minio-pass"
    minio_secure: bool = False
    minio_bucket: str = "tech-packs"
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-vl-235b-a22b-instruct"
    page_dpi: int = 220
    max_upload_mb: int = 40
    vision_page_classification: bool = True
    diagnostics_dir: str = '.venv/diagnostics'


@lru_cache
def get_settings() -> Settings:
    return Settings()
