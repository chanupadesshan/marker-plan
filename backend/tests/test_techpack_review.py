from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app import main
from app.techpack_schema import DocumentExtraction, Material

USER = SimpleNamespace(id=uuid4(), email='ann@example.com', full_name='Ann Editor')


def setup_review(monkeypatch, status):
    doc = SimpleNamespace(status=status, original_filename='tp.pdf', added=[], extraction=SimpleNamespace(
        extracted_json={'materials': [{'material_code': 'PARTIAL'}]}, warnings=[]))
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args): return doc
        def add(self, value): doc.added.append(value)
        def commit(self): pass
    monkeypatch.setattr(main, 'SessionLocal', Session)
    monkeypatch.setattr(main, 'write_material_rows', lambda *args: None)
    return doc


@pytest.mark.parametrize('status', ['failed', 'processing', 'queued'])
def test_partial_or_processing_techpack_cannot_be_approved(monkeypatch, status):
    doc = setup_review(monkeypatch, status)
    with pytest.raises(HTTPException) as error:
        main.approve_document(uuid4(), USER)
    assert error.value.status_code == 400
    assert doc.added == []


def test_editing_failed_partial_techpack_does_not_enable_approval(monkeypatch):
    doc = setup_review(monkeypatch, 'failed')
    main.save_corrections(uuid4(), DocumentExtraction(materials=[Material(material_code='EDIT')]), USER)
    assert doc.status == 'failed'


def test_techpack_edit_is_logged_with_who_and_what_changed(monkeypatch):
    doc = setup_review(monkeypatch, 'approved')
    doc_id = uuid4()
    main.save_corrections(doc_id, DocumentExtraction(materials=[Material(material_code='EDIT')]), USER)
    entry, = doc.added
    assert (entry.action, entry.user_email, entry.user_name) == ('techpack.edit', 'ann@example.com', 'Ann Editor')
    assert (entry.target_type, entry.target_id, entry.target_name) == ('techpack', str(doc_id), 'tp.pdf')
    assert (entry.details['previous_status'], entry.details['new_status']) == ('approved', 'needs_review')
    paths = [change['path'] for change in entry.details['changes']]
    assert any(path.startswith('materials[') for path in paths)
    assert not any(path.startswith(('request_usage', 'warnings', 'page_tables')) for path in paths)


def test_techpack_approval_is_logged_with_who(monkeypatch):
    doc = setup_review(monkeypatch, 'needs_review')
    assert main.approve_document(uuid4(), USER)['status'] == 'approved'
    entry, = doc.added
    assert (entry.action, entry.user_email, entry.target_name) == ('techpack.approve', 'ann@example.com', 'tp.pdf')
    assert entry.details == {'previous_status': 'needs_review', 'new_status': 'approved'}
