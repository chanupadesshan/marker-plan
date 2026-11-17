"""
read settings from .env file and cache them for the lifetime of the application
"""

## functools is used to cache the settings so that they are only read from the .env file once
from functools import lru_cache
import re
from typing import Literal
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

## structure of the settings is defined in the settings class, which inherits from BaseSettings. The settings are read from the .env file and cached for the lifetime of the application
class Settings(BaseSettings):
    """
    Purpose: Hold the application's settings: database URL, MinIO connection, model name and API key,
    page resolution, upload limit and the diagnostics folder.
    Input: environment variables and the .env file; anything not set uses the default shown here.
    Output: a Settings object with one typed attribute per setting.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = "postgresql+psycopg://wovens:local-dev-password@localhost:5432/wovens_bom"
    postgres_user: str = ""
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "local-dev-minio-pass"
    minio_root_user: str = ""
    minio_secure: bool = False
    minio_bucket: str = "tech-packs"
    openrouter_api_key: str = ""
    openrouter_model: str = "qwen/qwen3-vl-235b-a22b-instruct"
    page_dpi: int = 220
    max_upload_mb: int = 40
    vision_page_classification: bool = True
    # How many model requests one Tech Pack extraction may have in flight at once (pages and page checks run side by side).
    # 1 reads strictly one page at a time. Lower it if the model provider starts rejecting requests with rate-limit errors.
    extraction_concurrency: int = Field(4, ge=1, le=8)
    diagnostics_dir: str = '.venv/diagnostics'
    # The development fallback is accepted only when local mode is explicitly selected.
    app_env: Literal['production', 'local'] = 'production'
    auth_secret: str = "local-dev-auth-secret-change-me"
    auth_token_hours: int = 12
    # The first admin. At start-up this account is created (or promoted to admin if it exists) when both are set.
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Administrator"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = Field("", validation_alias=AliasChoices("langfuse_base_url", "langfuse_host"))
    # Optional USD per million tokens, used on the usage dashboard only for requests with no recorded cost.
    llm_price_input_per_mtok: float | None = None
    llm_price_output_per_mtok: float | None = None
    # Off by default: traces then hold only metadata (tokens, timings, status), never prompts or PDF text.
    langfuse_capture_content: bool = False

    @model_validator(mode='after')
    def validate_signing_secret(self):
        if self.app_env == 'production':
            secret = self.auth_secret
            if not re.fullmatch(r'[0-9a-f]{64}', secret):
                raise ValueError('AUTH_SECRET must be a securely generated 32-byte lowercase hexadecimal key in production')
            key = bytes.fromhex(secret)
            repeated = any(all(key[i] == key[i % period] for i in range(period, len(key)))
                           for period in range(1, len(key) // 2 + 1))
            step = (key[1] - key[0]) % 256
            sequential = all((key[i] - key[i - 1]) % 256 == step for i in range(2, len(key)))
            if len(set(key)) < 16 or repeated or sequential:
                raise ValueError('AUTH_SECRET must be a securely generated 32-byte lowercase hexadecimal key in production')
        return self

    @model_validator(mode='after')
    def validate_production_storage(self):
        if self.app_env != 'production':
            return self
        try:
            url = make_url(self.database_url)
        except Exception:
            raise ValueError('DATABASE_URL must contain valid production credentials') from None
        required = {'database_url', 'minio_access_key', 'minio_secret_key'}
        if (not required.issubset(self.model_fields_set) or not url.username or not url.password
                or url.password in {'local-dev-password', 'change-this-for-real-deployments'}
                or (self.postgres_user and url.username == self.postgres_user)
                or not self.minio_access_key or self.minio_access_key == 'minioadmin'
                or (self.minio_root_user and self.minio_access_key == self.minio_root_user)
                or not self.minio_secret_key
                or self.minio_secret_key in {'local-dev-minio-pass', 'change-this-minio-password'}
                or self.minio_secret_key == url.password):
            raise ValueError('Production requires distinct, explicitly configured database and MinIO service credentials')
        return self

    @field_validator('llm_price_input_per_mtok', 'llm_price_output_per_mtok', mode='before')
    @classmethod
    def empty_optional_price(cls, value):
        # Docker Compose supplies an empty string when optional prices are unset.
        return None if value == '' else value


@lru_cache
def get_settings() -> Settings:
    """
    Purpose: Provide the application settings (database, MinIO, model and upload limits).
    They are read from the environment and the .env file once, then cached.
    Input: none.
    Output: the shared Settings object.
    """
    return Settings()
