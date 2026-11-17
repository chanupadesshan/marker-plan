import pytest
from app.po_schema import POPageResult, PurchaseOrder, POSizeRow
from app.po_merge import combine_po_pages, number, validate_totals


def order(code='PO-1', **kwargs):
    return PurchaseOrder(contract_number=code, **kwargs)


def page(*orders):
    return POPageResult(page_kind='purchase_order', orders=list(orders))


def test_preserves_sizes_quantities_and_page_provenance():
    result = combine_po_pages([(2, page(order(size_rows=[POSizeRow(size='-C52', quantity='32', source_page=99)], total_quantity='32')))])
    row = result.orders[0].size_rows[0]
    assert (row.size, row.quantity, row.source_page) == ('-C52', '32', 2)
    assert result.orders[0].source_pages == [2]


def test_continuation_keeps_repeated_rows_and_separate_contracts():
    a = order(size_rows=[POSizeRow(size='M', quantity='2')])
    result = combine_po_pages([(1, page(a, order('PO-2'))), (2, page(a))])
    assert len(result.orders) == 2
    assert len(result.orders[0].size_rows) == 2
    assert result.orders[0].source_pages == [1, 2]


def test_conflicts_and_missing_identity_stay_separate():
    result = combine_po_pages([(1, page(order(model_id='A'), order(model_id='B'), order(None), order(None)))])
    assert len(result.orders) == 4
    assert result.warnings


@pytest.mark.parametrize('value,expected', [('12,50', '12.50'), ('12.50', '12.50'), ('1,234.50', None), (None, None), ('', None),
                                            ('1 002', '1002'), ('12 345', '12345'), ('1 002', '1002'), ('1 00', None)])
def test_explicit_decimal_parsing(value, expected):
    actual = number(value)
    assert (str(actual) if actual is not None else None) == expected


def test_incomplete_and_mismatched_totals_warn():
    result = combine_po_pages([(1, page(order(total_quantity='10', size_rows=[POSizeRow(quantity='2')]),
                                      order('PO-2', total_quantity='10', size_rows=[POSizeRow()])))])
    assert 'differs' in ' '.join(result.orders[0].warnings)
    assert 'incomplete' in ' '.join(result.orders[1].warnings)


@pytest.mark.parametrize('printed', ['1,410', '1.410', '1 410', '1410'])
def test_contract_355800_total_matches_its_size_rows(printed):
    po = order('355800', total_quantity=printed, size_rows=[
        POSizeRow(size=size, quantity=str(quantity)) for size, quantity in
        zip(['C44', 'C46', 'C48', 'C50', 'C52', 'C54', 'C56', 'C58', 'C60', 'C62'],
            [30, 90, 210, 240, 330, 270, 150, 30, 30, 30])])
    validate_totals(po)
    assert po.warnings == []
    assert po.total_quantity == printed


@pytest.mark.parametrize('printed,quantity', [('1,234,567', '1234567'), ('1.234.567', '1234567'),
                                             ('12,50', '12.50'), ('1,410', '1.410')])
def test_total_separator_is_resolved_by_the_actual_size_sum(printed, quantity):
    po = order(total_quantity=printed, size_rows=[POSizeRow(size='S', quantity=quantity)])
    validate_totals(po)
    assert po.warnings == []


def test_revalidation_removes_stale_warnings_but_keeps_real_mismatches_and_other_notes():
    po = order(total_quantity='1,410', size_rows=[POSizeRow(size='S', quantity='1410')], warnings=[
        'Size quantity sum differs from the printed total quantity',
        'Quantity validation incomplete: total or size quantities are missing/unreadable', 'Check original colour'])
    validate_totals(po)
    validate_totals(po)
    assert po.warnings == ['Check original colour']
    po.size_rows[0].quantity = '1400'
    validate_totals(po)
    validate_totals(po)
    assert po.warnings == ['Check original colour', 'Size quantity sum differs from the printed total quantity']


def test_comma_decimal_is_not_blindly_changed_to_thousands():
    po = order(total_quantity='1,41', size_rows=[POSizeRow(size='S', quantity='141')])
    validate_totals(po)
    assert 'differs' in ' '.join(po.warnings)


def test_page_outcomes_reject_contradictions_and_extra_fields():
    with pytest.raises(ValueError):
        POPageResult(page_kind='other', orders=[order()])
    with pytest.raises(ValueError):
        POSizeRow(invented='supplier')


def test_po_contract_contains_only_requested_business_fields():
    payload = order(tech_pack_reference='TP-1', model_id='M-1', quality_id='Q-1', color_id='0001',
                    total_quantity='32', size_rows=[POSizeRow(size='-M', quantity='32')]).model_dump()
    assert set(payload) == {'contract_number', 'tech_pack_reference', 'model_id', 'quality_id',
        'color_id', 'total_quantity', 'size_rows', 'source_pages', 'warnings'}
    assert set(payload['size_rows'][0]) == {'size', 'quantity', 'source_page'}
