from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app import po_routes
from app.po_schema import POExtraction, PurchaseOrder, POPageResult
from app.po_merge import combine_po_pages


@pytest.fixture
def context(monkeypatch):
    content = combine_po_pages([(1, POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(contract_number='TEST')]))])
    content.processing_complete = True
    content.request_usage = [{'total_tokens': 42}]
    extraction = SimpleNamespace(model_name='test', warnings=[], raw_page_results=[{'page': 1, 'status': 'completed'}],
        extracted_json=content.model_dump())
    doc = SimpleNamespace(id=uuid4(), original_filename='test.pdf', minio_key='test', tech_pack_id=None,
        status='needs_review', error_message=None, page_count=1, created_at=None, extraction=extraction, added=[])
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, model, key, **kwargs): return doc if key == doc.id else None
        def add(self, value): doc.added.append(value)
        def commit(self): pass
    monkeypatch.setattr(po_routes, 'SessionLocal', Session)
    monkeypatch.setattr(po_routes, 'put_bytes', lambda *args: None)
    monkeypatch.setattr(po_routes, 'get_bytes', lambda *args: b'%PDF-test')
    monkeypatch.setattr(po_routes, 'process_purchase_order', lambda *args: None)
    app = FastAPI(); app.include_router(po_routes.router)
    app.dependency_overrides[po_routes.require_user] = lambda: SimpleNamespace(id=uuid4(), email='ann@example.com', full_name='Ann Editor')
    return TestClient(app), doc


def test_details_and_json_export(context):
    client, doc = context
    response = client.get(f'/api/purchase-orders/{doc.id}')
    assert response.json()['request_usage'] == [{'total_tokens': 42}]
    assert client.get(f'/api/purchase-orders/{doc.id}/json').json()['orders'][0]['contract_number'] == 'TEST'
    assert client.get(f'/api/purchase-orders/{uuid4()}').status_code == 404


def test_po_progress_counts_completed_pages_and_keeps_retry_progress(context):
    client, doc = context
    doc.status = 'processing'
    doc.page_count = 3
    doc.extraction.raw_page_results = [{'page': 1, 'status': 'completed'},
        {'page': 2, 'status': 'pending', 'result': {'orders': []}}]
    progress = client.get(f'/api/purchase-orders/{doc.id}').json()['progress']
    assert progress == {'stage': 'extracting', 'completed_pages': 1, 'total_pages': 3, 'percent': 33}
    doc.status = 'queued'
    assert client.get(f'/api/purchase-orders/{doc.id}').json()['progress']['stage'] == 'queued'


def test_opening_saved_po_refreshes_false_total_warning_without_changing_approval(context):
    from copy import deepcopy
    client, doc = context
    doc.status = 'approved'
    saved_order = doc.extraction.extracted_json['orders'][0]
    saved_order.update(contract_number='355800', total_quantity='1,410',
                       size_rows=[{'size': 'S', 'quantity': '1410'}],
                       warnings=['Size quantity sum differs from the printed total quantity', 'Check colour'])
    original = deepcopy(doc.extraction.extracted_json)
    for path in [f'/api/purchase-orders/{doc.id}', f'/api/purchase-orders/{doc.id}/json']:
        payload = client.get(path).json()
        result = payload.get('extraction', payload)['orders'][0]
        assert result['warnings'] == ['Check colour']
        assert result['total_quantity'] == '1,410'
    assert doc.status == 'approved'
    assert doc.extraction.extracted_json == original


def test_list_returns_searchable_identifiers_without_full_extraction(context, monkeypatch):
    client, doc = context
    doc.extraction.extracted_json['orders'][0].update(tech_pack_reference='16404', size_rows=[{'size': '-M', 'quantity': '2'}])
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def scalars(self, *args, **kwargs): return SimpleNamespace(all=lambda: [doc])
    monkeypatch.setattr(po_routes, 'SessionLocal', Session)
    items = client.get('/api/purchase-orders').json()
    assert len(items) == 1
    assert items[0]['filename'] == 'test.pdf'
    assert items[0]['contract_numbers'] == ['TEST'] and items[0]['contract_count'] == 1
    assert items[0]['tech_pack_references'] == ['16404']
    assert 'extraction' not in items[0]


def test_existing_broader_extraction_remains_readable_with_new_field_scope(context):
    client, doc = context
    order = doc.extraction.extracted_json['orders'][0]
    order.update(registered_date='old-date', shipping_date=None, total_amount='0,00', currency=None)
    order['size_rows'] = [{'size': '-M', 'quantity': '2', 'unit_price': None, 'amount': None, 'currency': None, 'source_page': 1}]
    response = client.get(f'/api/purchase-orders/{doc.id}')
    assert response.status_code == 200
    result = response.json()['extraction']['orders'][0]
    assert result['contract_number'] == 'TEST'
    assert 'registered_date' not in result
    assert result['size_rows'] == [{'size': '-M', 'quantity': '2', 'source_page': 1}]


def test_pdf_validation_and_bad_link(context):
    client, doc = context
    doc.status = 'approved'
    assert client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'bad')}).status_code == 400
    assert client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'%PDF-test')}, data={'tech_pack_id': str(uuid4())}).status_code == 404
    response = client.post('/api/purchase-orders/upload', files={'file': ('../x.pdf', b'%PDF-test')}, data={'tech_pack_id': str(doc.id)})
    assert response.status_code == 202
    assert response.json()['filename'] == 'x.pdf'


def test_upload_requires_an_approved_tech_pack(context):
    client, doc = context
    send = lambda **data: client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'%PDF-test')}, data=data)
    assert send().status_code == 400
    for status in ('queued', 'processing', 'needs_review', 'failed'):
        doc.status = status
        assert send(tech_pack_id=str(doc.id)).status_code == 409
    doc.status = 'approved'
    assert send(tech_pack_id=str(doc.id)).status_code == 202


def test_upload_limit_and_existing_link(context, monkeypatch):
    client, doc = context
    doc.status = 'approved'
    response = client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'%PDF-test')},
                           data={'tech_pack_id': str(doc.id)})
    assert response.status_code == 202
    assert response.json()['tech_pack_id'] == str(doc.id)
    monkeypatch.setattr(po_routes, 'get_settings', lambda: SimpleNamespace(max_upload_mb=0))
    assert client.post('/api/purchase-orders/upload', files={'file': ('x.pdf', b'%PDF-test')}).status_code == 413


def link_tech_pack(doc, monkeypatch, style='1459', design='1845', designs=None):
    linked = SimpleNamespace(extraction=SimpleNamespace(extracted_json={'style_number': style, 'design_number': design,
        'design_numbers': designs if designs is not None else ([design] if design else [])}))
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, model, key, **kwargs): return doc if key == doc.id else linked
        def add(self, value): doc.added.append(value)
        def commit(self): pass
    monkeypatch.setattr(po_routes, 'SessionLocal', Session)
    doc.tech_pack_id = uuid4()


def test_ids_that_differ_from_the_tech_pack_block_approval(context, monkeypatch):
    client, doc = context
    link_tech_pack(doc, monkeypatch)
    doc.extraction.extracted_json['orders'][0].update(model_id='1459', quality_id='9999')
    detail = client.get(f'/api/purchase-orders/{doc.id}').json()
    assert detail['approval_ready'] is False
    assert detail['id_mismatches'] == [
        'ID mismatch: Contract TEST: Quality ID 9999 does not match the Tech Pack Quality ID 1845']
    response = client.post(f'/api/purchase-orders/{doc.id}/approve')
    assert response.status_code == 400 and 'Quality ID 9999' in response.json()['detail']
    assert doc.status == 'needs_review'
    doc.extraction.extracted_json['orders'][0].update(model_id='1459 ', quality_id='1845')
    assert client.get(f'/api/purchase-orders/{doc.id}').json()['id_mismatches'] == []
    assert client.post(f'/api/purchase-orders/{doc.id}/approve').status_code == 200


def test_a_po_may_use_any_design_of_a_multi_design_tech_pack(context, monkeypatch):
    client, doc = context
    link_tech_pack(doc, monkeypatch, design=None, designs=['1845', '1146', '1142'])
    order = doc.extraction.extracted_json['orders'][0]
    order.update(model_id='1459', quality_id='1146')
    assert client.get(f'/api/purchase-orders/{doc.id}').json()['id_mismatches'] == []
    order.update(quality_id='9999')
    assert client.get(f'/api/purchase-orders/{doc.id}').json()['id_mismatches'] == [
        'ID mismatch: Contract TEST: Quality ID 9999 does not match the Tech Pack Quality IDs 1845, 1146, 1142']


def test_id_check_sorts_each_po_by_how_its_ids_compare(context, monkeypatch):
    client, doc = context
    link_tech_pack(doc, monkeypatch)
    order = doc.extraction.extracted_json['orders'][0]
    check = lambda: client.get(f'/api/purchase-orders/{doc.id}').json()['id_check']
    order.update(model_id=None, quality_id=None)
    assert check() == 'unchecked'
    order.update(model_id='1459', quality_id=None)
    assert check() == 'no_design'
    order.update(quality_id='1845')
    assert check() == 'match'
    order.update(quality_id='9999')
    assert check() == 'mismatch'
    order.update(model_id='1655', quality_id=None)
    assert check() == 'mismatch'
    doc.tech_pack_id = None
    assert check() == 'unchecked'


def test_missing_ids_are_not_treated_as_a_mismatch(context, monkeypatch):
    client, doc = context
    link_tech_pack(doc, monkeypatch)
    assert client.post(f'/api/purchase-orders/{doc.id}/approve').status_code == 200


def test_corrections_preserve_usage_and_raw_evidence(context):
    client, doc = context
    url = f'/api/purchase-orders/{doc.id}/extraction'
    response = client.put(url, json={'orders': [PurchaseOrder(contract_number='CORRECTED', source_pages=[1]).model_dump()]})
    assert response.status_code == 200
    assert doc.extraction.extracted_json['orders'][0]['contract_number'] == 'CORRECTED'
    assert doc.extraction.extracted_json['request_usage'] == [{'total_tokens': 42}]
    assert client.put(url, json={'orders': [], 'processing_complete': True}).status_code == 422


def audit_rows(doc):
    return [entry for entry in doc.added if entry.__class__.__name__ == 'AuditLog']


def test_edit_and_approval_are_logged_with_who_and_what(context):
    client, doc = context
    url = f'/api/purchase-orders/{doc.id}'
    edit = client.put(f'{url}/extraction', json={'orders': [PurchaseOrder(contract_number='CORRECTED', source_pages=[1]).model_dump()]})
    assert edit.status_code == 200
    assert client.post(f'{url}/approve').status_code == 200
    edit_entry, approve_entry = audit_rows(doc)
    assert (edit_entry.action, edit_entry.user_email, edit_entry.user_name) == ('po.edit', 'ann@example.com', 'Ann Editor')
    assert (edit_entry.target_type, edit_entry.target_id, edit_entry.target_name) == ('po', str(doc.id), 'test.pdf')
    assert {'path': 'orders[1 · CORRECTED].contract_number', 'before': 'TEST', 'after': 'CORRECTED'} in edit_entry.details['changes']
    assert edit_entry.details['previous_status'] == 'needs_review'
    assert approve_entry.action == 'po.approve' and approve_entry.details == {'previous_status': 'needs_review', 'new_status': 'approved'}


def test_rejected_edit_and_approval_are_not_logged(context):
    client, doc = context
    doc.extraction.extracted_json['orders'] = []
    assert client.post(f'/api/purchase-orders/{doc.id}/approve').status_code == 400
    assert client.put(f'/api/purchase-orders/{doc.id}/extraction', json={'orders': [PurchaseOrder(source_pages=[9]).model_dump()]}).status_code == 400
    assert audit_rows(doc) == []


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


def test_only_failed_po_can_queue_a_retry(context):
    client, doc = context
    url = f'/api/purchase-orders/{doc.id}/retry'
    assert client.post(url).status_code == 409
    doc.status = 'failed'
    assert client.post(url).status_code == 202
    assert doc.status == 'queued'
    assert client.post(url).status_code == 409
    assert doc.extraction.extracted_json['request_usage'] == [{'total_tokens': 42}]


def test_retry_does_not_silently_overwrite_manual_corrections(context):
    client, doc = context
    doc.status = 'failed'
    doc.extraction.extracted_json['orders'][0]['contract_number'] = 'MANUAL-CORRECTION'
    response = client.post(f'/api/purchase-orders/{doc.id}/retry')
    assert response.status_code == 409
    assert doc.extraction.extracted_json['orders'][0]['contract_number'] == 'MANUAL-CORRECTION'


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
