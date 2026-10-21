from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app import po_routes
from app.po_schema import POExtraction, PurchaseOrder


@pytest.fixture
def context(monkeypatch):
    extraction = SimpleNamespace(model_name='test', warnings=[], raw_page_results=[{'page': 1, 'status': 'completed'}],
        extracted_json=POExtraction(orders=[PurchaseOrder(contract_number='TEST', source_pages=[1])],
            processing_complete=True, request_usage=[{'total_tokens': 42}]).model_dump())
    doc = SimpleNamespace(id=uuid4(), original_filename='test.pdf', minio_key='test', tech_pack_id=None,
        status='needs_review', error_message=None, page_count=1, created_at=None, extraction=extraction)
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, model, key): return doc if key == doc.id else None
        def add(self, value): pass
        def commit(self): pass
    monkeypatch.setattr(po_routes, 'SessionLocal', Session)
    monkeypatch.setattr(po_routes, 'put_bytes', lambda *args: None)
    monkeypatch.setattr(po_routes, 'get_bytes', lambda *args: b'%PDF-test')
    monkeypatch.setattr(po_routes, 'process_purchase_order', lambda *args: None)
    app = FastAPI(); app.include_router(po_routes.router)
    return TestClient(app), doc


def test_details_and_json_export(context):
    client, doc = context
    response = client.get(f'/api/purchase-orders/{doc.id}')
    assert response.json()['request_usage'] == [{'total_tokens': 42}]
    assert client.get(f'/api/purchase-orders/{doc.id}/json').json()['orders'][0]['contract_number'] == 'TEST'
    assert client.get(f'/api/purchase-orders/{uuid4()}').status_code == 404


def test_pdf_validation_and_bad_link(context):
    client, _ = context
    assert client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'bad')}).status_code == 400
    assert client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'%PDF-test')}, data={'tech_pack_id': str(uuid4())}).status_code == 404
    response = client.post('/api/purchase-orders/upload', files={'file': ('../x.pdf', b'%PDF-test')})
    assert response.status_code == 202
    assert response.json()['filename'] == 'x.pdf'


def test_upload_limit_and_existing_link(context, monkeypatch):
    client, doc = context
    response = client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'%PDF-test')},
                           data={'tech_pack_id': str(doc.id)})
    assert response.status_code == 202
    assert response.json()['tech_pack_id'] == str(doc.id)
    monkeypatch.setattr(po_routes, 'get_settings', lambda: SimpleNamespace(max_upload_mb=0))
    assert client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'%PDF-test')}).status_code == 413


def test_corrections_preserve_usage_and_raw_evidence(context):
    client, doc = context
    url = f'/api/purchase-orders/{doc.id}/extraction'
    response = client.put(url, json={'orders': [PurchaseOrder(contract_number='CORRECTED', source_pages=[1]).model_dump()]})
    assert response.status_code == 200
    assert doc.extraction.extracted_json['orders'][0]['contract_number'] == 'CORRECTED'
    assert doc.extraction.extracted_json['request_usage'] == [{'total_tokens': 42}]
    assert client.put(url, json={'orders': [], 'processing_complete': True}).status_code == 422


@pytest.mark.parametrize('failure', ['failed', 'missing_page', 'incomplete', 'empty'])
def test_server_blocks_approval_with_incomplete_processing(context, failure):
    client, doc = context
    if failure == 'failed': doc.status = 'failed'
    if failure == 'missing_page': doc.extraction.raw_page_results = []
    if failure == 'incomplete': doc.extraction.extracted_json['processing_complete'] = False
    if failure == 'empty': doc.extraction.extracted_json['orders'] = []
    assert client.post(f'/api/purchase-orders/{doc.id}/approve').status_code == 400


def test_failed_corrections_cannot_enable_approval(context):
    client, doc = context
    doc.status = 'failed'
    response = client.put(f'/api/purchase-orders/{doc.id}/extraction', json={'orders': [PurchaseOrder(contract_number='EDIT').model_dump()]})
    assert response.status_code == 200
    assert doc.status == 'failed'
    assert client.post(f'/api/purchase-orders/{doc.id}/approve').status_code == 400


def test_complete_review_can_approve(context):
    client, doc = context
    assert client.post(f'/api/purchase-orders/{doc.id}/approve').status_code == 200
    assert doc.status == 'approved'


def test_details_refreshes_reference_warning_when_linked_tech_pack_finishes_later(context, monkeypatch):
    client, doc = context
    doc.tech_pack_id = uuid4()
    doc.extraction.extracted_json['orders'][0]['tech_pack_reference'] = 'PO-REFERENCE'
    linked = SimpleNamespace(extraction=SimpleNamespace(extracted_json={'tech_pack_number': 'OTHER-REFERENCE'}))
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, model, key): return linked if key == doc.tech_pack_id else doc
    monkeypatch.setattr(po_routes, 'SessionLocal', Session)
    response = client.get(f'/api/purchase-orders/{doc.id}')
    assert any('differs' in warning for warning in response.json()['extraction']['warnings'])
