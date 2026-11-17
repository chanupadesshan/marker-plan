from app.techpack_schema import Colorway, Material, PageResult
from app.techpack_wovens import bom_title_numbers, normalize_wovens_page, scope_wovens_text
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


def test_source_identifiers_and_placement_types_survive_merge():
    rows = [Material(material_code='R1645', developer_code=dev,
                     placement_type=kind, placement='Knee, gusset, back')
            for dev, kind in [('B-10262', 'Shell 2_Fabric 2_Care'),
                              ('B-OTHER', 'Shell 2_Fabric 2_Care'),
                              ('B-10262', None)]]
    result = combine_pages([(63, PageResult(section_found=True, materials=rows))])
    assert len(result.materials) == 3
    assert result.materials[0].developer_code == 'B-10262'
    assert result.materials[0].placement_type == 'Shell 2_Fabric 2_Care'
    assert result.page_tables[0].materials[2].placement_type is None


@pytest.mark.parametrize('references, expected, conflict', [
    (['A-02916', 'TP 32197'], 'TP 32197', False),
    (['TP32197', 'tp 32197'], 'TP 32197', False),
    (['A-02916'], None, False),
    (['TP 32197', 'TP 31717'], None, True),
])
def test_only_tp_prefixed_numbers_participate_in_techpack_conflicts(references, expected, conflict):
    result = combine_pages([(i + 1, PageResult(section_found=True, tech_pack_number=value,
        materials=[Material(material_code='R1', quantity='1', unit='m')]))
        for i, value in enumerate(references)])
    assert result.tech_pack_number == expected
    assert any('Conflicting tech-pack numbers' in w for w in result.warnings) is conflict


def test_quantity_separates_printed_unit_before_merging():
    row = Material(material_code='R1', quantity='0.95 m', unit='m')
    assert row.quantity == '0.95'
    assert row.unit == 'm'
    assert Material(quantity='0.26 kg').unit == 'kg'
    assert Material(quantity='0,95', unit='m').quantity == '0,95'


def test_scope_keeps_header_wovens_and_knits_but_excludes_other_sections():
    scoped = scope_wovens_text(SOURCE)
    assert '9955' in scoped
    assert 'R1804' in scoped
    assert 'Knits' in scoped and 'R1963' in scoped
    assert 'Buttons' not in scoped
    assert 'R300410' not in scoped


def test_single_header_is_shared_by_every_material_not_its_color_code():
    page = PageResult(section_found=True, materials=[
        Material(material_code='R1371', colorways=[Colorway(code='9955', name='Black/HV Red', material_color_code='9900')]),
        Material(material_code='R1804', colorways=[Colorway(code='5500', name='Fluorescent red', material_color_code='5500')]),
        Material(material_code='R1963'),
        Material(material_code='R300410'),   # a Buttons row the model should not have returned
    ])
    normalized = normalize_wovens_page(page, SOURCE)
    assert [m.material_code for m in normalized.materials] == ['R1371', 'R1804', 'R1963']
    assert {v.code for m in normalized.materials for v in m.colorways} == {'9955'}
    assert normalized.materials[1].colorways[0].material_color_code == '5500'
    assert normalized.materials[1].colorways[0].name == 'Black/HV Red'
    assert any('Excluded R300410' in warning for warning in normalized.warnings)


def test_category_is_set_from_the_heading_in_the_pdf_text():
    # The model labelled the Knits row as wovens and the Wovens row as knits; the printed headings decide.
    page = PageResult(section_found=True, materials=[
        Material(material_code='R1371', category='knits'), Material(material_code='R1963', category='wovens')])
    normalized = normalize_wovens_page(page, SOURCE)
    assert {m.material_code: m.category for m in normalized.materials} == {'R1371': 'wovens', 'R1963': 'knits'}
    assert sum('category set to' in warning for warning in normalized.warnings) == 2
    # A row the text cannot place (not printed, or printed under both headings) keeps the model's label.
    both = SOURCE.replace('Knits\nR1963', 'Knits\nR1371\nR1963')
    kept = normalize_wovens_page(PageResult(section_found=True, materials=[
        Material(material_code='R1371', category='knits'), Material(material_code='R7777', category='knits')]), both)
    assert [m.category for m in kept.materials] == ['knits', 'knits']


def test_a_page_that_starts_with_knits_is_read_as_knits():
    from app.techpack_wovens import category_lines, section_lines
    source = 'Qty\n9900\nBlack\nKnits\nR1980\n0.02 m\nButtons\nR300410'
    lines, start, end = section_lines(source)
    wovens, knits = category_lines(lines, start, end)
    assert (lines[start], wovens, 'r1980' in knits, 'r300410' in knits) == ('Knits', set(), True, False)


def test_category_accepts_any_spelling_and_defaults_to_wovens():
    assert Material(category='Knits').category == 'knits'
    assert Material(category=' knitted fabrics ').category == 'knits'
    assert Material(category='Woven fabrics').category == 'wovens'
    assert Material().category == 'wovens' and Material(category=None).category == 'wovens'
    with pytest.raises(ValueError):
        Material(category='Buttons')


def test_results_saved_before_knits_existed_still_load_as_wovens():
    old = {'style_number': '1', 'materials': [{'material_code': 'R1', 'quantity': '1', 'unit': 'm'}],
           'page_tables': [{'page_number': 3, 'materials': [{'material_code': 'R1'}], 'colorway_headers': []}]}
    loaded = DocumentExtraction.model_validate(old)
    assert loaded.materials[0].category == 'wovens' and loaded.page_tables[0].materials[0].category == 'wovens'


def test_wovens_and_knits_rows_with_the_same_details_are_not_merged():
    rows = [Material(material_code='R1', quantity='1', unit='m', category='wovens'),
            Material(material_code='R1', quantity='1', unit='m', category='knits')]
    result = combine_pages([(1, PageResult(section_found=True, materials=rows))])
    assert [m.category for m in result.materials] == ['wovens', 'knits']
    # The same Knits row on two pages is still one row that collects both pages.
    again = combine_pages([(1, PageResult(section_found=True, materials=[rows[1]])), (2, PageResult(section_found=True, materials=[rows[1]]))])
    assert len(again.materials) == 1 and again.materials[0].source_pages == [1, 2]


def test_the_saved_material_rows_carry_their_category():
    from decimal import Decimal  # noqa: F401
    from uuid import uuid4
    from app.techpack_pipeline import write_material_rows
    captured = []
    class Session:
        def execute(self, statement): pass
        def add(self, row): captured.append(row)
    write_material_rows(Session(), uuid4(), DocumentExtraction(materials=[
        Material(material_code='R1', category='wovens'), Material(material_code='R2', category='knits')]))
    assert [(row.material_code, row.category) for row in captured] == [('R1', 'wovens'), ('R2', 'knits')]


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


def test_render_excludes_other_categories_from_both_image_and_text_but_keeps_knits():
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=400, height=600)
        for y, text in [(40, 'BOM'), (65, 'Qty'), (85, '9955'), (105, 'Black/HV Red'),
                        (130, 'Wovens'), (160, 'R1371'), (185, '0.95 m'),
                        (240, 'Knits'), (275, 'R1963'),
                        (360, 'Buttons'), (395, 'R300410')]:
            page.insert_text((30, y), text)
        image, text = render_page(pdf.tobytes(), 0)
    assert 'R1371' in text
    assert 'Knits' in text and 'R1963' in text
    assert 'R300410' not in text and 'Buttons' not in text
    with Image.open(BytesIO(image)) as rendered:
        # The 600pt page is about 1830px tall at 220 DPI. The crop ends just above Buttons (about 1060px), which is
        # well below Knits (about 730px; the old crop ended there at under 800px).
        assert 900 < rendered.height < 1150
        assert rendered.width > 1000


def test_a_page_with_a_knits_heading_and_a_bom_is_a_fabric_page():
    from app.techpack_pdf import locate_pages
    with pymupdf.open() as pdf:
        for text in ['Cover', 'BOM Knits R1980 Qty 0.02 m', 'How to measure']:
            pdf.new_page().insert_text((40, 60), text)
        selected, total = locate_pages(pdf.tobytes(), None)
    assert (selected, total) == ([1], 3)


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


def test_bom_title_gives_style_and_design_numbers_and_overrides_the_model():
    from app.techpack_wovens import bom_title_numbers
    assert bom_title_numbers('Tech Pack\n1459 - 1845 - BOM\nWovens') == ('1459', '1845')
    assert bom_title_numbers('1530-1310-bom') == ('1530', '1310')
    assert bom_title_numbers('no title here') == (None, None)
    page = PageResult(section_found=True, style_number='9999', design_number=None)
    fixed = normalize_wovens_page(page, '1449 - 1845 - BOM\nWovens\nR1\n')
    assert (fixed.style_number, fixed.design_number) == ('1449', '1845')


def test_design_numbers_merge_across_pages_and_keep_every_design():
    from app.techpack_merge import combine_pages
    row = {'material_code': 'R1', 'quantity': '1', 'unit': 'M', 'description': 'd'}
    pages = lambda *designs: [(i + 1, PageResult(section_found=True, style_number='1459', design_number=d,
        materials=[Material(**{**row, 'material_code': f'R{i}'})])) for i, d in enumerate(designs)]
    one = combine_pages(pages('1845', '1845', None))
    assert (one.design_number, one.design_numbers) == ('1845', ['1845'])
    # One Tech Pack can hold several designs; none of them is a conflict.
    many = combine_pages(pages('1845', '1146', '1142'))
    assert many.design_number is None and many.design_numbers == ['1845', '1146', '1142']
    assert not any('design' in w.lower() for w in many.warnings)


def test_titles_from_the_whole_pdf_add_every_design_and_fill_the_style():
    from app.techpack_merge import add_titles
    from app.techpack_schema import DocumentExtraction
    document = add_titles(DocumentExtraction(), [('1459', '1845'), ('1459', '1146'), ('1459', '1142')])
    assert (document.style_number, document.design_number, document.design_numbers) == ('1459', None, ['1845', '1146', '1142'])
    # The pages' own readings are kept after the titles, and a single design is also set as design_number.
    document = add_titles(DocumentExtraction(design_numbers=['1845']), [('1459', '1845')])
    assert (document.design_number, document.design_numbers) == ('1845', ['1845'])


def test_document_titles_are_read_from_pages_the_wovens_search_skips(tmp_path):
    import pymupdf
    from app.techpack_pdf import document_titles, render_page
    pdf = pymupdf.open()
    for text in ['Cover page', '1459 - 1845 - BOM\nWovens\nR1 Cotton', 'notes', '1459-1146 - BOM\nOther', '1459 - 1845 - BOM']:
        pdf.new_page().insert_text((72, 72), text)
    data = pdf.tobytes()
    assert document_titles(data) == [('1459', '1845'), ('1459', '1146')]
    # The scoped text given to the reader keeps the title that sits above the Wovens heading.
    assert bom_title_numbers(render_page(data, 1)[1]) == ('1459', '1845')