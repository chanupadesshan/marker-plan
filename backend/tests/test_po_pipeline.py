from types import SimpleNamespace
from uuid import uuid4
import pymupdf
import pytest
from app.po_schema import POPageResult, PurchaseOrder, POSizeRow
from app import po_pipeline


def setup_pipeline(monkeypatch, fail_page=None, kind='purchase_order'):
    doc = SimpleNamespace(id=uuid4(), minio_key='po.pdf', tech_pack_id=None, extraction=None,
                          status='queued', error_message=None, page_count=None)
    events = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args): return doc
        def add(self, value): doc.extraction = value
        def commit(self): pass
        def rollback(self): pass
    class Model:
        def __init__(self): self.request_usage = []
        def extract_po(self, image):
            events.append(('extract', self.current_page))
            self.request_usage.append({'page': self.current_page, 'stage': 'po_extraction'})
            if self.current_page == fail_page: raise RuntimeError('synthetic model failure')
            return POPageResult(page_kind=kind, orders=[PurchaseOrder(contract_number='TEST',
                total_quantity='4', size_rows=[POSizeRow(size='-M', quantity='2')])] if kind == 'purchase_order' else [])
    with pymupdf.open() as pdf:
        pdf.new_page(); pdf.new_page()
        data = pdf.tobytes()
    monkeypatch.setattr(po_pipeline, 'SessionLocal', Session)
    monkeypatch.setattr(po_pipeline, 'OpenRouterVLM', Model)
    monkeypatch.setattr(po_pipeline, 'get_bytes', lambda key: data)
    monkeypatch.setattr(po_pipeline, 'put_bytes', lambda key, *args: events.append(('image', key)))
    monkeypatch.setattr(po_pipeline, 'page_image', lambda *args, **kwargs: b'jpeg')
    return doc, events


def test_all_images_saved_before_inference_and_success(monkeypatch):
    doc, events = setup_pipeline(monkeypatch)
    po_pipeline.process_purchase_order(str(doc.id))
    assert [event[0] for event in events] == ['image', 'image', 'extract', 'extract']
    assert doc.status == 'needs_review'
    assert doc.extraction.extracted_json['processing_complete'] is True
    assert doc.extraction.extracted_json['orders'][0]['source_pages'] == [1, 2]


@pytest.mark.parametrize('failure,completed', [(1, 0), (2, 1)])
def test_failure_keeps_completed_pages_and_usage(monkeypatch, failure, completed):
    doc, events = setup_pipeline(monkeypatch, fail_page=failure)
    po_pipeline.process_purchase_order(str(doc.id))
    assert doc.status == 'failed'
    assert doc.extraction.extracted_json['processing_complete'] is False
    assert len(doc.extraction.extracted_json['page_results']) == completed
    assert len(doc.extraction.extracted_json['request_usage']) == failure
    assert len(doc.extraction.raw_page_results) == 2
    assert 'synthetic model failure' in doc.error_message


def test_non_po_pages_cannot_become_success(monkeypatch):
    doc, _ = setup_pipeline(monkeypatch, kind='other')
    po_pipeline.process_purchase_order(str(doc.id))
    assert doc.status == 'failed'
    assert len(doc.extraction.extracted_json['page_results']) == 2
