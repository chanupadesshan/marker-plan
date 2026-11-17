from app.extraction_progress import extraction_progress


def test_queue_and_page_detection_have_no_invented_percentage():
    assert extraction_progress('queued', [], [])['percent'] is None
    assert extraction_progress('processing', [], [])['stage'] == 'locating'


def test_only_completed_selected_pages_count_once():
    result = extraction_progress('processing', [3, 7, 9], [
        {'page': 3, 'status': 'completed'}, {'page': 3, 'status': 'completed'},
        {'page': 7, 'status': 'processing', 'result': {'materials': [{}]}},
        {'page': 40, 'status': 'completed'}])
    assert result == {'stage': 'extracting', 'completed_pages': 1, 'total_pages': 3, 'percent': 33}


def test_finishing_and_failure_do_not_claim_success():
    assert extraction_progress('processing', [1], [{'page': 1, 'status': 'completed'}])['stage'] == 'finalizing'
    assert extraction_progress('failed', [1], [])['stage'] == 'failed'
    assert extraction_progress('needs_review', [1], [])['percent'] == 100


def test_document_response_exposes_progress_without_raw_page_payloads(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from app import main
    document = SimpleNamespace(status='processing', selected_pages=[3, 7], extraction=SimpleNamespace(
        extracted_json={}, model_name='test', raw_page_results=[{'page': 3, 'status': 'completed'}]))
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args): return document
    monkeypatch.setattr(main, 'SessionLocal', Session)
    monkeypatch.setattr(main, 'record_summary', lambda row: {'status': row.status})
    monkeypatch.setattr(main, 'ply_info_for', lambda *args: {})
    result = main.get_document(uuid4())
    assert result['progress']['percent'] == 50
    assert result['progress']['completed_pages'] == 1
    assert 'raw_page_results' not in result
