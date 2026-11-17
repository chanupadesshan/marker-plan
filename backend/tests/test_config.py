import pytest
import secrets
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture
def production_storage(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://app:synthetic-database-password@postgres/db')
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'synthetic-app-access')
    monkeypatch.setenv('MINIO_SECRET_KEY', 'synthetic-object-password')
    monkeypatch.delenv('MINIO_ROOT_USER', raising=False)
    monkeypatch.delenv('POSTGRES_USER', raising=False)


def test_empty_optional_prices_allow_startup(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setenv('LLM_PRICE_INPUT_PER_MTOK', '')
    monkeypatch.setenv('LLM_PRICE_OUTPUT_PER_MTOK', '')
    settings = Settings(_env_file=None)
    assert settings.llm_price_input_per_mtok is None
    assert settings.llm_price_output_per_mtok is None


def test_configured_prices_are_preserved(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setenv('LLM_PRICE_INPUT_PER_MTOK', '0')
    monkeypatch.setenv('LLM_PRICE_OUTPUT_PER_MTOK', '2.5')
    settings = Settings(_env_file=None)
    assert settings.llm_price_input_per_mtok == 0
    assert settings.llm_price_output_per_mtok == 2.5


def test_invalid_price_is_rejected(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.setenv('LLM_PRICE_INPUT_PER_MTOK', 'invalid')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize('secret', ['', 'short', '0' * 64, 'z' * 64, 'ab' * 32])
def test_production_rejects_unsafe_signing_secrets(monkeypatch, production_storage, secret):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('AUTH_SECRET', secret)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize('key', [
    bytes(range(32)),
    bytes(range(31, -1, -1)),
    bytes((240 + 3 * index) % 256 for index in range(32)),
    bytes(range(16)) * 2,
], ids=['ascending', 'descending', 'wrapped-step', 'repeated-block'])
def test_production_rejects_predictable_patterns(monkeypatch, production_storage, key):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('AUTH_SECRET', key.hex())
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_requires_secret_by_default(monkeypatch, production_storage):
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.delenv('AUTH_SECRET', raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_accepts_generated_secret(monkeypatch, production_storage):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('AUTH_SECRET', secrets.token_hex(32))
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://app:synthetic-database-password@postgres/db')
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'synthetic-app-access')
    monkeypatch.setenv('MINIO_SECRET_KEY', 'synthetic-object-password')
    assert Settings(_env_file=None).app_env == 'production'


def test_local_mode_allows_development_default(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'local')
    monkeypatch.delenv('AUTH_SECRET', raising=False)
    assert Settings(_env_file=None).app_env == 'local'


def test_unknown_environment_is_rejected(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'prodution')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize('missing', ['DATABASE_URL', 'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY'])
def test_production_requires_storage_credentials(monkeypatch, missing):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('AUTH_SECRET', secrets.token_hex(32))
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://app:synthetic-database-password@postgres/db')
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'synthetic-app-access')
    monkeypatch.setenv('MINIO_SECRET_KEY', 'synthetic-object-password')
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_production_rejects_root_minio_identity(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('AUTH_SECRET', secrets.token_hex(32))
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://app:synthetic-database-password@postgres/db')
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'synthetic-root-access')
    monkeypatch.setenv('MINIO_SECRET_KEY', 'synthetic-object-password')
    monkeypatch.setenv('MINIO_ROOT_USER', 'synthetic-root-access')
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize('field,value', [
    ('DATABASE_URL', 'postgresql+psycopg://app:local-dev-password@postgres/db'),
    ('MINIO_ACCESS_KEY', 'minioadmin'),
    ('MINIO_SECRET_KEY', 'local-dev-minio-pass'),
    ('MINIO_SECRET_KEY', 'synthetic-database-password'),
    ('POSTGRES_USER', 'app'),
], ids=['default-db-password', 'default-minio-user', 'default-minio-password', 'reused-password', 'bootstrap-db-user'])
def test_production_rejects_insecure_storage_settings(monkeypatch, field, value):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('AUTH_SECRET', secrets.token_hex(32))
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://app:synthetic-database-password@postgres/db')
    monkeypatch.setenv('MINIO_ACCESS_KEY', 'synthetic-app-access')
    monkeypatch.setenv('MINIO_SECRET_KEY', 'synthetic-object-password')
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
