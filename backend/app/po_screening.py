"""Decide which pages of a purchase order belong to a Tech Pack before they are extracted in full.

One PO file can hold contracts for several models. Reading every page in full costs a model call per page, so each page's
header (Model ID and Quality ID) is read first: from the PDF text when it has any, otherwise by a small model call on the top
of the page. Only pages whose IDs fit the Tech Pack are then extracted.
"""
import re
from concurrent.futures import ThreadPoolExecutor
import pymupdf
from .config import get_settings
from .openrouter_client import fork
from .techpack_pdf import page_image

MODEL_LABEL = re.compile(r'\bModell?\s*ID\b', re.I)
MODEL_VALUE = re.compile(r'\bModell?\s*ID\s*:\s*(\d[\w./-]*)', re.I)
QUALITY_VALUE = re.compile(r'\bQuality\s*ID\s*:\s*(\d[\w./-]*)', re.I)
CONTRACT_VALUE = re.compile(r'\bContract\s*no\.?\s*:?\s*(\d[\w./-]*)', re.I)
# Below this many letters and digits a page has no usable text layer (a scanned or screenshot page can still carry
# a text layer made only of spaces and tabs).
MIN_TEXT = 40
# The header block sits in the top of the page; this share of the page height is read.
HEADER_SHARE = 0.45


def same_id(left, right):
    """Compare two business IDs ignoring case, spaces and punctuation."""
    clean = lambda value: ''.join(ch for ch in str(value) if ch.isalnum()).casefold()
    return clean(left) == clean(right)


def header_from_text(text):
    """
    Purpose: Read a page's header identifiers from its text layer.
    Input: text - the page's text.
    Output: {'contract_number', 'model_id', 'quality_id'} (each None when blank), or None when the page has no 'Model ID'
    label at all (a page that continues an earlier contract).
    """
    if not MODEL_LABEL.search(text):
        return None
    pick = lambda pattern: (pattern.search(text) or [None, None])[1]
    return {'contract_number': pick(CONTRACT_VALUE), 'model_id': pick(MODEL_VALUE), 'quality_id': pick(QUALITY_VALUE)}


def page_decision(header, style, designs):
    """
    Purpose: Decide whether one page's header fits the Tech Pack.
    Input: header - the page's identifiers; style - the Tech Pack's style number; designs - its design IDs.
    Output: 'skip' when the Model ID differs from the style number, or the Quality ID is not one of the design IDs;
    otherwise 'include' (a blank or unreadable ID is never a reason to skip).
    """
    if header.get('model_id') and style and not same_id(header['model_id'], style):
        return 'skip'
    if header.get('quality_id') and designs and not any(same_id(header['quality_id'], design) for design in designs):
        return 'skip'
    return 'include'


def _header_clip(page):
    return pymupdf.Rect(page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y0 + page.rect.height * HEADER_SHARE)


def screen_pages(pdf, style, designs, vlm=None):
    """
    Purpose: Screen every page of a PO against a Tech Pack.
    Input: pdf - an open PyMuPDF document; style - the Tech Pack's style number; designs - its design IDs; vlm - the model client
    used for pages with no text layer (pages are then read in parallel; if it is None or a read fails the page is included).
    Output: one record per page, in order: {'page', 'decision' ('include' or 'skip'), 'model_id', 'quality_id', 'contract_number',
    'source' ('text', 'image', 'inherited' or 'unread')}. A page with no header takes the decision of the page before it.
    """
    headers, to_read = {}, []
    for index in range(len(pdf)):
        page = pdf[index]
        text = page.get_text('text') or ''
        if sum(ch.isalnum() for ch in text) >= MIN_TEXT:
            headers[index] = (header_from_text(text), 'text')
        else:
            to_read.append((index, page_image(page, dpi=110, clip=_header_clip(page))))
    if to_read:
        def read(item):
            index, image = item
            if vlm is None:
                return index, None, 'unread', None
            child = fork(vlm)
            child.current_page, child.current_group = index + 1, None
            try:
                header = child.po_header(image).model_dump()
            except Exception:
                return index, {'contract_number': None, 'model_id': None, 'quality_id': None}, 'unread', child
            return index, (header if any(header.values()) else None), 'image', child
        with ThreadPoolExecutor(max_workers=max(1, min(len(to_read), get_settings().extraction_concurrency))) as pool:
            for index, header, source, child in pool.map(read, to_read):
                headers[index] = (header, source)
                if child is not None and vlm is not None:
                    vlm.request_usage.extend(child.request_usage)
    records, decision = [], 'include'
    for index in range(len(pdf)):
        header, source = headers.get(index, (None, 'unread'))
        if header is None:
            record = {'contract_number': None, 'model_id': None, 'quality_id': None}
            source = 'inherited' if index else source
        else:
            record = dict(header)
            decision = page_decision(record, style, designs)
        records.append({'page': index + 1, 'decision': decision, **record, 'source': source})
    return records


def skipped_notes(raw_pages):
    """
    Purpose: The note shown for each page that was skipped because it does not belong to the Tech Pack.
    Input: raw_pages - a PO's per-page records.
    Output: a list of strings such as 'Page 5 skipped (Model ID 1552, Quality ID 1648): it does not match this Tech Pack.'
    """
    notes = []
    for entry in raw_pages or []:
        if entry.get('status') != 'skipped':
            continue
        screen = entry.get('screen') or {}
        found = ', '.join(part for part in (f"Model ID {screen['model_id']}" if screen.get('model_id') else '',
                                            f"Quality ID {screen['quality_id']}" if screen.get('quality_id') else '') if part)
        notes.append(f"Page {entry['page']} skipped{f' ({found})' if found else ''}: it does not match this Tech Pack.")
    return notes
