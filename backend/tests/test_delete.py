from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app import main, po_routes, storage


class FakeSession:
    """Holds one row; records what the route deleted and committed."""
    def __init__(self, row):
        self.row, self.deleted, self.committed = row, [], False

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, model, key, **kwargs): return self.row if self.row is not None and key == self.row.id else None
    def delete(self, row): self.deleted.append(row)
    def commit(self): self.committed = True


def row(status):
    return SimpleNamespace(id=uuid4(), status=status, extraction=None)


@pytest.fixture
def removed(monkeypatch):
    prefixes = []
    monkeypatch.setattr(main, 'delete_prefix', prefixes.append)
    monkeypatch.setattr(po_routes, 'delete_prefix', prefixes.append)
    return prefixes


def client_for(monkeypatch, module, session):
    monkeypatch.setattr(module, 'SessionLocal', lambda: session)
    app = FastAPI()
    app.include_router(po_routes.router)
    app.delete('/api/documents/{doc_id}')(main.delete_document)
    return TestClient(app)


@pytest.mark.parametrize('module,path,prefix', [
    (po_routes, '/api/purchase-orders/{id}', 'purchase-orders/{id}/'),
    (main, '/api/documents/{id}', '{id}/'),
])
def test_delete_removes_row_then_stored_files(monkeypatch, removed, module, path, prefix):
    target = row('approved')
    session = FakeSession(target)
    response = client_for(monkeypatch, module, session).delete(path.format(id=target.id))
    assert response.status_code == 200 and response.json() == {'ok': True}
    assert session.deleted == [target] and session.committed
    assert removed == [prefix.format(id=target.id)]


@pytest.mark.parametrize('module,path', [(po_routes, '/api/purchase-orders/{id}'), (main, '/api/documents/{id}')])
@pytest.mark.parametrize('status', ['queued', 'processing'])
def test_delete_is_refused_while_extraction_runs(monkeypatch, removed, module, path, status):
    target = row(status)
    session = FakeSession(target)
    response = client_for(monkeypatch, module, session).delete(path.format(id=target.id))
    assert response.status_code == 409
    assert session.deleted == [] and not session.committed and removed == []


@pytest.mark.parametrize('module,path', [(po_routes, '/api/purchase-orders/{id}'), (main, '/api/documents/{id}')])
def test_delete_unknown_document_is_404(monkeypatch, removed, module, path):
    response = client_for(monkeypatch, module, FakeSession(None)).delete(path.format(id=uuid4()))
    assert response.status_code == 404 and removed == []


def test_failed_documents_can_be_deleted(monkeypatch, removed):
    target = row('failed')
    session = FakeSession(target)
    assert client_for(monkeypatch, po_routes, session).delete(f'/api/purchase-orders/{target.id}').status_code == 200


def test_storage_delete_prefix_removes_every_object_and_survives_errors(monkeypatch):
    deleted = []
    fake = SimpleNamespace(
        list_objects=lambda bucket, prefix, recursive: [SimpleNamespace(object_name=f'{prefix}source/a.pdf'),
                                                         SimpleNamespace(object_name=f'{prefix}page-images/page-1.jpg')],
        remove_object=lambda bucket, name: deleted.append(name))
    monkeypatch.setattr(storage, 'client', lambda: fake)
    monkeypatch.setattr(storage, 'get_settings', lambda: SimpleNamespace(minio_bucket='b'))
    assert storage.delete_prefix('doc/') is True
    assert deleted == ['doc/source/a.pdf', 'doc/page-images/page-1.jpg']

    def broken(): raise RuntimeError('minio down')
    monkeypatch.setattr(storage, 'client', broken)
    assert storage.delete_prefix('doc/') is False
