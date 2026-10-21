import ssl
from types import SimpleNamespace

import httpx

from app import openrouter_client as vlm


def test_openrouter_uses_system_trust_with_certificate_verification(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            return httpx.Response(
                200,
                request=httpx.Request('POST', url),
                json={'choices': [{'message': {'content': '{"has_wovens_bom": true}'}}]},
            )

    monkeypatch.setattr(vlm.httpx, 'Client', Client)
    monkeypatch.setattr(vlm, 'get_settings', lambda: SimpleNamespace(
        openrouter_api_key='test-key', openrouter_model='test-model',
    ))
    assert vlm.OpenRouterVLM().classify(b'test-image') is True
    context = captured.get('verify')
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.cert_store_stats()['x509_ca'] > 0
