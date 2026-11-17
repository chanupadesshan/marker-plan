"""Audit log: records who edited or approved a Tech Pack or purchase order, and lets admins read it."""
import json
from collections import Counter
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from .auth import require_admin
from .database import SessionLocal
from .models import AuditLog

router = APIRouter(prefix='/api/audit', tags=['Audit'], dependencies=[Depends(require_admin)])

MAX_CHANGES = 200
MAX_VALUE_CHARS = 300
ACTIONS = ('techpack.edit', 'techpack.approve', 'po.edit', 'po.approve',
           'marker_plan.create', 'marker_plan.delete', 'marker_plan.download')


def short(value):
    """
    Purpose: Make a value small enough to store in the log.
    Input: value - any JSON value.
    Output: numbers, text, booleans and None unchanged (text cut at 300 characters); anything else as cut-off JSON text.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text if len(text) <= MAX_VALUE_CHARS else text[:MAX_VALUE_CHARS] + '…'


def row_name(item):
    """
    Purpose: Find what a list row is called, so rows can be matched between two versions.
    Input: item - the row.
    Output: its material code, contract number or size, or None when it has none (or is not a dict).
    """
    return (item.get('material_code') or item.get('contract_number') or item.get('size')) if isinstance(item, dict) else None


def row_label(item, index):
    """
    Purpose: Name one list row so a change reads '[3] R1980' instead of just '[3]'.
    Input: item - the row; index - its 0-based position.
    Output: e.g. '[4]' or '[4 · R1980]' using the row's name when it has one.
    """
    name = row_name(item)
    return f'[{index + 1} · {name}]' if name else f'[{index + 1}]'


def diff_values(before, after, path='', changes=None):
    """
    Purpose: List what differs between two saved versions of the same data.
    Input: before and after - nested dicts and lists; path - the location so far; changes - the list being filled.
    Output: a list of {'path', 'before', 'after'}. Rows edited in place (same row count) are compared field by field, so
    a corrected code reads as one change; when a list gained or lost rows, the rows only in one version are reported
    as added or removed instead of shifting every row.
    Values are cut short, and it stops collecting just past 200 changes.
    """
    changes = [] if changes is None else changes
    if len(changes) > MAX_CHANGES:
        return changes
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            diff_values(before.get(key), after.get(key), f'{path}.{key}' if path else key, changes)
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) == len(after):
            for index, (old, new) in enumerate(zip(before, after)):
                diff_values(old, new, f'{path}{row_label(new, index)}', changes)
        else:
            def canon(item):
                return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            gone, new_only = Counter(map(canon, before)) - Counter(map(canon, after)), Counter(map(canon, after)) - Counter(map(canon, before))
            for index, item in enumerate(before):
                if gone[canon(item)] > 0:
                    gone[canon(item)] -= 1
                    changes.append({'path': f'{path}{row_label(item, index)}', 'before': short(item), 'after': 'removed'})
            for index, item in enumerate(after):
                if new_only[canon(item)] > 0:
                    new_only[canon(item)] -= 1
                    changes.append({'path': f'{path}{row_label(item, index)}', 'before': 'added', 'after': short(item)})
    elif before != after:
        changes.append({'path': path or 'value', 'before': short(before), 'after': short(after)})
    return changes


def without(data, *keys):
    """
    Purpose: Leave out the parts of saved data a person does not edit (usage, warnings, per-page copies) before comparing.
    Input: data - a dict; keys - the names to drop.
    Output: a new dict without those keys.
    """
    return {key: value for key, value in (data or {}).items() if key not in keys}


def edit_details(before, after, previous_status, new_status):
    """
    Purpose: Build the details stored for an edit.
    Input: before and after - the data as it was and as saved; previous_status and new_status - the document's status.
    Output: {'changes': [...up to 200...], 'more_changes': how many more were found beyond those (at least that many),
    'previous_status', 'new_status'}.
    """
    changes = diff_values(before, after)
    return {'changes': changes[:MAX_CHANGES], 'more_changes': max(0, len(changes) - MAX_CHANGES),
            'previous_status': previous_status, 'new_status': new_status}


def record(session, user, action, target_type, target_id, target_name, details=None):
    """
    Purpose: Add one entry to the audit log inside the caller's database transaction, so the action and its log
    entry are saved together or not at all.
    Input: session - the open session; user - who did it; action - one of ACTIONS; target_type - 'techpack' or 'po';
    target_id and target_name - the document's id and file name; details - what changed.
    Output: nothing. The caller commits.
    """
    session.add(AuditLog(user_id=user.id, user_email=user.email, user_name=user.full_name, action=action,
                         target_type=target_type, target_id=str(target_id), target_name=target_name, details=details or {}))


def entry_dict(row):
    """Purpose: One audit row for the API. Input: an AuditLog. Output: a dict with ISO time and all the fields."""
    return {'id': str(row.id), 'created_at': row.created_at.isoformat() if row.created_at else None,
            'user_id': str(row.user_id) if row.user_id else None, 'user_email': row.user_email, 'user_name': row.user_name,
            'action': row.action, 'target_type': row.target_type, 'target_id': row.target_id,
            'target_name': row.target_name, 'details': row.details or {}}


@router.get('')
def list_entries(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), action: str | None = None,
                 user_id: UUID | None = None, search: str | None = Query(None, max_length=100)):
    """
    Purpose: Let an admin read the audit log, newest first.
    Input: limit and offset - paging; action - only this action (one of ACTIONS); user_id - only this person's actions;
    search - text found in the file name or the person's name or email.
    Output: {'total': matching entries, 'items': [...], 'actions': the action names}. Raises 403 for non-admins.
    """
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if user_id:
        conditions.append(AuditLog.user_id == user_id)
    if search and search.strip():
        like = f'%{search.strip()}%'
        conditions.append(or_(AuditLog.target_name.ilike(like), AuditLog.user_email.ilike(like), AuditLog.user_name.ilike(like)))
    with SessionLocal() as session:
        total = session.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
        rows = session.scalars(select(AuditLog).where(*conditions)
                               .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)).all()
        return {'total': total, 'items': [entry_dict(row) for row in rows], 'actions': list(ACTIONS)}
