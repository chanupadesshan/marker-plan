"""Sign-in API: log in, who am I, and the dependencies that protect the other routes by permission."""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from .config import get_settings
from .database import SessionLocal
from .models import User

router = APIRouter(prefix='/api/auth', tags=['Auth'])

MIN_PASSWORD = 8
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
# scrypt cost: ~16 MB of memory per hash, which is slow enough to resist guessing but fast for one sign-in.
SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1}


def hash_password(password):
    """
    Purpose: Turn a password into a salted one-way hash that is safe to store.
    Input: password - the plain text.
    Output: a string 'scrypt$<salt>$<hash>' (both parts base64).
    """
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def verify_password(password, stored):
    """
    Purpose: Check a password against a stored hash without leaking timing information.
    Input: password - the plain text; stored - a string made by hash_password.
    Output: True when they match, otherwise False (also False for a malformed hash).
    """
    try:
        scheme, salt, digest = stored.split('$')
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **SCRYPT)
    except ValueError:
        return False
    return scheme == 'scrypt' and hmac.compare_digest(actual, expected)


def b64(data):
    """Purpose: URL-safe base64 without padding. Input: bytes. Output: str."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def unb64(text):
    """Purpose: Reverse b64. Input: str. Output: bytes."""
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sign(message):
    """Purpose: HMAC-SHA256 of a message with the auth secret. Input: str. Output: bytes."""
    return hmac.new(get_settings().auth_secret.encode(), message.encode(), hashlib.sha256).digest()


def make_token(user_id):
    """
    Purpose: Create a signed login token that expires after auth_token_hours.
    Input: user_id - the user's id.
    Output: a string 'payload.signature' (payload holds the user id and expiry time).
    """
    payload = b64(json.dumps({'sub': str(user_id), 'exp': int(time.time()) + get_settings().auth_token_hours * 3600}).encode())
    return payload + '.' + b64(sign(payload))


def read_token(token):
    """
    Purpose: Check a token's signature and expiry.
    Input: token - a string made by make_token.
    Output: the user id it was issued for, or None when it is forged, malformed or expired.
    """
    try:
        payload, signature = token.split('.')
        if not hmac.compare_digest(unb64(signature), sign(payload)):
            return None
        claims = json.loads(unb64(payload))
        return claims['sub'] if claims['exp'] > time.time() else None
    except (ValueError, KeyError, TypeError):
        return None


# The areas an admin can grant, with the names shown on screen. Each is granted as 'view' (read) or 'edit' (read and change).
FEATURES = {'techpacks': 'Tech Packs', 'purchase_orders': 'Purchase Orders', 'marker_plan': 'Marker Plan',
            'plies': 'Plies', 'usage': 'Usage'}
LEVELS = ('view', 'edit')


def effective_permissions(user):
    """
    Purpose: Work out what a user may do.
    Input: user - a User.
    Output: a dict feature -> 'view' | 'edit' for the features they have; admins have 'edit' on every feature.
    """
    if user.is_admin:
        return {feature: 'edit' for feature in FEATURES}
    return {feature: level for feature, level in (user.permissions or {}).items() if feature in FEATURES and level in LEVELS}


def can(user, feature, level):
    """
    Purpose: Check one permission. Input: user; feature - a key of FEATURES; level - 'view' or 'edit'.
    Output: True when allowed ('edit' also allows 'view').
    """
    have = effective_permissions(user).get(feature)
    return have == 'edit' or (have == 'view' and level == 'view')


def user_dict(user):
    """Purpose: The public details of a user (never the hash). Input: a User. Output: dict with id, email, full_name, is_admin, is_active and permissions."""
    return {'id': str(user.id), 'email': user.email, 'full_name': user.full_name, 'is_admin': user.is_admin,
            'is_active': user.is_active, 'permissions': effective_permissions(user)}


def require_user(authorization: str | None = Header(default=None)):
    """
    Purpose: Route dependency that only lets signed-in people through.
    Input: the 'Authorization: Bearer <token>' header.
    Output: the User. Raises 401 when the token is missing, invalid or expired, or the user no longer exists or was disabled.
    """
    scheme, _, token = (authorization or '').partition(' ')
    user_id = read_token(token) if scheme.lower() == 'bearer' else None
    if user_id is not None:
        with SessionLocal() as session:
            try:
                user = session.get(User, user_id)
            except (ValueError, TypeError):
                user = None
            if user is not None and user.is_active:
                return user
    raise HTTPException(401, 'Please sign in', headers={'WWW-Authenticate': 'Bearer'})


def require_admin(user: User = Depends(require_user)):
    """
    Purpose: Route dependency that only lets admins through.
    Input: the signed-in User.
    Output: the User. Raises 403 for anyone who is not an admin.
    """
    if not user.is_admin:
        raise HTTPException(403, 'Only an admin can do this')
    return user


def needs(feature):
    """
    Purpose: Build a route dependency for one feature: reading (GET) needs 'view' and anything that changes data needs 'edit'.
    Input: feature - a key of FEATURES.
    Output: a dependency returning the User; it raises 401 when not signed in and 403 when the permission is missing.
    """
    def check(request: Request, user: User = Depends(require_user)):
        level = 'view' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'edit'
        if not can(user, feature, level):
            raise HTTPException(403, f'You do not have {level} access to {FEATURES[feature]}')
        return user
    return check


def clean_email(value):
    """Purpose: Require a plausible email. Input: the submitted text. Output: it trimmed and lower-cased, or a ValueError."""
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL_PATTERN.match(value):
        raise ValueError('Enter a valid email address')
    return value


def clean_name(value):
    """Purpose: Require a name of up to 120 characters. Input: the submitted text. Output: it trimmed, or a ValueError."""
    value = value.strip()
    if not value or len(value) > 120:
        raise ValueError('Name is required and must be 120 characters or fewer')
    return value


def clean_password(value):
    """Purpose: Require a sensible password length. Input: the text, kept exactly as typed. Output: it, or a ValueError."""
    if len(value) < MIN_PASSWORD:
        raise ValueError(f'Password must be at least {MIN_PASSWORD} characters')
    if len(value) > 200:
        raise ValueError('Password must be 200 characters or fewer')
    return value


def clean_permissions(value):
    """
    Purpose: Check a permissions map. Input: a dict feature -> level. Output: the same dict without entries set to
    'none'/empty; a ValueError for an unknown feature or level.
    """
    cleaned = {}
    for feature, level in value.items():
        if feature not in FEATURES:
            raise ValueError(f'Unknown feature: {feature}')
        if level in (None, '', 'none'):
            continue
        if level not in LEVELS:
            raise ValueError(f'Permission for {FEATURES[feature]} must be none, view or edit')
        cleaned[feature] = level
    return cleaned


# Purpose: Base for the sign-in bodies: unknown fields are rejected, and spaces are kept in passwords
# (only the email and name are trimmed).
class AuthModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


# Purpose: What a person submits to log in. Input: email and password. Output: a LoginIn.
class LoginIn(AuthModel):
    email: str
    password: str = Field(max_length=200)


@router.post('/login')
def login(payload: LoginIn):
    """
    Purpose: Sign a person in.
    Input: payload - email and password.
    Output: {'token', 'user'}. Raises 401 with the same message whether the email or the password is wrong,
    and 403 when the password is right but an admin has disabled the account.
    """
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == payload.email.strip().lower()))
        # Hash even for an unknown email, so response time does not reveal which emails exist.
        stored = user.password_hash if user else DUMMY_HASH
        if not verify_password(payload.password, stored) or user is None:
            raise HTTPException(401, 'Incorrect email or password')
        if not user.is_active:
            raise HTTPException(403, 'This account has been disabled. Ask an admin for access.')
        return {'token': make_token(user.id), 'user': user_dict(user)}


@router.get('/me')
def me(user: User = Depends(require_user)):
    """
    Purpose: Tell the page who is signed in and what they may use (also confirms a stored token is still valid).
    Input: the Authorization header.
    Output: {'user': {id, email, full_name, is_admin, is_active, permissions}}. Raises 401 when not signed in.
    """
    return {'user': user_dict(user)}


DUMMY_HASH = hash_password('not-a-real-password')


def prepare_users_table(engine):
    """
    Purpose: Add the role columns to a users table created before roles existed (create_all never alters tables).
    Input: engine - the database engine.
    Output: nothing; safe to run on every start.
    """
    with engine.begin() as connection:
        for statement in (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB NOT NULL DEFAULT '{}'::jsonb",
        ):
            connection.execute(text(statement))


def prepare_upload_owner_columns(engine):
    """
    Purpose: Add the uploaded_by column to Tech Pack and PO tables created before per-user usage existed.
    Input: engine - the database engine.
    Output: nothing; safe to run on every start. Older uploads keep an empty uploaded_by.
    """
    with engine.begin() as connection:
        for table in ('tech_packs', 'purchase_order_documents'):
            connection.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL"))


def ensure_first_admin():
    """
    Purpose: Make sure the admin named in ADMIN_EMAIL / ADMIN_PASSWORD exists and is an active admin. An existing
    account keeps its password; this is also the way back in if every admin is locked out.
    Input: none (reads the settings).
    Output: nothing; does nothing when either setting is empty.
    """
    settings = get_settings()
    if not settings.admin_email.strip() or not settings.admin_password:
        return
    email = clean_email(settings.admin_email)
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            session.add(User(email=email, full_name=settings.admin_name.strip() or 'Administrator',
                             password_hash=hash_password(clean_password(settings.admin_password)), is_admin=True, is_active=True))
        else:
            user.is_admin, user.is_active = True, True
        session.commit()