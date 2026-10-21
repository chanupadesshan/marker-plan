"""
checks Wovens boundaries and colorway headers against the source PDF text, and normalizes the extracted page data accordingly.


Boundaries :

Wovens     <------- Start boundary
R1372
R1642
Knits      <------- End boundary
"""

import re
from .schema import ColorwayHeader, PageResult

WOVENS_HEADING = re.compile(r"^\s*(?:wovens|woven fabrics?)\s*$", re.I)
NEXT_SECTION = re.compile(
    r"^\s*(?:knits?|knitted fabrics?|trims?|buttons?|zippers?|interlinings?|"
    r"linings?|labels?|threads?|elastics?|packaging|accessories)(?:\s*\([^\n]*\))?\s*$", re.I,
)


def section_lines(text):
    """
    split the text into lines and find the start and end indexes of the Wovens section.
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if WOVENS_HEADING.fullmatch(line)), None)
    end = next((i for i in range(start + 1, len(lines)) if NEXT_SECTION.fullmatch(lines[i])), len(lines)) if start is not None else len(lines)
    return lines, start, end


def scope_wovens_text(text: str) -> str:
    """
    extract the text of the wovens section from the full page text, so that the VLM doesn't see unrelated content.
    """
    lines, start, end = section_lines(text)
    return '\n'.join(lines[:end]) if start is not None else text


def printed_headers(text):
    """
    extract the colorway headers from the source PDF text, so that the VLM doesn't have to guess them.
    """
    lines, start, _ = section_lines(text)
    if start is None:
        return []
    # Only read the column labels between Qty and Wovens, never body color codes.
    qty = next((i for i in range(start - 1, -1, -1) if re.fullmatch(r'\s*(?:qty|quantity)\s*', lines[i], re.I)), None)
    if qty is None:
        return []
    headers = []
    for line in lines[qty + 1:start]:
        line = line.strip()
        if re.fullmatch(r'\d{4}', line):
            headers.append(ColorwayHeader(code=line, name=''))
        elif headers and line:
            headers[-1].name = ' '.join(filter(None, [headers[-1].name, line]))
        elif line:
            return []  # Unrecognized header layout: leave it to visual extraction.
    return headers


def normalize_wovens_page(page: PageResult, source_text: str) -> PageResult:
    """
    Check Wovens boundaries and colorway headers against the source PDF text, and normalize the extracted page data accordingly.
    """
    page = page.model_copy(deep=True)
    if not page.section_found:
        page.materials = []
        return page
    lines, start, end = section_lines(source_text)
    if start is not None and end < len(lines):
        inside = {line.strip().casefold() for line in lines[start + 1:end]}
        outside = {line.strip().casefold() for line in lines[end:]}
        retained = []
        for row in page.materials:
            code = (row.material_code or '').strip().casefold()
            if code and code in outside and code not in inside:
                page.warnings.append(f'Excluded {row.material_code}: source row is outside Wovens')
            else:
                retained.append(row)
        page.materials = retained
    headers = printed_headers(source_text) or page.colorway_headers
    page.colorway_headers = headers
    if not headers:
        return page
    by_code = {header.code: header for header in headers if header.code}
    for row in page.materials:
        for variant in row.colorways:
            if variant.code in by_code:
                variant.name = by_code[variant.code].name
            elif len(headers) == 1 and len(row.colorways) == 1:
                variant.code, variant.name = headers[0].code, headers[0].name
            else:
                page.warnings.append(f'{row.material_code}: colorway {variant.code} does not match a column header; review assignment')
                variant.code, variant.name = None, None
    return page
