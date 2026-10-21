from app.techpack_schema import Colorway, Material, PageResult
from app.techpack_wovens import normalize_wovens_page, scope_wovens_text
from app.techpack_merge import combine_pages
from app.techpack_pdf import render_page
import pymupdf
from PIL import Image
from io import BytesIO
import pytest
from app.techpack_schema import DocumentExtraction, WovensPageTable


SOURCE = '''Description
Composition
Qty
9955
Black/HV
Red
Wovens
R1371
0.95 m
9900
Black
R1804
0.57 m
5500
Fluorescent red
Knits
R1963
0.03 m
Buttons (R3...)
R300410
'''


def test_quantity_separates_printed_unit_before_merging():
    row = Material(material_code='R1', quantity='0.95 m', unit='m')
    assert row.quantity == '0.95'
    assert row.unit == 'm'
    assert Material(quantity='0.26 kg').unit == 'kg'
    assert Material(quantity='0,95', unit='m').quantity == '0,95'


def test_scope_keeps_header_and_wovens_but_excludes_following_sections():
    scoped = scope_wovens_text(SOURCE)
    assert '9955' in scoped
    assert 'R1804' in scoped
    assert 'Knits' not in scoped
    assert 'R1963' not in scoped
    assert 'R300410' not in scoped


def test_single_header_is_shared_by_every_material_not_its_color_code():
    page = PageResult(section_found=True, materials=[
        Material(material_code='R1371', colorways=[Colorway(code='9955', name='Black/HV Red', material_color_code='9900')]),
        Material(material_code='R1804', colorways=[Colorway(code='5500', name='Fluorescent red', material_color_code='5500')]),
        Material(material_code='R1963'),
    ])
    normalized = normalize_wovens_page(page, SOURCE)
    assert [m.material_code for m in normalized.materials] == ['R1371', 'R1804']
    assert {v.code for m in normalized.materials for v in m.colorways} == {'9955'}
    assert normalized.materials[1].colorways[0].material_color_code == '5500'
    assert normalized.materials[1].colorways[0].name == 'Black/HV Red'


def test_multiple_headers_do_not_guess_unknown_column_assignment():
    source = SOURCE.replace('9955\nBlack/HV\nRed', '8833\nNavy/HV yellow\n8853\nNavy/HV orange')
    page = PageResult(section_found=True, materials=[Material(
        material_code='R1371', colorways=[Colorway(code='9900', material_color_code='9900')],
    )])
    result = normalize_wovens_page(page, source)
    assert result.materials[0].colorways[0].code is None
    assert any('header' in warning.lower() for warning in result.warnings)


def test_combination_retains_separate_page_tables():
    p = normalize_wovens_page(PageResult(section_found=True, materials=[
        Material(material_code='R1371', quantity='0.95 m', unit='m'),
    ]), SOURCE)
    result = combine_pages([(12, p), (19, p)])
    assert len(result.materials) == 1
    assert [table.page_number for table in result.page_tables] == [12, 19]
    assert len(result.page_tables[0].materials) == 1


def test_render_excludes_next_category_from_both_image_and_text():
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=400, height=600)
        for y, text in [(40, 'BOM'), (65, 'Qty'), (85, '9955'), (105, 'Black/HV Red'),
                        (130, 'Wovens'), (160, 'R1371'), (185, '0.95 m'),
                        (240, 'Knits'), (275, 'R1963')]:
            page.insert_text((30, y), text)
        image, text = render_page(pdf.tobytes(), 0)
    assert 'R1371' in text
    assert 'R1963' not in text
    with Image.open(BytesIO(image)) as rendered:
        # Original 600pt page is over 1800px at 220 DPI; the crop ends above Knits.
        assert rendered.height < 800
        assert rendered.width > 1000


def test_page_table_corrections_regenerate_material_rows():
    from app.techpack_merge import canonicalize_corrections
    payload = DocumentExtraction(page_tables=[WovensPageTable(
        page_number=4, materials=[Material(material_code='R1', quantity='0.75 m', unit='m')],
    )])
    result = canonicalize_corrections(payload)
    assert result.materials[0].quantity == '0.75'
    assert result.materials[0].source_pages == [4]
    assert result.page_tables[0].materials[0].quantity == '0.75'
    assert result.source_pages == [4]
    from app.techpack_pipeline import write_material_rows
    from decimal import Decimal
    from uuid import uuid4
    captured = []
    class Session:
        def execute(self, statement):
            pass
        def add(self, row):
            captured.append(row)
    write_material_rows(Session(), uuid4(), result)
    assert captured[0].quantity == Decimal('0.75')
    assert captured[0].source_pages == [4]


def test_conflicting_material_and_page_table_edits_are_rejected():
    from app.techpack_merge import canonicalize_corrections
    payload = DocumentExtraction(
        materials=[Material(material_code='R1', quantity='1', unit='m', source_pages=[4])],
        page_tables=[WovensPageTable(page_number=4, materials=[Material(material_code='R1', quantity='2', unit='m')])],
    )
    with pytest.raises(ValueError, match='page_tables'):
        canonicalize_corrections(payload)
