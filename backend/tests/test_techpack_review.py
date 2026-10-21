from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app import main
from app.techpack_schema import DocumentExtraction, Material


def setup_review(monkeypatch, status):
    doc = SimpleNamespace(status=status, extraction=SimpleNamespace(
        extracted_json={'materials': [{'material_code': 'PARTIAL'}]}, warnings=[]))
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args): return doc
        def commit(self): pass
    monkeypatch.setattr(main, 'SessionLocal', Session)
    monkeypatch.setattr(main, 'write_material_rows', lambda *args: None)
    return doc


@pytest.mark.parametrize('status', ['failed', 'processing', 'queued'])
def test_partial_or_processing_techpack_cannot_be_approved(monkeypatch, status):
    setup_review(monkeypatch, status)
    with pytest.raises(HTTPException) as error:
        main.approve_document(uuid4())
    assert error.value.status_code == 400


def test_editing_failed_partial_techpack_does_not_enable_approval(monkeypatch):
    doc = setup_review(monkeypatch, 'failed')
    main.save_corrections(uuid4(), DocumentExtraction(materials=[Material(material_code='EDIT')]))
    assert doc.status == 'failed'
