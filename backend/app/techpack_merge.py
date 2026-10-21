"""
Combine Wovens BOM results from multiple PDF pages into one document result.

Merge material rows when their code, description, placement, quantity, and unit
match, collecting their colorways and source page numbers together.

Keep differing rows separate and add warnings for conflicts or missing values.
Preserve individual page tables for display and keep manual corrections consistent
with the combined material records.
"""

import re
from decimal import Decimal, InvalidOperation
from .techpack_schema import PageResult, DocumentExtraction, Material, WovensPageTable


def canonical(text: str | None) -> str:
    """
    Purpose: Prepare a string for comparison by lowercasing it and removing everything except letters and digits.
    Input: text - any string, or None.
    Output: the normalized string ('' when the input is None or empty).
    """
    return re.sub(r"[^a-z0-9]+", "", (text or "").casefold())


def parse_quantity(value: str | None):
    """
    Purpose: Convert a printed quantity such as '0.95' or '1,5' into a number.
    Input: value - the quantity text, or None.
    Output: a Decimal, or None when the value is empty or not numeric.
    """
    if not value:
        return None
    try:
        return Decimal(value.strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def canonicalize_corrections(payload: DocumentExtraction) -> DocumentExtraction:
    """
    Purpose: Keep a manually edited extraction consistent. An extraction has two views of the
    same data: page_tables (per page) and materials (combined across pages). The page tables
    are the source of truth, so the combined list is rebuilt from them.
    Input: payload - the corrected DocumentExtraction submitted by the user.
    Output: a DocumentExtraction with materials, page_tables, source_pages and warnings rebuilt
    from the page tables. Raises ValueError if the submitted materials contradict the page tables.
    """
    if not payload.page_tables:
        return payload
    combined = combine_pages([
        (table.page_number, PageResult(section_found=True, materials=table.materials,
                                      colorway_headers=table.colorway_headers))
        for table in payload.page_tables
    ])
    if 'materials' in payload.model_fields_set and payload.materials != combined.materials:
        raise ValueError('Conflicting materials and page_tables. Edit page_tables and omit the derived materials field.')
    return payload.model_copy(update={
        'materials': combined.materials, 'page_tables': combined.page_tables,
        'source_pages': combined.source_pages,
        'warnings': list(dict.fromkeys(payload.warnings + combined.warnings)),
    })


def combine_pages(results: list[tuple[int, PageResult]]) -> DocumentExtraction:
    """
    Purpose: Combine the Wovens results of several PDF pages into one document result, merging
    matching rows, collecting colorways and source pages, and warning about conflicts or gaps
    (different style or Tech Pack numbers, missing codes, quantities or units).
    Input: results - a list of (page_number, PageResult) pairs.
    Output: one DocumentExtraction with the merged materials, per-page tables, source pages and warnings.
    """
    warnings: list[str] = []
    merged: dict[tuple, Material] = {}
    seen_codes: dict[str, set[tuple]] = {}
    styles, tech_packs = set(), set()
    pages: list[int] = []
    page_tables = []
    for page_number, page in results:
        if not page.section_found:
            warnings.append(f"Page {page_number}: candidate did not contain a Wovens BOM")
            continue
        pages.append(page_number)
        page_tables.append(WovensPageTable(
            page_number=page_number,
            materials=[row.model_copy(update={'source_pages': [page_number]}, deep=True) for row in page.materials],
            colorway_headers=page.colorway_headers,
        ))
        if page.style_number:
            styles.add(page.style_number.strip())
        if page.tech_pack_number:
            tech_packs.add(page.tech_pack_number.strip())
        warnings.extend(f"Page {page_number}: {w}" for w in page.warnings)
        occurrences = {}
        for row_index, item in enumerate(page.materials):
            row = item.model_copy(deep=True)
            row.source_pages = [page_number]
            if not row.material_code:
                warnings.append(f"Page {page_number}: material without a material code")
            if parse_quantity(row.quantity) is None:
                warnings.append(f"Page {page_number}: missing or nonnumeric quantity for {row.material_code}")
            if not row.unit:
                warnings.append(f"Page {page_number}: missing unit for {row.material_code}")
            # Same material/code can legitimately occur at different placements or quantities.
            # Do not collapse such entries into one line.
            key = (canonical(row.material_code), canonical(row.description),
                   canonical(row.placement), canonical(row.quantity), canonical(row.unit))
            if not row.material_code:
                # Rows without identifiers must not be merged just because fields match.
                key = ("unidentified", page_number, row_index)
            # Chunk crops do not overlap: repeated physical rows on this page are
            # genuine evidence, not duplicate extraction to collapse. Across pages
            # the corresponding occurrence may still collect other colorways.
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence + 1
            key = (*key, occurrence)
            if row.material_code:
                seen_codes.setdefault(canonical(row.material_code), set()).add(key)
            if key not in merged:
                merged[key] = row
                continue
            previous = merged[key]
            previous.source_pages = sorted(set(previous.source_pages + row.source_pages))
            for variant in row.colorways:
                signature = (canonical(variant.code), canonical(variant.material_color_code), canonical(variant.fabric_reference))
                signatures = {(canonical(v.code), canonical(v.material_color_code), canonical(v.fabric_reference)) for v in previous.colorways}
                if signature not in signatures:
                    if any(canonical(v.code) == canonical(variant.code) for v in previous.colorways):
                        warnings.append(f"Colorway conflict for {row.material_code} / {variant.code}; both versions preserved")
                    previous.colorways.append(variant)
    for code, keys in seen_codes.items():
        if len(keys) > 1:
            warnings.append(f"Material {code.upper()} appears in {len(keys)} distinct BOM rows; review grouping")
    if len(styles) > 1:
        warnings.append("Conflicting style numbers found: " + ", ".join(sorted(styles)))
    if len(tech_packs) > 1:
        warnings.append("Conflicting tech-pack numbers found: " + ", ".join(sorted(tech_packs)))
    if not merged:
        warnings.append("No woven materials were extracted; manual review is required")
    return DocumentExtraction(
        style_number=next(iter(styles)) if len(styles) == 1 else None,
        tech_pack_number=next(iter(tech_packs)) if len(tech_packs) == 1 else None,
        materials=list(merged.values()),
        source_pages=sorted(set(pages)),
        warnings=warnings,
        page_tables=page_tables,
    )
