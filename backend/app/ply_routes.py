"""Plies dashboard API: list, add, edit and delete the rows of the plies table."""
from fastapi import APIRouter, HTTPException
from pydantic import field_validator
from sqlalchemy import select
from .database import SessionLocal
from .models import Ply
from .techpack_schema import StrictModel

router = APIRouter(prefix='/api/plies', tags=['Plies'])

MAX_TEXT = 100


# Purpose: The values a user submits when adding or editing a ply row (the id is never sent).
# Input: col_b - a whole number; col_c - a code (required, up to 100 characters); col_d - a value or range, or empty.
# Output: a validated PlyIn with surrounding spaces removed and an empty col_d turned into None.
class PlyIn(StrictModel):
    col_b: int
    col_c: str
    col_d: str | None = None

    @field_validator('col_c')
    @classmethod
    def code_required(cls, value):
        """
        Purpose: Make sure the code is present and not too long.
        Input: value - the submitted col_c text (already stripped).
        Output: the same text, or a ValueError when it is empty or longer than 100 characters.
        """
        if not value:
            raise ValueError('Material is required')
        if len(value) > MAX_TEXT:
            raise ValueError(f'Material must be {MAX_TEXT} characters or fewer')
        return value

    @field_validator('col_d')
    @classmethod
    def empty_to_none(cls, value):
        """
        Purpose: Store a blank col_d as "no value" (NULL) and keep it short.
        Input: value - the submitted col_d text (already stripped), or None.
        Output: None for blank text, otherwise the text; a ValueError when longer than 100 characters.
        """
        if not value:
            return None
        if len(value) > MAX_TEXT:
            raise ValueError(f'Maximum plies must be {MAX_TEXT} characters or fewer')
        return value


def row_dict(row):
    """
    Purpose: Turn a Ply database row into the JSON shape the dashboard uses.
    Input: row - a Ply.
    Output: a dict with id, col_b, col_c and col_d.
    """
    return {'id': row.id, 'col_b': row.col_b, 'col_c': row.col_c, 'col_d': row.col_d}


def find(session, ply_id):
    """
    Purpose: Load one ply row or stop the request with a 404.
    Input: session - a database session; ply_id - the row's id.
    Output: the Ply row. Raises HTTP 404 when it does not exist.
    """
    row = session.get(Ply, ply_id)
    if row is None:
        raise HTTPException(404, 'Ply not found')
    return row


@router.get('')
def list_plies():
    """
    Purpose: List every row of the plies table for the dashboard.
    Input: none.
    Output: a list of {id, col_b, col_c, col_d}, ordered by id.
    """
    with SessionLocal() as session:
        return [row_dict(row) for row in session.scalars(select(Ply).order_by(Ply.id))]


@router.post('', status_code=201)
def add_ply(payload: PlyIn):
    """
    Purpose: Add a new row to the plies table.
    Input: payload - the new values (col_b, col_c and optional col_d).
    Output: the created row including its new id (HTTP 201). Invalid values give a 422 error.
    """
    with SessionLocal() as session:
        row = Ply(col_b=payload.col_b, col_c=payload.col_c, col_d=payload.col_d)
        session.add(row)
        session.commit()
        return row_dict(row)


@router.put('/{ply_id}')
def edit_ply(ply_id: int, payload: PlyIn):
    """
    Purpose: Replace the values of an existing row.
    Input: ply_id - the row's id; payload - the new values (col_b, col_c and optional col_d).
    Output: the updated row. Raises 404 if the row does not exist; invalid values give a 422 error.
    """
    with SessionLocal() as session:
        row = find(session, ply_id)
        row.col_b, row.col_c, row.col_d = payload.col_b, payload.col_c, payload.col_d
        session.commit()
        return row_dict(row)


@router.delete('/{ply_id}')
def delete_ply(ply_id: int):
    """
    Purpose: Permanently delete a row from the plies table.
    Input: ply_id - the row's id.
    Output: {'ok': True}. Raises 404 if the row does not exist.
    """
    with SessionLocal() as session:
        session.delete(find(session, ply_id))
        session.commit()
        return {'ok': True}
