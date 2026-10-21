import json
from types import SimpleNamespace
import httpx
import pytest
from app import vlm
from app.schema import PageResult, Material


def make_vlm(monkeypatch, content, finish='stop', usage=None):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            return httpx.Response(200, request=httpx.Request('POST', url), json={
                'id': 'gen-test', 'usage': usage,
                'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(content() if callable(content) else content)}}],
            })
    monkeypatch.setattr(vlm.httpx, 'Client', Client)
    monkeypatch.setattr(vlm, 'get_settings', lambda: SimpleNamespace(openrouter_api_key='test-key', openrouter_model='test-model'))
    return vlm.OpenRouterVLM()


def test_success_records_native_usage_and_page(monkeypatch):
    model = make_vlm(monkeypatch, PageResult(section_found=True, materials=[Material(material_code='R1')]).model_dump(),
                     usage={'prompt_tokens': 1200, 'completion_tokens': 350, 'total_tokens': 1550})
    model.current_page = 7
    model.extract(b'private-image', 'private-pdf-text')
    entry = model.request_usage[0]
    assert entry['input_tokens'] == 1200
    assert entry['output_tokens'] == 350
    assert entry['total_tokens'] == 1550
    assert entry['finish_reason'] == 'stop'
    assert entry['page'] == 7
    assert entry['status'] == 'success'
    assert entry['output_limit'] == 6500
    assert 'private' not in json.dumps(entry)


def test_empty_result_is_failure_with_usage_preserved(monkeypatch):
    model = make_vlm(monkeypatch, PageResult(section_found=True).model_dump(), usage={'completion_tokens': 30})
    with pytest.raises(RuntimeError, match='no material rows'):
        model.extract(b'image', '')
    assert model.request_usage[0]['status'] == 'empty_result'
    assert model.request_usage[0]['output_tokens'] == 30
    assert len(model.request_usage) == 2


def test_empty_result_has_one_corrective_retry_then_can_succeed(monkeypatch):
    replies = iter([PageResult(section_found=True).model_dump(),
                    PageResult(section_found=True, materials=[Material(material_code='R1')]).model_dump()])
    model = make_vlm(monkeypatch, lambda: next(replies))
    assert len(model.extract(b'image', '').materials) == 1
    assert [entry['status'] for entry in model.request_usage] == ['empty_result', 'success']


def test_token_limit_is_distinct_and_missing_usage_is_unknown(monkeypatch):
    model = make_vlm(monkeypatch, {}, finish='length')
    with pytest.raises(RuntimeError, match='token limit'):
        model.extract(b'image', '')
    entry = model.request_usage[0]
    assert entry['status'] == 'token_limit'
    assert entry['finish_reason'] == 'length'
    assert entry['input_tokens'] is None


def test_pipeline_persists_usage_when_extraction_fails(monkeypatch):
    from app import pipeline
    from uuid import uuid4
    document = SimpleNamespace(status='queued', error_message=None, extraction=None,
                               minio_key='test.pdf', page_count=None, selected_pages=[])
    usage = [{'page': 1, 'stage': 'extraction', 'status': 'empty_result', 'output_tokens': 30}]
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args): return document
        def commit(self): pass
        def rollback(self): pass
        def add(self, extraction): document.extraction = extraction
    class Model:
        request_usage = usage
        def extract(self, *args): raise RuntimeError('no material rows')
    monkeypatch.setattr(pipeline, 'SessionLocal', Session)
    monkeypatch.setattr(pipeline, 'OpenRouterVLM', Model)
    monkeypatch.setattr(pipeline, 'get_bytes', lambda key: b'pdf')
    monkeypatch.setattr(pipeline, 'put_bytes', lambda *args: None)
    monkeypatch.setattr(pipeline, 'locate_pages', lambda *args: ([0], 1))
    monkeypatch.setattr(pipeline, 'render_page', lambda *args: (b'image', 'Wovens'))
    pipeline.process_document(str(uuid4()))
    assert document.status == 'failed'
    assert document.extraction.extracted_json['request_usage'] == usage
    assert 'no material rows' in document.error_message
