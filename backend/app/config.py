"""
read settings from .env file and cache them for the lifetime of the application
"""

## functools is used to cache the settings so that they are only read from the .env file once
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

## structure of the settings is defined in the settings class, which inherits from BaseSettings. The settings are read from the .env file and cached for the lifetime of the application
class Settings(BaseSettings):
    """
    Purpose: Hold the application's settings: database URL, MinIO connection, model name and API key,
    page resolution, upload limit and the diagnostics folder.
    Input: environment variables and the .env file; anything not set uses the default shown here.
    Output: a Settings object with one typed attribute per setting.
    """
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
    """
    Purpose: Provide the application settings (database, MinIO, model and upload limits).
    They are read from the environment and the .env file once, then cached.
    Input: none.
    Output: the shared Settings object.
    """
    return Settings()
