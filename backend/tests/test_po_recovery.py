"""Synthetic reproduction of PO responses that consume output with blank lines."""
from copy import deepcopy
import json
from types import SimpleNamespace
import httpx
import pytest
from app import openrouter_client as client
from app.po_schema import POPageResult, PurchaseOrder, POSizeRow
from app.techpack_schema import PageResult


LOOP = '{"page_kind":"purchase_order","orders":[{' + '\n' * 10000


def model_for(monkeypatch, replies):
    requests, saved = [], []
    iterator = iter(replies)
    class Transport:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            requests.append(deepcopy(kwargs['json']))
            content, finish = next(iterator)
            return httpx.Response(200, request=httpx.Request('POST', url), json={
                'usage': {'prompt_tokens': 400, 'completion_tokens': 6500, 'total_tokens': 6900},
                'choices': [{'finish_reason': finish, 'message': {'content': content}}]})
    monkeypatch.setattr(client.httpx, 'Client', Transport)
    monkeypatch.setattr(client, 'get_settings', lambda: SimpleNamespace(openrouter_api_key='test', openrouter_model='same-model'))
    monkeypatch.setattr(client.time, 'sleep', lambda _: None)
    model = client.OpenRouterVLM()
    monkeypatch.setattr(model, '_save_failed_response', lambda entry, content: saved.append(deepcopy(entry)))
    return model, requests, saved


def valid_po():
    return json.dumps(POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(
        contract_number='SYNTHETIC', size_rows=[POSizeRow(size='-M', quantity='2')])]).model_dump())


@pytest.mark.parametrize('finish', ['length', 'stop'])
def test_po_retries_whitespace_once_with_compact_json_and_preserves_usage(monkeypatch, finish):
    model, requests, saved = model_for(monkeypatch, [(LOOP, finish), (valid_po(), 'stop')])
    model.current_page = 1
    model.current_group = {'group': '2.1', 'row_group_mode': True}
    assert model.extract_po(b'image').orders[0].contract_number == 'SYNTHETIC'
    assert len(requests) == 2
    assert 'single-line' in requests[1]['messages'][1]['content'][0]['text']
    assert 'TARGET' in requests[1]['messages'][1]['content'][0]['text']
    assert requests[1]['response_format'] == requests[0]['response_format']
    assert requests[1]['model'] == 'same-model'
    assert requests[1]['max_tokens'] == 6500
    assert [entry['status'] for entry in model.request_usage] == ['malformed_generation', 'success']
    assert model.request_usage[0]['output_tokens'] == 6500
    assert model.request_usage[1]['group'] == '2.1'
    assert saved[0]['status'] == 'malformed_generation'


def test_repeated_whitespace_fails_after_one_retry_without_row_split_error(monkeypatch):
    model, requests, _ = model_for(monkeypatch, [(LOOP, 'length'), (LOOP, 'length')])
    with pytest.raises(RuntimeError, match='repeated blank output') as error:
        model.extract_po(b'image')
    assert not isinstance(error.value, client.OutputTokenLimitError)
    assert len(requests) == 2
    assert [entry['status'] for entry in model.request_usage] == ['malformed_generation'] * 2


def test_real_table_truncation_still_uses_row_group_fallback(monkeypatch):
    model, requests, _ = model_for(monkeypatch, [('{"orders":[{"contract_number":"TEST"}', 'length')])
    with pytest.raises(client.OutputTokenLimitError):
        model.extract_po(b'image')
    assert len(requests) == 1


def test_techpack_and_filtered_results_do_not_use_po_recovery(monkeypatch):
    model, requests, _ = model_for(monkeypatch, [(LOOP, 'length')])
    with pytest.raises(client.OutputTokenLimitError):
        model.extract(b'image', '')
    assert len(requests) == 1


def contract_loop(count=27, closed=False):
    order = json.loads(valid_po())['orders'][0]
    result = '{"page_kind":"purchase_order","orders":[' + ','.join(json.dumps(order) for _ in range(count))
    return result + ('],"warnings":[]}' if closed else ',{"contract_number":')


@pytest.mark.parametrize('finish,closed', [('length', False), ('stop', True)])
def test_repeated_contract_blocks_get_one_recovery_without_row_splitting(monkeypatch, finish, closed):
    model, requests, _ = model_for(monkeypatch, [(contract_loop(closed=closed), finish), (valid_po(), 'stop')])
    result = model.extract_po(b'image')
    assert len(result.orders) == 1
    assert len(requests) == 2
    assert model.request_usage[0]['status'] == 'malformed_generation'
    assert model.request_usage[0]['generation_issue'] == 'repeated_contract_blocks'
    assert 'exactly once' in requests[1]['messages'][1]['content'][0]['text']
    assert requests[0]['response_format'] == {'type': 'json_object'}
    assert requests[1]['response_format'] == {'type': 'json_object'}


def test_json_mode_recovery_still_requires_every_field(monkeypatch):
    incomplete = '{"page_kind":"purchase_order","orders":[{"contract_number":"ONLY"}]}'
    model, requests, _ = model_for(monkeypatch, [(contract_loop(), 'length'),
        (incomplete, 'stop'), (valid_po(), 'stop')])
    assert model.extract_po(b'image').orders[0].contract_number == 'SYNTHETIC'
    assert [entry['status'] for entry in model.request_usage] == ['malformed_generation', 'invalid_response', 'success']
    assert len(requests) == 3


def test_repeated_contract_failure_is_bounded_and_not_a_token_split(monkeypatch):
    content = contract_loop()
    model, requests, _ = model_for(monkeypatch, [(content, 'length'), (content, 'length')])
    with pytest.raises(RuntimeError, match='repeated contract blocks') as error:
        model.extract_po(b'image')
    assert not isinstance(error.value, client.OutputTokenLimitError)
    assert len(requests) == 2


def test_repeated_sizes_and_distinct_contracts_are_not_removed_or_retried(monkeypatch):
    orders = [PurchaseOrder(contract_number=f'TEST-{i}', size_rows=[POSizeRow(size='M', quantity='2')] * 12) for i in range(6)]
    content = POPageResult(page_kind='purchase_order', orders=orders).model_dump_json()
    model, requests, _ = model_for(monkeypatch, [(content, 'stop')])
    result = model.extract_po(b'image')
    assert len(result.orders) == 6
    assert len(result.orders[0].size_rows) == 12
    assert len(requests) == 1
    model, requests, _ = model_for(monkeypatch, [(LOOP, 'content_filter')])
    with pytest.raises(RuntimeError, match='content_filter'):
        model.extract_po(b'image')
    assert len(requests) == 1
