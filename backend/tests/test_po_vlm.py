import pytest
from app import vlm
from app.po_schema import POPageResult, PurchaseOrder, POSizeRow
from test_token_usage import make_vlm


def test_po_wire_schema_requires_nested_fields():
    schema = vlm.required_response_model(POPageResult).model_json_schema()
    for definition in [schema, *schema['$defs'].values()]:
        if definition.get('type') == 'object':
            assert set(definition['required']) == set(definition['properties'])


def test_po_request_records_extraction_budget_and_usage(monkeypatch):
    payload = POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(contract_number='TEST', size_rows=[POSizeRow(size='-M')])])
    model = make_vlm(monkeypatch, payload.model_dump())
    model.current_page = 3
    assert model.extract_po(b'image').orders[0].size_rows[0].size == '-M'
    assert model.request_usage[0]['stage'] == 'po_extraction'
    assert model.request_usage[0]['output_limit'] == 6500


def test_empty_po_has_one_corrective_retry(monkeypatch):
    model = make_vlm(monkeypatch, POPageResult(page_kind='purchase_order').model_dump())
    with pytest.raises(RuntimeError, match='no orders'):
        model.extract_po(b'image')
    assert len(model.request_usage) == 2
    assert model.request_usage[0]['status'] == 'empty_result'


@pytest.mark.parametrize('kind', ['empty', 'other'])
def test_explicit_non_po_outcome_is_valid(monkeypatch, kind):
    model = make_vlm(monkeypatch, POPageResult(page_kind=kind).model_dump())
    assert model.extract_po(b'image').page_kind == kind


def test_po_token_limit_is_recorded(monkeypatch):
    model = make_vlm(monkeypatch, {}, finish='length')
    with pytest.raises(RuntimeError, match='token limit'):
        model.extract_po(b'image')
    assert model.request_usage[0]['status'] == 'token_limit'
