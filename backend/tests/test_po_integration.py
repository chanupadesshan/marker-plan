"""Exercise real ORM commits/reloads without a live DB, storage or paid model call."""
from uuid import uuid4
import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import PurchaseOrderDocument
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
    assert po_routes.approve(doc_id)['status'] == 'approved'
    with sessions() as session:
        assert session.get(PurchaseOrderDocument, doc_id).status == 'approved'
    engine.dispose()
