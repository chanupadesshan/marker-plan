import pymupdf
from app.pdf_processing import locate_pages
from app.merge import combine_pages
from app.schema import PageResult, Material, Colorway


def test_detects_dynamic_pages_not_hardcoded():
    pdf = pymupdf.open()
    for text in ["Cover tech pack", "Detail sketches", "BOM Wovens R1371 Qty 0.95 m", "How to measure", "BOM Wovens R1371 Qty 0.95 m"]:
        page = pdf.new_page()
        page.insert_text((40, 60), text)
    selected, total = locate_pages(pdf.tobytes(), None)
    assert total == 5
    assert selected == [2, 4]  # zero-index PDF pages 3 and 5


def test_combines_colorways_and_provenance():
    row1 = Material(material_code="R1371", description="100% cotton", placement="Main Fabric",
                    quantity="0.95", unit="m", colorways=[Colorway(code="8833", material_color_code="8800")])
    row2 = Material(material_code="R1371", description="100% cotton", placement="Main Fabric",
                    quantity="0.95", unit="m", colorways=[Colorway(code="9955", material_color_code="9900")])
    combined = combine_pages([
        (3, PageResult(section_found=True, style_number="7196", materials=[row1])),
        (5, PageResult(section_found=True, style_number="7196", materials=[row2])),
    ])
    assert len(combined.materials) == 1
    assert combined.materials[0].source_pages == [3, 5]
    assert {v.code for v in combined.materials[0].colorways} == {"8833", "9955"}


def test_does_not_merge_same_material_with_different_quantity():
    data = [(2, PageResult(section_found=True, materials=[Material(material_code="R1", quantity="1", unit="m")])),
            (3, PageResult(section_found=True, materials=[Material(material_code="R1", quantity="2", unit="m")]))]
    combined = combine_pages(data)
    assert len(combined.materials) == 2
    assert any("distinct BOM rows" in w for w in combined.warnings)
