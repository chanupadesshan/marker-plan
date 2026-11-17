from io import BytesIO
from types import SimpleNamespace
from PIL import Image, ImageDraw
import pytest
from app.table_groups import plan_groups, extract_grouped
from app.openrouter_client import OutputTokenLimitError
from app.techpack_schema import PageResult, Material, ColorwayHeader
from app.po_schema import POPageResult, PurchaseOrder, POSizeRow


def grid_image(rows=12):
    image = Image.new('RGB', (600, 800), 'white')
    draw = ImageDraw.Draw(image)
    for y in range(100, 101 + rows * 45, 45):
        draw.line((20, y, 580, y), fill='black', width=2)
    draw.line((20, 100, 20, 100 + rows * 45), fill='black', width=2)
    draw.text((30, 30), 'CONTEXT HEADER', fill='black')
    buffer = BytesIO(); image.save(buffer, 'JPEG')
    return buffer.getvalue()


def test_groups_cover_page_without_overlapping_and_cut_only_at_rules():
    groups = plan_groups(grid_image(), max_bands=4)
    assert len(groups) > 1
    assert groups[0].top == 0 and groups[-1].bottom == 800
    assert all(a.bottom == b.top for a, b in zip(groups, groups[1:]))
    assert all(any(abs(group.bottom - y) <= 3 for y in range(100, 641, 45)) for group in groups[:-1])


def test_large_groups_preserve_identical_rows_and_merge_headers():
    class Model:
        current_group = None
        def extract(self, image, text):
            return PageResult(section_found=True, materials=[Material(material_code='REPEATED')],
                colorway_headers=[ColorwayHeader(code='1234', name='Blue')])
    model = Model()
    log = []
    result = extract_grouped(model, grid_image(), 'techpack', groups_log=log)
    assert len(result.materials) == len([entry for entry in log if entry['status'] == 'completed'])
    assert len(result.materials) > 1
    assert len(result.colorway_headers) == 1
    assert model.current_group is None


def bom_row(code, qty, placement='Main Fabric', colour='9900'):
    from app.techpack_schema import Colorway
    return Material(material_code=code, quantity=qty, unit='m', placement=placement,
                    colorways=[Colorway(code='9900', name='Black', material_color_code=colour, material_color_name='Black')])


def two_group_page(first, second):
    """Extract a page that splits into two groups, whose model replies are `first` and `second`."""
    replies = iter([first, second])
    class Model:
        current_group = None
        def extract(self, image, text):
            return PageResult(section_found=True, materials=next(replies))
    log = []
    result = extract_grouped(Model(), grid_image(rows=6), 'techpack', groups_log=log)
    assert len(log) == 2
    return result, log


def groups_reading(first_tp, second_tp):
    replies = iter([first_tp, second_tp])
    class Model:
        current_group = None
        def extract(self, image, text):
            return PageResult(section_found=True, tech_pack_number=next(replies), materials=[Material(material_code='R1')])
    return extract_grouped(Model(), grid_image(rows=6), 'techpack')


def test_the_same_tech_pack_number_read_differently_by_two_groups_is_not_a_conflict():
    # Seen on a real page: one half returned a garbled prefix and the other dropped the TP.
    assert groups_reading(')[32197', '32197').tech_pack_number.endswith('32197')   # no conflict raised
    assert groups_reading('32197', 'TP 32197').tech_pack_number == 'TP 32197'
    assert groups_reading('TP 32197', 'tp32197').tech_pack_number == 'TP 32197'
    assert groups_reading(None, 'TP 32197').tech_pack_number == 'TP 32197'


def test_different_tech_pack_numbers_between_groups_still_stop_the_extraction():
    with pytest.raises(RuntimeError, match='Conflicting tech_pack_number'):
        groups_reading('TP 32197', 'TP 31717')
    with pytest.raises(RuntimeError, match='Conflicting tech_pack_number'):
        groups_reading('TP 32197', '31717')


def test_a_group_that_re_reads_earlier_rows_does_not_duplicate_them():
    # BOM page 3: the first group returned three rows; the second returned those three again plus the fourth.
    a, b, c, d = bom_row('R1847', '1.22'), bom_row('R1645', '0.34', 'Knee'), bom_row('R1845', '0.04', 'Pocket'), bom_row('R2020', '0.37', 'Lining')
    result, log = two_group_page([a, b, c], [a.model_copy(deep=True), b.model_copy(deep=True), c.model_copy(deep=True), d])
    assert [row.material_code for row in result.materials] == ['R1847', 'R1645', 'R1845', 'R2020']
    assert any('repeated 3 rows already read earlier' in warning for warning in result.warnings)
    assert log[1]['ignored_repeated_rows'] == 3
    assert len(log[1]['result']['materials']) == 1


def test_a_group_that_only_repeats_earlier_rows_adds_nothing():
    a, b = bom_row('R1', '1'), bom_row('R2', '2', 'Knee')
    result, _ = two_group_page([a, b], [a.model_copy(deep=True), b.model_copy(deep=True)])
    assert [row.material_code for row in result.materials] == ['R1', 'R2']


def test_genuinely_repeated_rows_are_kept():
    a, b, c = bom_row('R1', '1'), bom_row('R2', '2', 'Knee'), bom_row('R3', '3', 'Lining')
    # Different rows, even with a shared first row, are never treated as a repeat.
    result, log = two_group_page([a, b], [b.model_copy(update={'quantity': '9'}), c])
    assert [row.material_code for row in result.materials] == ['R1', 'R2', 'R2', 'R3']
    assert 'ignored_repeated_rows' not in log[1]
    # A single identical row (or two that differ in any field, such as a colour) is evidence, not an echo.
    result, _ = two_group_page([a], [a.model_copy(deep=True), c])
    assert [row.material_code for row in result.materials] == ['R1', 'R1', 'R3']
    result, _ = two_group_page([a, b], [a.model_copy(deep=True), bom_row('R2', '2', 'Knee', colour='8600')])
    assert [row.material_code for row in result.materials] == ['R1', 'R2', 'R1', 'R2']
    assert not any('repeated' in warning for warning in result.warnings)


def test_purchase_orders_are_not_filtered_for_repeats():
    rows = [POSizeRow(size='-M', quantity='1'), POSizeRow(size='-L', quantity='2')]
    class Model:
        current_group = None
        def extract_po(self, image):
            return POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(contract_number='C', size_rows=[row.model_copy() for row in rows])])
    result = extract_grouped(Model(), grid_image(rows=6), 'po')
    assert len(result.orders[0].size_rows) == 4


def test_truncated_group_is_replaced_by_children_not_counted_twice():
    class Model:
        current_group = None
        calls = 0
        def extract_po(self, image):
            self.calls += 1
            if self.calls == 1:
                raise OutputTokenLimitError('token limit')
            return POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(contract_number='SYNTHETIC',
                total_quantity='2', size_rows=[POSizeRow(size='-M', quantity='1')])])
    model = Model(); log = []
    result = extract_grouped(model, grid_image(rows=3), 'po', groups_log=log)
    assert model.calls == 3
    assert len(result.orders) == 1
    assert len(result.orders[0].size_rows) == 2
    assert [entry['status'] for entry in log] == ['split', 'completed', 'completed']
    assert model.current_group is None


def test_single_row_limit_fails_clearly_without_infinite_retry():
    class Model:
        current_group = None
        calls = 0
        def extract_po(self, image):
            self.calls += 1
            raise OutputTokenLimitError('token limit')
    model = Model()
    buffer = BytesIO(); Image.new('RGB', (100, 100), 'white').save(buffer, 'JPEG')
    with pytest.raises(RuntimeError, match='safe row boundary'):
        extract_grouped(model, buffer.getvalue(), 'po')
    assert model.calls == 1
    assert model.current_group is None


def test_non_limit_errors_are_not_retried_as_row_splits():
    class Model:
        current_group = None
        def extract_po(self, image): raise RuntimeError('authentication failed')
    with pytest.raises(RuntimeError, match='authentication failed'):
        extract_grouped(Model(), grid_image(), 'po')


def test_failure_keeps_completed_groups_and_reports_partial_result():
    class Model:
        current_group = None
        calls = 0
        def extract_po(self, image):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError('provider unavailable')
            return POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(contract_number='TEST',
                size_rows=[POSizeRow(size='-M', quantity='1')])])
    log, progress = [], []
    with pytest.raises(RuntimeError, match='provider unavailable'):
        extract_grouped(Model(), grid_image(), 'po', groups_log=log, on_progress=progress.append)
    assert len(progress) == 1
    assert progress[0].orders[0].size_rows[0].size == '-M'
    assert [entry['status'] for entry in log] == ['completed', 'failed']


def test_request_cap_stops_recursive_splitting():
    class Model:
        current_group = None
        calls = 0
        def extract_po(self, image):
            self.calls += 1
            raise OutputTokenLimitError('token limit')
    model = Model()
    with pytest.raises(RuntimeError, match='request cap'):
        extract_grouped(model, grid_image(), 'po', max_calls=2)
    assert model.calls == 2
    assert model.current_group is None


def test_thin_rules_survive_on_large_rendered_pages():
    image = Image.new('RGB', (2400, 3200), 'white')
    draw = ImageDraw.Draw(image)
    for y in range(100, 3001, 100):
        draw.line((40, y, 2360, y), fill='black', width=1)
    output = BytesIO(); image.save(output, 'PNG')
    assert len(plan_groups(output.getvalue())) > 1


def test_partial_cell_rules_do_not_cut_a_spanning_description():
    image = Image.new('RGB', (600, 800), 'white')
    draw = ImageDraw.Draw(image)
    for y in range(100, 701, 50):
        draw.line((20, y, 450, y), fill='black', width=2)
        draw.text((480, y - 4), 'ROW SPAN', fill='black')
    output = BytesIO(); image.save(output, 'PNG')
    assert len(plan_groups(output.getvalue())) == 1


def test_unruled_table_uses_validated_layout_after_truncation():
    class Model:
        current_group = None
        calls = 0
        layouts = 0
        def locate_table_rows(self, image, workflow):
            self.layouts += 1
            return [300, 500, 700]
        def extract_po(self, image):
            self.calls += 1
            if self.calls == 1: raise OutputTokenLimitError('token limit')
            return POPageResult(page_kind='purchase_order', orders=[PurchaseOrder(contract_number='TEST',
                size_rows=[POSizeRow(size='M', quantity='1')])])
    output = BytesIO(); Image.new('RGB', (600, 800), 'white').save(output, 'JPEG')
    model = Model()
    result = extract_grouped(model, output.getvalue(), 'po')
    assert model.layouts == 1
    assert model.calls == 3
    assert len(result.orders[0].size_rows) == 2


def test_layout_cannot_cut_through_actual_printed_content():
    class Model:
        current_group = None
        calls = 0
        def locate_table_rows(self, image, workflow): return [300, -1, 1001]
        def extract_po(self, image):
            self.calls += 1
            raise OutputTokenLimitError('token limit')
    image = Image.new('RGB', (600, 800), 'white')
    ImageDraw.Draw(image).rectangle((20, 220, 580, 260), fill='black')
    output = BytesIO(); image.save(output, 'JPEG')
    model = Model()
    with pytest.raises(RuntimeError, match='safe row boundary'):
        extract_grouped(model, output.getvalue(), 'po')
    assert model.calls == 1
