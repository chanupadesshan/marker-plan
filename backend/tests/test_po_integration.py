"""Exercise real ORM commits/reloads without a live DB, storage or paid model call."""
from types import SimpleNamespace
from uuid import uuid4
import pymupdf
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.models import AuditLog, PurchaseOrderDocument
from app.po_schema import POPageResult, PurchaseOrder, POSizeRow
from app import po_pipeline, po_routes


@compiles(JSONB, 'sqlite')
def sqlite_jsonb(element, compiler, **kwargs):
    return 'JSON'


def test_po_pipeline_can_reload_and_approve_after_real_commits(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    doc_id = uuid4()
    with sessions() as session:
        session.add(PurchaseOrderDocument(id=doc_id, original_filename='synthetic.pdf',
            minio_key='source', sha256='0' * 64, status='queued'))
        session.commit()
    with pymupdf.open() as pdf:
        pdf.new_page(); pdf.new_page()
        objects = {'source': pdf.tobytes()}
    class Model:
        def __init__(self): self.request_usage = []
        def extract_po(self, image):
            self.request_usage.append({'page': self.current_page, 'total_tokens': 10})
            return POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(
                contract_number=f'SYNTHETIC-{self.current_page}', total_quantity='2',
                size_rows=[POSizeRow(size='-M', quantity='2')])])
    monkeypatch.setattr(po_pipeline, 'SessionLocal', sessions)
    monkeypatch.setattr(po_pipeline, 'get_bytes', objects.__getitem__)
    monkeypatch.setattr(po_pipeline, 'put_bytes', lambda key, data, mime: objects.__setitem__(key, data))
    monkeypatch.setattr(po_pipeline, 'OpenRouterVLM', Model)
    monkeypatch.setattr(po_routes, 'SessionLocal', sessions)
    po_pipeline.process_purchase_order(str(doc_id))
    with sessions() as session:
        doc = session.get(PurchaseOrderDocument, doc_id)
        assert doc.status == 'needs_review'
        assert [page['status'] for page in doc.extraction.raw_page_results] == ['completed', 'completed']
        assert len(doc.extraction.extracted_json['orders']) == 2
        assert len(doc.extraction.extracted_json['request_usage']) == 2
        assert po_routes.source_complete(doc)
    approver = SimpleNamespace(id=uuid4(), email='ann@example.com', full_name='Ann Approver')
    assert po_routes.approve(doc_id, approver)['status'] == 'approved'
    with sessions() as session:
        assert session.get(PurchaseOrderDocument, doc_id).status == 'approved'
        entry, = session.scalars(select(AuditLog)).all()
        assert (entry.action, entry.user_email, entry.target_name, entry.target_id) == ('po.approve', 'ann@example.com', 'synthetic.pdf', str(doc_id))
        assert entry.details == {'previous_status': 'needs_review', 'new_status': 'approved'}
    engine.dispose()


def test_techpack_saves_successful_group_before_a_later_group_fails(monkeypatch):
    from app import techpack_pipeline
    from app.models import TechPack
    from app.techpack_schema import PageResult, Material
    from test_table_groups import grid_image
    # Pages are read in worker threads, so every thread must share the one in-memory database.
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    doc_id = uuid4()
    with sessions() as session:
        session.add(TechPack(id=doc_id, original_filename='synthetic.pdf', minio_key='source',
            sha256='0' * 64, status='queued'))
        session.commit()
    snapshots = []
    class Model:
        def __init__(self): self.request_usage = []; self.calls = 0
        def extract(self, image, text):
            self.calls += 1
            if self.calls == 2:
                # Observe durable progress from an independent session before failure.
                with sessions() as session:
                    saved = session.get(TechPack, doc_id)
                    snapshots.append(saved.extraction.extracted_json['materials'][0]['material_code'] if saved.extraction else None)
                raise RuntimeError('second group failed')
            return PageResult(section_found=True, materials=[Material(material_code='PARTIAL')])
    monkeypatch.setattr(techpack_pipeline, 'SessionLocal', sessions)
    monkeypatch.setattr(techpack_pipeline, 'OpenRouterVLM', Model)
    monkeypatch.setattr(techpack_pipeline, 'get_bytes', lambda key: b'pdf')
    monkeypatch.setattr(techpack_pipeline, 'put_bytes', lambda *args: None)
    monkeypatch.setattr(techpack_pipeline, 'locate_pages', lambda *args: ([0], 1))
    monkeypatch.setattr(techpack_pipeline, 'render_page', lambda *args: (grid_image(), 'Wovens'))
    techpack_pipeline.process_document(str(doc_id))
    assert snapshots == ['PARTIAL']
    with sessions() as session:
        doc = session.get(TechPack, doc_id)
        assert doc.status == 'failed'
        assert doc.extraction.raw_page_results[0]['groups'][0]['status'] == 'completed'
    engine.dispose()


def test_po_retry_keeps_completed_pages_and_usage_without_extracting_them_again(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    doc_id = uuid4()
    with pymupdf.open() as pdf:
        pdf.new_page(); pdf.new_page()
        objects = {'source': pdf.tobytes()}
    with sessions() as session:
        session.add(PurchaseOrderDocument(id=doc_id, original_filename='retry.pdf', minio_key='source',
            sha256='0' * 64, status='queued'))
        session.commit()
    calls = []
    fail = [True]
    class Model:
        def __init__(self): self.request_usage = []
        def extract_po(self, image):
            calls.append(self.current_page)
            self.request_usage.append({'page': self.current_page, 'total_tokens': 10})
            if self.current_page == 2 and fail[0]: raise RuntimeError('synthetic page-two failure')
            return POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(
                contract_number=f'TEST-{self.current_page}', size_rows=[POSizeRow(size='M', quantity='1')])])
    monkeypatch.setattr(po_pipeline, 'SessionLocal', sessions)
    monkeypatch.setattr(po_pipeline, 'get_bytes', objects.__getitem__)
    monkeypatch.setattr(po_pipeline, 'put_bytes', lambda key, data, mime: objects.__setitem__(key, data))
    monkeypatch.setattr(po_pipeline, 'OpenRouterVLM', Model)
    po_pipeline.process_purchase_order(str(doc_id))
    with sessions() as session:
        assert session.get(PurchaseOrderDocument, doc_id).status == 'failed'
    # A transient source-storage outage during retry must not erase page-one results.
    monkeypatch.setattr(po_pipeline, 'get_bytes', lambda key: (_ for _ in ()).throw(RuntimeError('storage unavailable')))
    po_pipeline.process_purchase_order(str(doc_id), resume=True)
    with sessions() as session:
        saved = session.get(PurchaseOrderDocument, doc_id)
        assert len(saved.extraction.extracted_json['orders']) == 1
        assert len(saved.extraction.extracted_json['page_results']) == 1
    monkeypatch.setattr(po_pipeline, 'get_bytes', objects.__getitem__)
    fail[0] = False
    po_pipeline.process_purchase_order(str(doc_id), resume=True)
    # Page one is read once and page two twice; pages are read side by side, so the order is not fixed.
    assert sorted(calls) == [1, 2, 2]
    with sessions() as session:
        doc = session.get(PurchaseOrderDocument, doc_id)
        assert doc.status == 'needs_review'
        assert len(doc.extraction.extracted_json['request_usage']) == 3
        assert len(doc.extraction.extracted_json['orders']) == 2
        assert po_routes.source_complete(doc)
    engine.dispose()
