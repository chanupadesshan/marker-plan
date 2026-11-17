"""Tech Pack extraction reads pages (and checks pages) in parallel without changing the result."""
import threading
import time
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
import pymupdf
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import techpack_pdf, techpack_pipeline
from app.database import Base
from app.models import TechPack
from app.techpack_schema import Material, PageResult
import test_po_integration  # noqa: F401  (registers the SQLite stand-in for JSONB)


def blank_page():
    buffer = BytesIO(); Image.new('RGB', (400, 300), 'white').save(buffer, 'JPEG')
    return buffer.getvalue()


class Probe:
    """Counts how many calls are in flight at once."""
    def __init__(self): self.lock, self.now, self.peak = threading.Lock(), 0, 0
    def __enter__(self):
        with self.lock:
            self.now += 1; self.peak = max(self.peak, self.now)
    def __exit__(self, *args):
        with self.lock: self.now -= 1


def setup_document(monkeypatch, pages, model, concurrency):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    doc_id = uuid4()
    with sessions() as session:
        session.add(TechPack(id=doc_id, original_filename='x.pdf', minio_key='k', sha256='0' * 64, status='queued'))
        session.commit()
    monkeypatch.setattr(techpack_pipeline, 'SessionLocal', sessions)
    monkeypatch.setattr(techpack_pipeline, 'OpenRouterVLM', model)
    monkeypatch.setattr(techpack_pipeline, 'get_bytes', lambda key: b'pdf')
    monkeypatch.setattr(techpack_pipeline, 'put_bytes', lambda *args: None)
    monkeypatch.setattr(techpack_pipeline, 'locate_pages', lambda *args: (pages, 20))
    monkeypatch.setattr(techpack_pipeline, 'render_page', lambda *args: (blank_page(), 'Wovens'))
    monkeypatch.setattr(techpack_pipeline, 'get_settings',
                        lambda: SimpleNamespace(extraction_concurrency=concurrency, openrouter_model='test-model'))
    return sessions, doc_id, engine


def slow_first_page_model(probe, delays):
    class Model:
        def __init__(self): self.request_usage = []; self.current_page = None; self.current_group = None
        def extract(self, image, text):
            with probe:
                time.sleep(delays.get(self.current_page, 0.05))
            self.request_usage.append({'page': self.current_page, 'stage': 'extraction', 'status': 'success'})
            return PageResult(section_found=True, materials=[Material(material_code=f'R{self.current_page}', quantity='1', unit='m')])
    return Model


def test_pages_are_read_side_by_side_and_merged_in_page_order(monkeypatch):
    probe = Probe()
    # Page 11 finishes last, so completion order differs from page order.
    sessions, doc_id, engine = setup_document(monkeypatch, [10, 11, 12, 13], slow_first_page_model(probe, {11: 0.4}), 4)
    techpack_pipeline.process_document(str(doc_id))
    assert probe.peak >= 2
    with sessions() as session:
        doc = session.get(TechPack, doc_id)
        assert doc.status == 'needs_review'
        assert [row['material_code'] for row in doc.extraction.extracted_json['materials']] == ['R11', 'R12', 'R13', 'R14']
        assert [entry['page'] for entry in doc.extraction.raw_page_results] == [11, 12, 13, 14]
        assert all(entry['status'] == 'completed' for entry in doc.extraction.raw_page_results)
        assert [use['page'] for use in doc.extraction.extracted_json['request_usage']] == [11, 12, 13, 14]
        assert doc.selected_pages == [11, 12, 13, 14]
    engine.dispose()


def test_a_limit_of_one_reads_one_page_at_a_time(monkeypatch):
    probe = Probe()
    sessions, doc_id, engine = setup_document(monkeypatch, [0, 1, 2], slow_first_page_model(probe, {}), 1)
    techpack_pipeline.process_document(str(doc_id))
    assert probe.peak == 1
    with sessions() as session:
        assert session.get(TechPack, doc_id).status == 'needs_review'
    engine.dispose()


def test_one_failed_page_fails_the_document_without_waiting_for_the_others(monkeypatch):
    release = threading.Event()
    class Model:
        def __init__(self): self.request_usage = []; self.current_page = None; self.current_group = None
        def extract(self, image, text):
            if self.current_page == 1:
                release.wait(10)   # stays busy until the document has already been reported as failed
                return PageResult(section_found=True, materials=[Material(material_code='LATE')])
            raise RuntimeError('page two failed')
    sessions, doc_id, engine = setup_document(monkeypatch, [0, 1], Model, 4)
    started = time.time()
    techpack_pipeline.process_document(str(doc_id))
    returned_while_page_one_was_busy = not release.is_set()
    release.set()
    assert returned_while_page_one_was_busy and time.time() - started < 8
    with sessions() as session:
        doc = session.get(TechPack, doc_id)
        assert doc.status == 'failed'
        assert 'page two failed' in doc.error_message
        assert {entry['page']: entry['status'] for entry in doc.extraction.raw_page_results}[1] == 'failed'
    time.sleep(0.5)   # let the stopped page thread wind down before the engine goes away
    engine.dispose()


def test_partial_results_are_saved_for_every_page_in_flight(monkeypatch):
    seen = []
    class Model:
        def __init__(self): self.request_usage = []; self.current_page = None; self.current_group = None
        def extract(self, image, text):
            return PageResult(section_found=True, materials=[Material(material_code=f'R{self.current_page}')])
    sessions, doc_id, engine = setup_document(monkeypatch, [4, 5], Model, 2)
    original = techpack_pipeline.combine_pages
    def watch(results):
        seen.append(sorted(page for page, _ in results))
        return original(results)
    monkeypatch.setattr(techpack_pipeline, 'combine_pages', watch)
    techpack_pipeline.process_document(str(doc_id))
    assert [5] in seen or [6] in seen   # a snapshot was saved while a page was still being read
    assert seen[-1] == [5, 6]
    engine.dispose()


def test_page_checks_run_side_by_side_and_keep_their_order(monkeypatch):
    document = pymupdf.open()
    for _ in range(6):
        document.new_page()          # no text, so every page needs the model's check
    probe = Probe()
    class Model:
        def __init__(self): self.request_usage = []; self.current_page = None; self.current_group = None
        def classify(self, image):
            with probe:
                time.sleep(0.15 if self.current_page == 1 else 0.05)
            self.request_usage.append({'page': self.current_page, 'stage': 'classification'})
            return self.current_page in (2, 5)
    monkeypatch.setattr(techpack_pdf, 'get_settings', lambda: SimpleNamespace(vision_page_classification=True, extraction_concurrency=3))
    model = Model()
    selected, total = techpack_pdf.locate_pages(document.tobytes(), model)
    assert (selected, total) == ([1, 4], 6)
    assert probe.peak >= 2
    assert [use['page'] for use in model.request_usage] == [1, 2, 3, 4, 5, 6]
    assert model.current_page is None   # the original client's page label is left alone


def test_a_failed_page_check_stops_the_rest(monkeypatch):
    document = pymupdf.open()
    for _ in range(6):
        document.new_page()
    class Model:
        def __init__(self): self.request_usage = []; self.current_page = None; self.current_group = None
        def classify(self, image):
            if self.current_page == 2:
                raise RuntimeError('check failed')
            return False
    monkeypatch.setattr(techpack_pdf, 'get_settings', lambda: SimpleNamespace(vision_page_classification=True, extraction_concurrency=2))
    try:
        techpack_pdf.locate_pages(document.tobytes(), Model())
    except RuntimeError as error:
        assert 'check failed' in str(error)
    else:
        raise AssertionError('the failure should have been raised')
