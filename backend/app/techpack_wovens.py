"""
checks the fabric (Wovens and Knits) boundaries and colorway headers against the source PDF text, and normalizes the
extracted page data accordingly.


Boundaries :

Wovens     <------- Start boundary
R1372
R1642
Knits      <------- still inside: Knits is read too
R1980
Buttons    <------- End boundary (any other category)
"""

import re
from .techpack_schema import ColorwayHeader, PageResult

WOVENS_HEADING = re.compile(r"^\s*(?:wovens|woven fabrics?)\s*$", re.I)
KNITS_HEADING = re.compile(r"^\s*(?:knits?|knitted fabrics?)(?:\s*\([^\n]*\))?\s*$", re.I)
# A heading for any category other than Wovens and Knits ends the fabric section.
NEXT_SECTION = re.compile(
    r"^\s*(?:trims?|buttons?|zippers?|interlinings?|"
    r"linings?|labels?|threads?|elastics?|packaging|accessories)(?:\s*\([^\n]*\))?\s*$", re.I,
)


def is_fabric_heading(label):
    """
    Purpose: Tell whether a line is a Wovens or Knits section heading.
    Input: label - one line of page text.
    Output: True for 'Wovens', 'Woven fabrics', 'Knits' or 'Knitted fabrics' (any case), otherwise False.
    """
    return bool(WOVENS_HEADING.fullmatch(label) or KNITS_HEADING.fullmatch(label))


def section_lines(text):
    """
    Purpose: Split page text into lines and find where the fabric section (Wovens and Knits) starts and ends.
    Input: text - the page's text layer.
    Output: a tuple (lines, start, end): the list of lines, the index of the first Wovens or Knits heading
    (None if there is none), and the index of the next heading of another category such as Buttons
    (the number of lines when no later heading exists).
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if is_fabric_heading(line)), None)
    end = next((i for i in range(start + 1, len(lines)) if NEXT_SECTION.fullmatch(lines[i])), len(lines)) if start is not None else len(lines)
    return lines, start, end


def scope_wovens_text(text: str) -> str:
    """
    Purpose: Cut the page text off at the end of the Wovens and Knits sections, so the model does not see later categories.
    Input: text - the page's full text layer.
    Output: the text up to the next category heading, or the original text if no Wovens or Knits heading is found.
    """
    lines, start, end = section_lines(text)
    return '\n'.join(lines[:end]) if start is not None else text


def category_lines(lines, start, end):
    """
    Purpose: Split the fabric section into what sits under the Wovens heading and what sits under the Knits heading.
    Input: lines, start, end - as returned by section_lines().
    Output: (wovens, knits): two sets of lowercase, trimmed line texts, so a material code can be looked up in each.
    A line before any heading of the section belongs to neither.
    """
    wovens, knits, current = set(), set(), None
    # Start at the heading that opens the section, so the first rows belong to it.
    for line in lines[start:end] if start is not None else []:
        if WOVENS_HEADING.fullmatch(line):
            current = wovens
        elif KNITS_HEADING.fullmatch(line):
            current = knits
        elif current is not None:
            current.add(line.strip().casefold())
    return wovens, knits


def printed_headers(text):
    """
    Purpose: Read the colorway column headers (4-digit code plus name) printed above the Wovens heading,
    so the model does not have to guess them.
    Input: text - the page's text layer.
    Output: a list of ColorwayHeader objects, or an empty list when the layout is not recognized.
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


BOM_TITLE = re.compile(r"\b(\d{3,6})\s*[-–]\s*(\d{3,6})\s*[-–]\s*BOM\b", re.I)


def bom_title_numbers(text):
    """
    Purpose: Read the style and design numbers from a BOM page title such as '1459 - 1845 - BOM'.
    Input: text - the page's text layer.
    Output: (style_number, design_number), or (None, None) when no such title is printed.
    """
    match = BOM_TITLE.search(text or '')
    return (match[1], match[2]) if match else (None, None)


def normalize_wovens_page(page: PageResult, source_text: str) -> PageResult:
    """
    Purpose: Check a model-extracted page against the PDF's own text: drop rows that belong to a later category
    (anything but Wovens and Knits), set each row's Wovens/Knits category from the heading it sits under, and
    replace colorway names with the printed headers.
    Input: page - the PageResult from the model; source_text - the page's text layer.
    Output: a corrected copy of the PageResult, with warnings added for rows removed, categories changed or
    colorways that do not match any column header. The input is not modified.
    """
    page = page.model_copy(deep=True)
    if not page.section_found:
        page.materials = []
        return page
    # The printed title in the text layer is more reliable than the model's reading of it.
    style, design = bom_title_numbers(source_text)
    if style:
        page.style_number, page.design_number = style, design
    lines, start, end = section_lines(source_text)
    if start is not None and end < len(lines):
        inside = {line.strip().casefold() for line in lines[start + 1:end]}
        outside = {line.strip().casefold() for line in lines[end:]}
        retained = []
        for row in page.materials:
            code = (row.material_code or '').strip().casefold()
            if code and code in outside and code not in inside:
                page.warnings.append(f'Excluded {row.material_code}: source row is outside the Wovens and Knits sections')
            else:
                retained.append(row)
        page.materials = retained
    if start is not None:
        # The text layer is more reliable than the model about which heading a row sits under.
        wovens, knits = category_lines(lines, start, end)
        for row in page.materials:
            code = (row.material_code or '').strip().casefold()
            expected = 'knits' if code in knits and code not in wovens else 'wovens' if code in wovens and code not in knits else None
            if expected and row.category != expected:
                page.warnings.append(f'{row.material_code}: category set to {expected.capitalize()} from the section heading in the PDF text')
                row.category = expected
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
