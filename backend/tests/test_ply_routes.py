from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app import ply_routes
from app.models import Ply


class FakeSession:
    """An in-memory stand-in for the database session, holding Ply rows by id."""
    def __init__(self, rows):
        self.rows, self.committed = rows, 0

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def scalars(self, *args, **kwargs): return sorted(self.rows.values(), key=lambda row: row.id)
    def get(self, model, key): return self.rows.get(key)
    def add(self, row):
        row.id = max(self.rows, default=0) + 1
        self.rows[row.id] = row
    def delete(self, row): del self.rows[row.id]
    def commit(self): self.committed += 1


@pytest.fixture
def client(monkeypatch):
    rows = {1: Ply(id=1, col_b=1, col_c='1800', col_d='90-100'), 2: Ply(id=2, col_b=2, col_c='818647', col_d=None)}
    session = FakeSession(rows)
    monkeypatch.setattr(ply_routes, 'SessionLocal', lambda: session)
    app = FastAPI(); app.include_router(ply_routes.router)
    test_client = TestClient(app)
    test_client.session = session
    return test_client


def test_list_returns_every_row_in_id_order(client):
    assert client.get('/api/plies').json() == [
        {'id': 1, 'col_b': 1, 'col_c': '1800', 'col_d': '90-100'},
        {'id': 2, 'col_b': 2, 'col_c': '818647', 'col_d': None}]


def test_add_creates_a_row_trims_text_and_turns_a_blank_col_d_into_null(client):
    response = client.post('/api/plies', json={'col_b': 1, 'col_c': '  R1330-1000 ', 'col_d': '   '})
    assert response.status_code == 201
    assert response.json() == {'id': 3, 'col_b': 1, 'col_c': 'R1330-1000', 'col_d': None}
    assert client.session.committed == 1 and len(client.get('/api/plies').json()) == 3


def test_add_without_col_d_is_allowed(client):
    assert client.post('/api/plies', json={'col_b': 2, 'col_c': 'F0717'}).json()['col_d'] is None


@pytest.mark.parametrize('body', [
    {'col_c': 'x'},                                  # col_b missing
    {'col_b': 'one', 'col_c': 'x'},                  # col_b not a whole number
    {'col_b': 1},                                    # col_c missing
    {'col_b': 1, 'col_c': '   '},                    # col_c blank
    {'col_b': 1, 'col_c': 'x' * 101},                # col_c too long
    {'col_b': 1, 'col_c': 'x', 'col_d': 'y' * 101},  # col_d too long
    {'col_b': 1, 'col_c': 'x', 'id': 99},            # the id cannot be set by the user
])
def test_invalid_input_is_rejected_and_nothing_is_saved(client, body):
    assert client.post('/api/plies', json=body).status_code == 422
    assert client.session.committed == 0 and len(client.session.rows) == 2


def test_edit_replaces_the_values(client):
    response = client.put('/api/plies/2', json={'col_b': 1, 'col_c': '818648', 'col_d': '70'})
    assert response.status_code == 200
    assert response.json() == {'id': 2, 'col_b': 1, 'col_c': '818648', 'col_d': '70'}
    assert client.session.rows[2].col_d == '70'


def test_edit_can_clear_col_d(client):
    assert client.put('/api/plies/1', json={'col_b': 1, 'col_c': '1800', 'col_d': ''}).json()['col_d'] is None


def test_edit_validates_and_unknown_id_is_404(client):
    assert client.put('/api/plies/1', json={'col_b': 1, 'col_c': ''}).status_code == 422
    assert client.put('/api/plies/99', json={'col_b': 1, 'col_c': 'x'}).status_code == 404


def test_delete_removes_the_row(client):
    assert client.delete('/api/plies/1').json() == {'ok': True}
    assert [row['id'] for row in client.get('/api/plies').json()] == [2]


def test_delete_unknown_id_is_404(client):
    assert client.delete('/api/plies/99').status_code == 404
