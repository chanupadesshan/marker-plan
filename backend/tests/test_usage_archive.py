"""Deleting a Tech Pack or purchase order must not lower what the Usage page reports."""
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import BomExtraction, PurchaseOrderDocument, PurchaseOrderExtraction, TechPack, UsageArchive
from app import main, po_routes, usage_routes
from app.usage_archive import archive_usage


@compiles(JSONB, 'sqlite')
def sqlite_jsonb(element, compiler, **kwargs):
    return 'JSON'


def request(tokens, cost, status='success', stage='extraction'):
    return {'status': status, 'stage': stage, 'total_tokens': tokens, 'input_tokens': tokens - 10, 'output_tokens': 10, 'cost_usd': cost}


def build(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    tech_pack_id, po_id, kept_id = uuid4(), uuid4(), uuid4()
    with sessions() as session:
        session.add(TechPack(id=tech_pack_id, original_filename='tp.pdf', minio_key='a', sha256='0' * 64, status='needs_review'))
        session.add(BomExtraction(document_id=tech_pack_id, model_name='m', raw_page_results=[], warnings=[],
                                  extracted_json={'request_usage': [request(100, 0.01), request(200, 0.02, 'request_error')]}))
        session.add(PurchaseOrderDocument(id=po_id, original_filename='po.pdf', minio_key='b', sha256='1' * 64, status='needs_review'))
        session.add(PurchaseOrderExtraction(document_id=po_id, model_name='m', raw_page_results=[], warnings=[],
                                            extracted_json={'request_usage': [request(300, 0.03, stage='po_extraction')]}))
        session.add(TechPack(id=kept_id, original_filename='kept.pdf', minio_key='c', sha256='2' * 64, status='approved'))
        session.add(BomExtraction(document_id=kept_id, model_name='m', raw_page_results=[], warnings=[],
                                  extracted_json={'request_usage': [request(50, 0.005)]}))
        session.commit()
    for module in (main, po_routes, usage_routes):
        monkeypatch.setattr(module, 'SessionLocal', sessions)
    monkeypatch.setattr(main, 'delete_prefix', lambda prefix: None)
    monkeypatch.setattr(po_routes, 'delete_prefix', lambda prefix: None)
    return sessions, engine, tech_pack_id, po_id


def totals():
    summary = usage_routes.summarize(usage_routes.load_documents(30), 30)
    return {key: summary['totals'][key] for key in ('documents', 'requests', 'failed_requests', 'total_tokens', 'cost_usd')}


def test_usage_totals_do_not_drop_when_documents_are_deleted(monkeypatch):
    sessions, engine, tech_pack_id, po_id = build(monkeypatch)
    before = totals()
    assert (before['documents'], before['requests'], before['total_tokens']) == (3, 4, 650)
    assert round(before['cost_usd'], 3) == 0.065

    main.delete_document(tech_pack_id)
    po_routes.delete_purchase_order(po_id)
    with sessions() as session:
        assert session.get(TechPack, tech_pack_id) is None and session.get(PurchaseOrderDocument, po_id) is None
        archived = {row.kind: row for row in session.scalars(select(UsageArchive))}
    assert set(archived) == {'techpack', 'po'}
    assert archived['techpack'].filename == 'tp.pdf' and archived['po'].document_id == str(po_id)
    assert totals() == before

    # The deleted uploads are still listed, marked as deleted, with their failed requests.
    summary = usage_routes.summarize(usage_routes.load_documents(30), 30)
    assert [(item['filename'], item['deleted']) for item in summary['worst_documents']] == [('tp.pdf', True)]
    assert {row['stage'] for row in summary['by_stage']} == {'extraction', 'po_extraction'}
    engine.dispose()


def test_per_user_usage_survives_deletion_and_a_document_without_usage_adds_no_row(monkeypatch):
    sessions, engine, tech_pack_id, po_id = build(monkeypatch)
    before = usage_routes.summarize_by_user(usage_routes.load_documents(30), {}, 30)
    main.delete_document(tech_pack_id)
    assert usage_routes.summarize_by_user(usage_routes.load_documents(30), {}, 30) == before
    with sessions() as session:
        empty_id = uuid4()
        session.add(TechPack(id=empty_id, original_filename='empty.pdf', minio_key='d', sha256='3' * 64, status='failed'))
        session.commit()
        archive_usage(session, 'techpack', session.get(TechPack, empty_id))
        session.commit()
        assert len(session.scalars(select(UsageArchive)).all()) == 1
    engine.dispose()
