from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import audit
from app.audit import diff_values, edit_details, short, without


def material(code, qty):
    return {'material_code': code, 'quantity': qty, 'colorways': [{'code': 'A', 'value': 'x'}]}


def test_in_place_edits_name_the_row_and_the_field():
    changes = diff_values({'materials': [material('R1', '1'), material('R2', '2')]},
                          {'materials': [material('R1', '1'), material('R2', '3')]})
    assert changes == [{'path': 'materials[2 · R2].quantity', 'before': '2', 'after': '3'}]


def test_removed_and_added_rows_do_not_shift_the_rows_after_them():
    before = {'materials': [material('R1', '1'), material('R2', '2'), material('R3', '3')]}
    after = {'materials': [material('R1', '1'), material('R3', '3'), material('R4', '4'), material('R5', '5')]}
    changes = diff_values(before, after)
    assert [(change['path'], change['before'], change['after']) for change in changes] == [
        ('materials[2 · R2]', changes[0]['before'], 'removed'), ('materials[3 · R4]', 'added', changes[1]['after']),
        ('materials[4 · R5]', 'added', changes[2]['after'])]
    assert 'R2' in changes[0]['before'] and 'R4' in changes[1]['after']
    # A shorter list reports only the missing row, and the rows after it are not blamed.
    only_removed = diff_values(before, {'materials': [material('R1', '1'), material('R3', '3')]})
    assert [change['path'] for change in only_removed] == ['materials[2 · R2]']


def test_identical_data_has_no_changes_and_status_is_recorded():
    assert diff_values({'a': [1, {'b': 2}]}, {'a': [1, {'b': 2}]}) == []
    details = edit_details({'a': 1}, {'a': 1}, 'approved', 'needs_review')
    assert details == {'changes': [], 'more_changes': 0, 'previous_status': 'approved', 'new_status': 'needs_review'}


def test_long_values_are_cut_and_big_edits_are_capped():
    assert len(short('x' * 1000)) == audit.MAX_VALUE_CHARS + 1
    assert short(None) is None and short(5) == 5
    details = edit_details({'rows': list(range(500))}, {'rows': list(range(1, 501))}, 'needs_review', 'needs_review')
    assert len(details['changes']) == audit.MAX_CHANGES and details['more_changes'] >= 1


def test_without_drops_only_the_named_keys():
    assert without({'a': 1, 'request_usage': [], 'warnings': []}, 'request_usage', 'warnings') == {'a': 1}
    assert without(None, 'a') == {}


def test_the_log_is_closed_to_signed_out_visitors_and_non_admins():
    app = FastAPI(); app.include_router(audit.router)
    client = TestClient(app)
    assert client.get('/api/audit').status_code == 401
    from app.auth import require_user
    app.dependency_overrides[require_user] = lambda: SimpleNamespace(id=uuid4(), is_admin=False)
    assert client.get('/api/audit').status_code == 403
