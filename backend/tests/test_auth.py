import time
import secrets
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app import admin_routes, auth
from app.models import User


class FakeSession:
    """An in-memory stand-in for the database session, holding User rows by email."""
    def __init__(self):
        self.users = {}

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def scalar(self, statement): return self.users.get(statement.whereclause.right.value)
    def scalars(self, statement): return list(self.users.values())
    def get(self, model, key): return next((user for user in self.users.values() if str(user.id) == str(key)), None)
    def add(self, user):
        user.id = user.id or f'00000000-0000-0000-0000-{len(self.users) + 1:012d}'
        user.is_admin = bool(user.is_admin)
        user.is_active = True if user.is_active is None else user.is_active
        user.permissions = user.permissions or {}
        user.created_at = None
        self.users[user.email] = user
    def delete(self, user): del self.users[user.email]
    def commit(self): pass


def make_user(session, email='ada@example.com', password='correct horse', **changes):
    user = User(email=email, full_name='Ada', password_hash=auth.hash_password(password), **changes)
    session.add(user)
    return user


@pytest.fixture
def session(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(auth, 'SessionLocal', lambda: fake)
    monkeypatch.setattr(admin_routes, 'SessionLocal', lambda: fake)
    return fake


@pytest.fixture
def client(session):
    app = FastAPI()
    app.include_router(auth.router); app.include_router(admin_routes.router)
    app.get('/api/plies-like', dependencies=[auth.Depends(auth.needs('plies'))])(lambda: {'ok': True})
    app.post('/api/plies-like', dependencies=[auth.Depends(auth.needs('plies'))])(lambda: {'ok': True})
    return TestClient(app)


def bearer(user):
    return {'Authorization': f'Bearer {auth.make_token(user.id)}'}


def login(client, email='ada@example.com', password='correct horse'):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


# ---- passwords and tokens ------------------------------------------------------------------------------

def test_password_hash_verifies_only_the_right_password_and_is_salted():
    stored = auth.hash_password('s3cret-pass')
    assert 's3cret-pass' not in stored and stored != auth.hash_password('s3cret-pass')
    assert auth.verify_password('s3cret-pass', stored)
    assert not auth.verify_password('s3cret-pasS', stored)
    assert not auth.verify_password('x', 'garbage')


def test_token_round_trip_and_rejections(monkeypatch):
    token = auth.make_token('abc')
    assert auth.read_token(token) == 'abc'
    payload, signature = token.split('.')
    assert auth.read_token(payload + '.' + signature[:-2] + 'AA') is None   # forged signature
    assert auth.read_token('not-a-token') is None and auth.read_token('') is None
    now = time.time()
    monkeypatch.setattr(auth.time, 'time', lambda: now + 13 * 3600)          # past the 12-hour lifetime
    assert auth.read_token(token) is None


def test_token_key_rotation_and_expiration(monkeypatch):
    current = SimpleNamespace(auth_secret=secrets.token_hex(32), auth_token_hours=1)
    monkeypatch.setattr(auth, 'get_settings', lambda: current)
    monkeypatch.setattr(auth.time, 'time', lambda: 1000)
    token = auth.make_token('user-id')
    assert auth.read_token(token) == 'user-id'
    payload, signature = token.split('.')
    assert auth.read_token(payload + '.' + ('A' if signature[0] != 'A' else 'B') + signature[1:]) is None
    current.auth_secret = secrets.token_hex(32)
    assert auth.read_token(token) is None
    new_token = auth.make_token('user-id')
    assert auth.read_token(new_token) == 'user-id'
    monkeypatch.setattr(auth.time, 'time', lambda: 4600)
    assert auth.read_token(new_token) is None


# ---- login ---------------------------------------------------------------------------------------------

def test_there_is_no_public_registration(client):
    assert client.post('/api/auth/register', json={'email': 'a@b.co', 'password': 'longenough', 'full_name': 'A'}).status_code in (404, 405)


def test_login_returns_a_working_token_and_the_users_permissions(client, session):
    make_user(session, permissions={'plies': 'view', 'bogus': 'edit'})
    response = login(client, ' ADA@example.com')
    assert response.status_code == 200
    body = response.json()
    assert body['user']['permissions'] == {'plies': 'view'} and body['user']['is_admin'] is False
    me = client.get('/api/auth/me', headers={'Authorization': f"Bearer {body['token']}"})
    assert me.json()['user']['email'] == 'ada@example.com'


def test_login_failures_look_the_same_for_a_wrong_password_and_an_unknown_email(client, session):
    make_user(session)
    wrong, unknown = login(client, password='nope nope'), login(client, email='who@example.com')
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {'detail': 'Incorrect email or password'}


def test_a_disabled_account_cannot_log_in_and_its_old_token_stops_working(client, session):
    user = make_user(session)
    headers = bearer(user)
    user.is_active = False
    assert login(client).status_code == 403
    assert client.get('/api/auth/me', headers=headers).status_code == 401


def test_passwords_keep_their_surrounding_spaces(client, session):
    make_user(session, password='  spaced out  ')
    assert login(client, password='spaced out').status_code == 401
    assert login(client, password='  spaced out  ').status_code == 200


@pytest.mark.parametrize('header', [None, '', 'Bearer', 'Bearer junk', 'Basic abc', 'Bearer a.b'])
def test_protected_routes_reject_missing_or_bad_tokens(client, header):
    response = client.get('/api/plies-like', headers={'Authorization': header} if header is not None else {})
    assert response.status_code == 401 and response.headers['www-authenticate'] == 'Bearer'


# ---- permissions ---------------------------------------------------------------------------------------

def test_view_allows_reading_but_not_changing(client, session):
    headers = bearer(make_user(session, permissions={'plies': 'view'}))
    assert client.get('/api/plies-like', headers=headers).status_code == 200
    denied = client.post('/api/plies-like', headers=headers)
    assert denied.status_code == 403 and 'edit access to Plies' in denied.json()['detail']


def test_edit_allows_reading_and_changing(client, session):
    headers = bearer(make_user(session, permissions={'plies': 'edit'}))
    assert client.get('/api/plies-like', headers=headers).status_code == 200
    assert client.post('/api/plies-like', headers=headers).status_code == 200


def test_no_permission_for_a_feature_is_403_even_with_others(client, session):
    headers = bearer(make_user(session, permissions={'usage': 'edit'}))
    assert client.get('/api/plies-like', headers=headers).status_code == 403


def test_admins_can_do_everything(client, session):
    headers = bearer(make_user(session, is_admin=True))
    assert client.post('/api/plies-like', headers=headers).status_code == 200
    assert login(client).json()['user']['permissions'] == {f: 'edit' for f in auth.FEATURES}


# ---- admin: manage users -------------------------------------------------------------------------------

def new_user(**changes):
    return {'email': 'Bob@Example.com', 'full_name': 'Bob', 'password': 'bobs password',
            'is_admin': False, 'permissions': {'techpacks': 'view', 'plies': 'none'}} | changes


def test_only_admins_can_use_the_user_management_api(client, session):
    user = make_user(session, permissions={f: 'edit' for f in auth.FEATURES})
    for method, url in [('get', '/api/admin/users'), ('post', '/api/admin/users'), ('get', '/api/admin/features')]:
        assert getattr(client, method)(url, headers=bearer(user)).status_code == 403
    assert client.get('/api/admin/users').status_code == 401


def test_admin_creates_a_user_who_can_then_log_in_with_only_the_granted_access(client, session):
    admin = make_user(session, email='root@example.com', is_admin=True)
    response = client.post('/api/admin/users', json=new_user(), headers=bearer(admin))
    assert response.status_code == 201
    assert response.json()['email'] == 'bob@example.com' and response.json()['permissions'] == {'techpacks': 'view'}
    assert 'password' not in str(response.json())
    logged_in = login(client, 'bob@example.com', 'bobs password')
    assert logged_in.status_code == 200 and logged_in.json()['user']['is_admin'] is False


def test_creating_a_duplicate_email_is_409(client, session):
    admin = make_user(session, email='root@example.com', is_admin=True)
    assert client.post('/api/admin/users', json=new_user(), headers=bearer(admin)).status_code == 201
    assert client.post('/api/admin/users', json=new_user(email='BOB@example.com'), headers=bearer(admin)).status_code == 409


@pytest.mark.parametrize('changes', [
    {'email': 'nope'}, {'password': 'short'}, {'full_name': '  '}, {'permissions': {'nothing': 'view'}},
    {'permissions': {'plies': 'owner'}}, {'surprise': 1},
])
def test_creating_a_user_validates_input(client, session, changes):
    admin = make_user(session, email='root@example.com', is_admin=True)
    assert client.post('/api/admin/users', json=new_user(**changes), headers=bearer(admin)).status_code == 422
    assert len(session.users) == 1


def test_admin_edits_permissions_role_and_resets_a_password(client, session):
    admin = make_user(session, email='root@example.com', is_admin=True)
    bob = make_user(session, email='bob@example.com', password='old password')
    body = {'full_name': 'Robert', 'is_admin': False, 'is_active': True, 'permissions': {'usage': 'edit'}, 'password': 'brand new pass'}
    response = client.put(f'/api/admin/users/{bob.id}', json=body, headers=bearer(admin))
    assert response.status_code == 200 and response.json()['permissions'] == {'usage': 'edit'}
    assert login(client, 'bob@example.com', 'old password').status_code == 401
    assert login(client, 'bob@example.com', 'brand new pass').status_code == 200


def test_editing_without_a_password_keeps_the_old_one(client, session):
    admin = make_user(session, email='root@example.com', is_admin=True)
    bob = make_user(session, email='bob@example.com', password='old password')
    body = {'full_name': 'Bob', 'is_admin': False, 'is_active': True, 'permissions': {}, 'password': ''}
    assert client.put(f'/api/admin/users/{bob.id}', json=body, headers=bearer(admin)).status_code == 200
    assert login(client, 'bob@example.com', 'old password').status_code == 200


def test_an_admin_cannot_demote_disable_or_delete_themselves(client, session):
    admin = make_user(session, email='root@example.com', is_admin=True)
    base = {'full_name': 'Root', 'is_admin': True, 'is_active': True, 'permissions': {}}
    for change in ({'is_admin': False}, {'is_active': False}):
        assert client.put(f'/api/admin/users/{admin.id}', json=base | change, headers=bearer(admin)).status_code == 400
    assert client.delete(f'/api/admin/users/{admin.id}', headers=bearer(admin)).status_code == 400
    assert client.put(f'/api/admin/users/{admin.id}', json=base | {'full_name': 'Boss'}, headers=bearer(admin)).status_code == 200


def test_admin_deletes_another_user_and_unknown_ids_are_404(client, session):
    admin = make_user(session, email='root@example.com', is_admin=True)
    bob = make_user(session, email='bob@example.com')
    assert client.delete(f'/api/admin/users/{bob.id}', headers=bearer(admin)).json() == {'ok': True}
    assert 'bob@example.com' not in session.users
    assert client.delete(f'/api/admin/users/{bob.id}', headers=bearer(admin)).status_code == 404


def test_the_user_list_never_includes_password_hashes(client, session):
    admin = make_user(session, email='root@example.com', is_admin=True)
    make_user(session, email='bob@example.com')
    users = client.get('/api/admin/users', headers=bearer(admin)).json()
    assert len(users) == 2 and 'scrypt' not in str(users) and 'password' not in str(users)


# ---- first admin from the environment ------------------------------------------------------------------

def settings_with(monkeypatch, **values):
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        admin_email='', admin_password='', admin_name='Administrator', **values))


def test_first_admin_is_created_from_settings(monkeypatch, session):
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        admin_email='Boss@Example.com', admin_password='first admin pass', admin_name='Boss'))
    auth.ensure_first_admin()
    boss = session.users['boss@example.com']
    assert boss.is_admin and boss.is_active and auth.verify_password('first admin pass', boss.password_hash)


def test_an_existing_account_named_as_admin_is_promoted_and_keeps_its_password(monkeypatch, session):
    make_user(session, email='boss@example.com', password='my own pass', is_active=False)
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        admin_email='boss@example.com', admin_password='something else', admin_name='Boss'))
    auth.ensure_first_admin()
    boss = session.users['boss@example.com']
    assert boss.is_admin and boss.is_active and auth.verify_password('my own pass', boss.password_hash)


def test_nothing_is_created_without_admin_settings(monkeypatch, session):
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(admin_email='', admin_password='', admin_name='x'))
    auth.ensure_first_admin()
    assert session.users == {}


# ---- the real app --------------------------------------------------------------------------------------

def test_every_route_of_the_real_app_requires_sign_in():
    from app.main import app
    open_paths = {'/api/health', '/api/auth/login'}
    client = TestClient(app)
    checked = 0
    # The OpenAPI schema lists every route, including those of included routers (app.routes does not).
    for path, methods in app.openapi()['paths'].items():
        if path in open_paths:
            continue
        for method in methods:
            url = path.replace('{', '').replace('}', '')
            assert client.request(method, url).status_code == 401, f'{method.upper()} {path} is not protected'
            checked += 1
    assert checked > 25


def test_each_area_of_the_real_app_checks_its_own_permission(monkeypatch, session):
    from app import main, ply_routes, po_routes, usage_routes
    from app.main import app

    def no_database():
        raise RuntimeError('the test has no database')   # an allowed request reaches the handler and fails here: a 500, not a 403
    for module in (main, ply_routes, po_routes, usage_routes):
        monkeypatch.setattr(module, 'SessionLocal', no_database)
    client = TestClient(app, raise_server_exceptions=False)
    areas = {'techpacks': '/api/documents', 'purchase_orders': '/api/purchase-orders', 'plies': '/api/plies',
             'usage': '/api/usage/summary', 'marker_plan': '/api/marker-plans/00000000-0000-0000-0000-000000000000'}
    for granted in areas:
        user = make_user(session, email=f'{granted}@example.com', permissions={granted: 'view'})
        for feature, url in areas.items():
            status = client.get(url, headers=bearer(user)).status_code
            assert (status != 403) == (feature == granted), f'{granted} user got {status} for {url}'
