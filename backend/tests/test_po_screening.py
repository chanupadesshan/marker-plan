"""Screening a PO's pages against its Tech Pack before they are extracted in full."""
from types import SimpleNamespace
from uuid import uuid4
import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import BomExtraction, PurchaseOrderDocument, PurchaseOrderExtraction, TechPack
from app.po_schema import POHeader, POPageResult, POSizeRow, PurchaseOrder
from app.po_screening import header_from_text, page_decision, screen_pages, skipped_notes
from app import po_pipeline, po_routes


@compiles(JSONB, 'sqlite')
def sqlite_jsonb(element, compiler, **kwargs):
    return 'JSON'


def test_header_is_read_from_the_text_layer():
    text = 'DRAFT\nContract no\n361592\nteckpack:\nModel ID:\n1655\nQualityID:\nColorID:\n2799\nTotal quantity:\n90'
    assert header_from_text(text) == {'contract_number': '361592', 'model_id': '1655', 'quality_id': None}
    # Another spelling, and a printed quality ID.
    assert header_from_text('Contract no 362928\nModell ID: 1805\nQualityID: 2513')['quality_id'] == '2513'
    assert header_from_text('Combined schedule\nModel ID: 1552\nFabric QualityID: 1648')['quality_id'] == '1648'
    # A page that continues a size table has no header.
    assert header_from_text('Size Quantity\n-C52 32\n-C54 40\n-C56 12 and more size lines') is None


def test_a_page_is_skipped_only_when_a_printed_id_does_not_fit():
    designs = ['1845', '1146']
    assert page_decision({'model_id': '1459', 'quality_id': '1845'}, '1459', designs) == 'include'
    assert page_decision({'model_id': '1459 ', 'quality_id': '1146'}, '1459', designs) == 'include'
    assert page_decision({'model_id': '1459', 'quality_id': None}, '1459', designs) == 'include'
    assert page_decision({'model_id': '1655', 'quality_id': '1845'}, '1459', designs) == 'skip'
    assert page_decision({'model_id': '1459', 'quality_id': '9999'}, '1459', designs) == 'skip'
    # A blank or unreadable ID is never a reason to skip.
    assert page_decision({'model_id': None, 'quality_id': None}, '1459', designs) == 'include'
    assert page_decision({'model_id': '1459', 'quality_id': '9999'}, '1459', []) == 'include'


def pdf_with(texts):
    pdf = pymupdf.open()
    for text in texts:
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
    return pdf


def test_text_pages_are_screened_and_continuation_pages_follow_the_page_before():
    pdf = pdf_with(['Contract no 1\nModel ID: 1459\nQualityID: 1845\nTotal quantity: 90',
                    'Size Quantity -C52 32 -C54 40 -C56 12 more size lines here',
                    'Contract no 2\nModel ID: 1655\nQualityID: 1845\nTotal quantity: 40',
                    'Size Quantity -C52 32 -C54 40 -C56 12 more size lines here',
                    'Contract no 3\nModel ID: 1459\nQualityID:\nColorID: 2799\nTotal quantity: 10'])
    records = screen_pages(pdf, '1459', ['1845'])
    assert [r['decision'] for r in records] == ['include', 'include', 'skip', 'skip', 'include']
    assert [r['source'] for r in records] == ['text', 'inherited', 'text', 'inherited', 'text']
    assert records[3]['model_id'] is None and records[2]['model_id'] == '1655'


def test_pages_without_text_are_read_by_a_small_header_call():
    pdf = pdf_with([None, None, None])
    headers = {1: POHeader(contract_number='1', model_id='1459', quality_id='1845'), 2: POHeader(),
               3: POHeader(contract_number='3', model_id='1552', quality_id='1648')}
    class Model:
        request_usage, current_page, current_group = [], None, None
        def po_header(self, image):
            assert image[:2] == b'\xff\xd8', 'a JPEG of the top of the page is sent'
            self.request_usage.append({'stage': 'po_header', 'page': self.current_page})
            return headers[self.current_page]
    model = Model()
    records = screen_pages(pdf, '1459', ['1845'], model)
    assert [(r['decision'], r['source']) for r in records] == [('include', 'image'), ('include', 'inherited'), ('skip', 'image')]
    assert sorted(use['page'] for use in model.request_usage) == [1, 2, 3]
    # Without a model, or when a read fails, nothing is skipped by guesswork.
    assert [r['decision'] for r in screen_pages(pdf, '1459', ['1845'], None)] == ['include'] * 3
    class Broken(Model):
        def po_header(self, image): raise RuntimeError('model down')
    records = screen_pages(pdf, '1459', ['1845'], Broken())
    assert [(r['decision'], r['source']) for r in records] == [('include', 'unread')] * 3


def test_skipped_notes_name_the_ids_that_were_read():
    raw = [{'page': 1, 'status': 'completed'},
           {'page': 2, 'status': 'skipped', 'screen': {'model_id': '1552', 'quality_id': '1648'}},
           {'page': 3, 'status': 'skipped', 'screen': {'model_id': '1655', 'quality_id': None}}]
    assert skipped_notes(raw) == ['Page 2 skipped (Model ID 1552, Quality ID 1648): it does not match this Tech Pack.',
                                  'Page 3 skipped (Model ID 1655): it does not match this Tech Pack.']
    assert skipped_notes(None) == []


def build(monkeypatch, texts, style='1459', designs=('1845',)):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    tech_pack_id, doc_id = uuid4(), uuid4()
    with sessions() as session:
        session.add(TechPack(id=tech_pack_id, original_filename='tp.pdf', minio_key='tp', sha256='0' * 64, status='approved'))
        session.add(BomExtraction(document_id=tech_pack_id, model_name='m', raw_page_results=[], warnings=[],
                                  extracted_json={'style_number': style, 'design_numbers': list(designs)}))
        session.add(PurchaseOrderDocument(id=doc_id, tech_pack_id=tech_pack_id, original_filename='po.pdf',
                                          minio_key='source', sha256='1' * 64, status='queued'))
        session.commit()
    objects = {'source': pdf_with(texts).tobytes()}
    read = []
    class Model:
        def __init__(self): self.request_usage = []; self.current_page = None
        def extract_po(self, image):
            read.append(self.current_page)
            return POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(
                contract_number=f'C{self.current_page}', model_id=style, quality_id=designs[0], total_quantity='2',
                size_rows=[POSizeRow(size='-M', quantity='2')])])
    monkeypatch.setattr(po_pipeline, 'SessionLocal', sessions)
    monkeypatch.setattr(po_pipeline, 'get_bytes', objects.__getitem__)
    monkeypatch.setattr(po_pipeline, 'put_bytes', lambda key, data, mime: objects.__setitem__(key, data))
    monkeypatch.setattr(po_pipeline, 'OpenRouterVLM', Model)
    monkeypatch.setattr(po_routes, 'SessionLocal', sessions)
    return sessions, doc_id, read, engine


TEXTS = ['Contract no 1\nModel ID: 1459\nQualityID: 1845\nTotal quantity: 90',
         'Contract no 2\nModel ID: 1655\nQualityID: 1845\nTotal quantity: 40',
         'Contract no 3\nModel ID: 1459\nQualityID: 1845\nTotal quantity: 10']


def test_only_matching_pages_are_extracted_and_the_po_can_still_be_approved(monkeypatch):
    sessions, doc_id, read, engine = build(monkeypatch, TEXTS)
    po_pipeline.process_purchase_order(str(doc_id))
    assert sorted(read) == [1, 3]
    with sessions() as session:
        doc = session.get(PurchaseOrderDocument, doc_id)
        assert doc.status == 'needs_review'
        assert [page['status'] for page in doc.extraction.raw_page_results] == ['completed', 'skipped', 'completed']
        assert [order['contract_number'] for order in doc.extraction.extracted_json['orders']] == ['C1', 'C3']
        assert 'Page 2 skipped (Model ID 1655, Quality ID 1845): it does not match this Tech Pack.' in doc.extraction.warnings
        assert po_routes.source_complete(doc)
        detail = po_routes.details(doc_id)
        assert detail['skipped_pages'] == [{'page': 2, 'model_id': '1655', 'quality_id': '1845', 'contract_number': '2'}]
        assert detail['progress']['percent'] == 100
    engine.dispose()


def test_extracting_the_skipped_pages_reads_only_those_pages(monkeypatch):
    sessions, doc_id, read, engine = build(monkeypatch, TEXTS)
    po_pipeline.process_purchase_order(str(doc_id))
    queued = []
    tasks = SimpleNamespace(add_task=lambda function, *args: queued.append((function, args)))
    assert po_routes.extract_skipped(doc_id, tasks)['status'] == 'queued'
    assert queued == [(po_pipeline.process_purchase_order, (str(doc_id), True))] or queued[0][1] == (str(doc_id), True)
    read.clear()
    po_pipeline.process_purchase_order(str(doc_id), True)
    assert read == [2]
    with sessions() as session:
        doc = session.get(PurchaseOrderDocument, doc_id)
        assert doc.status == 'needs_review'
        assert [page['status'] for page in doc.extraction.raw_page_results] == ['completed'] * 3
        assert len(doc.extraction.extracted_json['orders']) == 3
        assert not any('skipped' in warning for warning in doc.extraction.warnings)
    # Nothing is left to extract the second time.
    try:
        po_routes.extract_skipped(doc_id, tasks)
        raise AssertionError('expected a 409')
    except Exception as exc:
        assert getattr(exc, 'status_code', None) == 409
    engine.dispose()


def test_a_po_with_no_matching_page_fails_with_a_clear_reason_and_can_be_extracted_anyway(monkeypatch):
    sessions, doc_id, read, engine = build(monkeypatch, [TEXTS[1], TEXTS[1].replace('Contract no 2', 'Contract no 9')])
    po_pipeline.process_purchase_order(str(doc_id))
    assert read == []
    with sessions() as session:
        doc = session.get(PurchaseOrderDocument, doc_id)
        assert doc.status == 'failed'
        assert 'No page of this PO matches the Tech Pack (style number 1459, Quality IDs 1845)' in doc.error_message
        assert [page['status'] for page in doc.extraction.raw_page_results] == ['skipped', 'skipped']
    tasks = SimpleNamespace(add_task=lambda function, *args: None)
    po_routes.extract_skipped(doc_id, tasks)
    po_pipeline.process_purchase_order(str(doc_id), True)
    assert sorted(read) == [1, 2]
    with sessions() as session:
        assert session.get(PurchaseOrderDocument, doc_id).status == 'needs_review'
    engine.dispose()


def test_a_po_without_a_style_number_to_compare_is_extracted_in_full(monkeypatch):
    sessions, doc_id, read, engine = build(monkeypatch, TEXTS, style=None, designs=('1845',))
    po_pipeline.process_purchase_order(str(doc_id))
    assert sorted(read) == [1, 2, 3]
    engine.dispose()
