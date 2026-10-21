import json
from types import SimpleNamespace
import httpx
import pytest
from app import openrouter_client as vlm
from app.techpack_schema import Material, PageResult


def test_wire_schema_requires_materials_and_nested_fields():
    model = vlm.required_response_model(PageResult)
    schema = model.model_json_schema()
    assert set(schema['required']) == set(schema['properties'])
    for definition in schema['$defs'].values():
        if definition.get('type') == 'object':
            assert set(definition['required']) == set(definition['properties'])
            assert definition['additionalProperties'] is False
    with pytest.raises(ValueError):
        model.model_validate({'section_found': True})


@pytest.mark.parametrize('bad_response', [
    {'section_found': True},
    PageResult(section_found=True).model_dump(),
])
def test_failed_response_saved_without_request_secrets(monkeypatch, tmp_path, bad_response):
    requests = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            requests.append(kwargs['json'])
            return httpx.Response(200, request=httpx.Request('POST', url), json={
                'id': 'test-generation', 'usage': {'completion_tokens': 94},
                'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(bad_response)}}],
            })
    monkeypatch.setattr(vlm.httpx, 'Client', Client)
    monkeypatch.setattr(vlm.time, 'sleep', lambda _: None)
    monkeypatch.setattr(vlm, 'get_settings', lambda: SimpleNamespace(
        openrouter_api_key='SECRET-KEY', openrouter_model='test', diagnostics_dir=str(tmp_path)))
    with pytest.raises(RuntimeError):
        vlm.OpenRouterVLM().extract(b'SECRET-IMAGE', 'SECRET-PDF-TEXT')
    files = list(tmp_path.glob('*.json'))
    assert files
    content = files[0].read_text(encoding='utf-8')
    assert json.loads(content)['response_content'] == json.dumps(bad_response)
    assert 'SECRET-' not in content
    assert requests[0]['response_format']['json_schema']['strict'] is True
    assert requests[0]['provider']['require_parameters'] is True


def test_complete_response_validates_with_required_network_contract():
    payload = PageResult(section_found=True, materials=[Material(material_code='R1', quantity='0.95', unit='m')]).model_dump()
    result = vlm.required_response_model(PageResult).model_validate(payload)
    assert result.materials[0].quantity == '0.95'
