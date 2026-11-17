from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_storage_services_have_no_published_ports_by_default():
    compose = (ROOT / 'docker-compose.yml').read_text()
    postgres = compose.split('  postgres:', 1)[1].split('  minio:', 1)[0]
    minio = compose.split('  minio:', 1)[1].split('  backend:', 1)[0]
    assert '\n    ports:' not in postgres
    assert '\n    ports:' not in minio
    assert 'MINIO_ENDPOINT: minio:9000' in compose
    assert 'DATABASE_URL: ${DOCKER_DATABASE_URL:-}' in compose
    assert 'POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD' in compose
    assert 'MINIO_ROOT_PASSWORD:?Set MINIO_ROOT_PASSWORD' in compose


def test_local_storage_ports_bind_only_to_loopback():
    override = (ROOT / 'docker-compose.local.yml').read_text()
    assert '127.0.0.1:5432:5432' in override
    assert '127.0.0.1:9000:9000' in override
    assert '127.0.0.1:9001:9001' in override
    assert '@postgres:5432/' in override
