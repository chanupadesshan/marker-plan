"""User management API for admins: list, create, edit (details, role, permissions, password) and delete users."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import (AuthModel, FEATURES, LEVELS, User, clean_email, clean_name, clean_password, clean_permissions,
                   hash_password, require_admin, user_dict)
from .database import SessionLocal

router = APIRouter(prefix='/api/admin', tags=['Admin'])


# Purpose: The fields shared by creating and editing a user.
# Input: full_name; is_admin (full access); permissions (feature -> 'none' | 'view' | 'edit', ignored for admins).
# Output: validated values with a trimmed name and a cleaned permissions map.
class UserFields(AuthModel):
    full_name: str
    is_admin: bool = False
    permissions: dict[str, str | None] = {}

    @field_validator('full_name')
    @classmethod
    def valid_name(cls, value):
        """Purpose: Require a name. Input: the submitted text. Output: it trimmed, or a ValueError."""
        return clean_name(value)

    @field_validator('permissions')
    @classmethod
    def valid_permissions(cls, value):
        """Purpose: Reject unknown features and levels. Input: the submitted map. Output: the cleaned map, or a ValueError."""
        return clean_permissions(value)


# Purpose: What an admin submits to create a user. Input: email and password plus the shared fields. Output: a NewUserIn.
class NewUserIn(UserFields):
    email: str
    password: str

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        """Purpose: Require a plausible email. Input: the submitted text. Output: it lower-cased, or a ValueError."""
        return clean_email(value)

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        """Purpose: Require a sensible password. Input: the text. Output: it, or a ValueError."""
        return clean_password(value)


# Purpose: What an admin submits to change a user. Input: the shared fields, is_active, and an optional new password
# (leave out to keep the current one). The email cannot be changed. Output: an EditUserIn.
class EditUserIn(UserFields):
    is_active: bool = True
    password: str | None = None

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        """Purpose: Check a new password when one is given. Input: the text or None/empty. Output: it, or None to keep the old one."""
        return clean_password(value) if value else None


def find(session, user_id):
    """
    Purpose: Load one user or stop the request with a 404.
    Input: session - a database session; user_id - the user's id.
    Output: the User. Raises HTTP 404 when it does not exist.
    """
    row = session.get(User, user_id)
    if row is None:
        raise HTTPException(404, 'User not found')
    return row


@router.get('/features')
def list_features(admin: User = Depends(require_admin)):
    """
    Purpose: Tell the Users page which permissions can be granted.
    Input: none.
    Output: {'features': [{key, label}], 'levels': ['view', 'edit']}.
    """
    return {'features': [{'key': key, 'label': label} for key, label in FEATURES.items()], 'levels': list(LEVELS)}


@router.get('/users')
def list_users(admin: User = Depends(require_admin)):
    """
    Purpose: List every user for the Users page.
    Input: none.
    Output: a list of user details (never password hashes), oldest first.
    """
    with SessionLocal() as session:
        return [user_dict(row) | {'created_at': row.created_at.isoformat() if row.created_at else None}
                for row in session.scalars(select(User).order_by(User.created_at))]


@router.post('/users', status_code=201)
def create_user(payload: NewUserIn, admin: User = Depends(require_admin)):
    """
    Purpose: Create a user with a role and permissions.
    Input: payload - email, full_name, password, is_admin and permissions.
    Output: the new user (HTTP 201). Raises 409 when the email is taken, 422 for invalid input.
    """
    with SessionLocal() as session:
        if session.scalar(select(User).where(User.email == payload.email)) is not None:
            raise HTTPException(409, 'A user with this email already exists')
        row = User(email=payload.email, full_name=payload.full_name, password_hash=hash_password(payload.password),
                   is_admin=payload.is_admin, permissions=payload.permissions)
        session.add(row)
        try:
            session.commit()
        except IntegrityError:  # The same email was added at the same moment.
            raise HTTPException(409, 'A user with this email already exists')
        return user_dict(row)


@router.put('/users/{user_id}')
def edit_user(user_id: uuid.UUID, payload: EditUserIn, admin: User = Depends(require_admin)):
    """
    Purpose: Change a user's name, role, permissions, active state and (optionally) password.
    Input: user_id; payload - the new values. Admins cannot remove their own admin rights or disable themselves,
    so there is always an admin who can sign in.
    Output: the updated user. Raises 400 for those self-changes, 404 if the user does not exist, 422 for invalid input.
    """
    with SessionLocal() as session:
        row = find(session, user_id)
        if row.id == admin.id and not (payload.is_admin and payload.is_active):
            raise HTTPException(400, 'You cannot remove your own admin rights or disable your own account')
        row.full_name, row.is_admin, row.is_active = payload.full_name, payload.is_admin, payload.is_active
        row.permissions = payload.permissions
        if payload.password:
            row.password_hash = hash_password(payload.password)
        session.commit()
        return user_dict(row)


@router.delete('/users/{user_id}')
def delete_user(user_id: uuid.UUID, admin: User = Depends(require_admin)):
    """
    Purpose: Permanently delete a user (their documents are kept).
    Input: user_id.
    Output: {'ok': True}. Raises 400 when deleting yourself, 404 if the user does not exist.
    """
    with SessionLocal() as session:
        row = find(session, user_id)
        if row.id == admin.id:
            raise HTTPException(400, 'You cannot delete your own account')
        session.delete(row)
        session.commit()
        return {'ok': True}
