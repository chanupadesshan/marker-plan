"""Match Tech Pack materials to the plies table and find each material's maximum ply.

A material such as 'R1371' is related to every plies row whose Column C is the same code,
ignoring a leading 'R' and any colour suffix ('1371', 'R1371', 'R1371-9800' are all related).
The maximum ply is the largest number found in the related rows' Column D, where a range
such as '70-75' counts as its upper end (75).
"""
import re
from sqlalchemy import select
from .models import Ply


def base_code(value):
    """
    Purpose: Reduce a material code to the part used for matching: upper case, without a leading 'R'
    (when a digit follows) and without a colour suffix after a dash.
    Input: value - a code such as 'R1371', '1371' or 'R1936-9800', or None.
    Output: the base code, e.g. '1371' or '1936'; '' when the input is empty.
    """
    text = (value or '').strip().upper()
    text = re.split(r'[-\s]', text, maxsplit=1)[0]
    return re.sub(r'^R(?=\d)', '', text)


def max_ply(value):
    """
    Purpose: Read the largest number from a ply value or range.
    Input: value - Column D text such as '80', '70-75' or '90-100', or None.
    Output: the largest number as an int (or a float when it has decimals); None when there is no number.
    """
    numbers = [float(found.replace(',', '.')) for found in re.findall(r'\d+(?:[.,]\d+)?', value or '')]
    if not numbers:
        return None
    top = max(numbers)
    return int(top) if top == int(top) else top


def material_codes(extraction):
    """
    Purpose: Collect the distinct material codes of a Tech Pack extraction, from the combined list and the page tables.
    Input: extraction - the saved extraction as a dict (with 'materials' and/or 'page_tables').
    Output: a set of material codes exactly as printed (empty codes are skipped).
    """
    rows = list(extraction.get('materials') or [])
    for table in extraction.get('page_tables') or []:
        rows.extend(table.get('materials') or [])
    return {row['material_code'] for row in rows if row.get('material_code')}


def ply_info_for(session, extraction):
    """
    Purpose: For every material in an extraction, find the related plies rows and their maximum ply.
    A broken lookup (for example a missing plies table) never stops a Tech Pack from loading; it just returns nothing.
    Input: session - a database session; extraction - the saved Tech Pack extraction as a dict.
    Output: a dict keyed by material code, only for codes with at least one related plies row:
    {'max_ply': the largest Column D number or None, 'matches': [{'id', 'col_c', 'col_d'}, ...]}.
    """
    codes = material_codes(extraction or {})
    if not codes:
        return {}
    try:
        rows = session.scalars(select(Ply).order_by(Ply.id)).all()
    except Exception:
        session.rollback()
        return {}
    by_base = {}
    for row in rows:
        by_base.setdefault(base_code(row.col_c), []).append(row)
    info = {}
    for code in sorted(codes):
        matches = by_base.get(base_code(code)) if base_code(code) else None
        if not matches:
            continue
        values = [max_ply(row.col_d) for row in matches]
        values = [value for value in values if value is not None]
        info[code] = {'max_ply': max(values) if values else None,
                      'matches': [{'id': row.id, 'col_c': row.col_c, 'col_d': row.col_d} for row in matches]}
    return info
