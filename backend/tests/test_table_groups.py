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
