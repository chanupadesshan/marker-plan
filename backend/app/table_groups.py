"""Extract disjoint table bands, splitting only at visible horizontal separators.

The context panel is for headers only; the target panel owns the rows returned by
that request. Successful parent results are never retained when a parent splits.
"""
from dataclasses import dataclass
from io import BytesIO
import re
from PIL import Image, ImageDraw, ImageOps
from .openrouter_client import OutputTokenLimitError
from .techpack_schema import PageResult
from .po_schema import POPageResult
from .po_merge import combine_po_pages


@dataclass(frozen=True)
class RowGroup:
    """
    Purpose: A horizontal band of a page's table rows that is sent to the model in one request.
    Input: top and bottom - the band's pixel positions; cuts - the row separators inside it;
    band_start and band_end - the numbers of the first and last separator bands it covers.
    Output: an immutable RowGroup; split() divides it in two when a reply was truncated.
    """
    top: int
    bottom: int
    cuts: tuple[int, ...]
    band_start: int
    band_end: int

    def split(self):
        """
        Purpose: Divide this group in two at its middle separator, used when a reply was truncated.
        Input: none (uses the group's own cut positions).
        Output: a pair of two smaller RowGroups that together cover the same rows, or None
        when the group has no separator left to split at.
        """
        if not self.cuts:
            return None
        index = len(self.cuts) // 2
        cut = self.cuts[index]
        middle = self.band_start + index
        return (RowGroup(self.top, cut, self.cuts[:index], self.band_start, middle),
                RowGroup(cut, self.bottom, self.cuts[index + 1:], middle + 1, self.band_end))


def _rule_positions(image):
    """
    Purpose: Find the horizontal ruled lines that separate table rows, using pixel geometry so
    invalid PDF text mappings do not affect split points. Only thin lines spanning the full content
    width count; partial cell borders and filled dark panels are ignored.
    Input: image - a PIL image of the page.
    Output: a sorted list of y positions (pixels from the top) of the separator lines.
    """
    # Inspect original pixels: shrinking can erase one-pixel rules entirely.
    width = image.width
    gray = image.convert('L')
    ink = ImageOps.invert(gray).point(lambda value: 255 if value >= 128 else 0).getbbox()
    if ink is None:
        return []
    pattern = re.compile(rb'[\x00-\x80]{' + str(max(30, round((ink[2] - ink[0]) * .65))).encode() + rb',}')
    pixels = gray.tobytes()
    candidates = []
    tolerance = max(2, round(width * .015))
    for y in range(gray.height):
        match = pattern.search(pixels[y * width:(y + 1) * width])
        # Reject partial cell borders: they must span the full content/table width.
        if match and match.start() <= ink[0] + tolerance and match.end() >= ink[2] - tolerance:
            candidates.append(y)
    runs = []
    for y in candidates:
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    # Ignore filled dark panels. A separator should be thin relative to the page.
    positions = [run[len(run) // 2] for run in runs
                 if len(run) <= max(5, round(gray.height * .006))]
    return sorted(set(y for y in positions if 4 < y < image.height - 4))


def _layout_cuts(image_bytes, proposed, group):
    """
    Purpose: Check row boundaries proposed by the model against the actual image, keeping only those
    that fall in a blank horizontal corridor of whitespace (so a split never cuts through text).
    Input: image_bytes - the page image; proposed - positions as integers from 0 to 1000 (fractions
    of the page height); group - the RowGroup being split.
    Output: a sorted list of safe cut positions in pixels, possibly empty.
    """
    with Image.open(BytesIO(image_bytes)) as image:
        gray = image.convert('L')
        pixels = gray.tobytes()
        cuts = []
        for value in proposed:
            if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 1000:
                continue
            center = round(value * image.height / 1000)
            radius = max(2, round(image.height * .003))
            for y in sorted(range(center - radius, center + radius + 1), key=lambda candidate: abs(candidate - center)):
                if not group.top + 6 < y < group.bottom - 6:
                    continue
                # Require a blank corridor, not just a white pixel row inside a glyph.
                if all(sum(pixel < 160 for pixel in pixels[line * image.width:(line + 1) * image.width])
                       <= max(1, round(image.width * .002)) for line in range(y - 2, y + 3)):
                    if not cuts or all(abs(y - cut) > 6 for cut in cuts):
                        cuts.append(y)
                    break
        return sorted(cuts)


def plan_groups(image_bytes, max_bands=6):
    """
    Purpose: Divide a page into bands of table rows at the visible ruled lines, so large tables
    are extracted in smaller requests. A page without ruled lines stays whole.
    Input: image_bytes - the page image; max_bands - the most separator bands in one group (default 6).
    Output: a list of RowGroups covering the page from top to bottom.
    """
    with Image.open(BytesIO(image_bytes)) as image:
        cuts = _rule_positions(image)
        # A page without a grid remains whole; never guess a midpoint through text.
        bounds = [0, *cuts, image.height]
        groups = []
        for offset in range(0, len(bounds) - 1, max(1, max_bands)):
            stop = min(offset + max(1, max_bands), len(bounds) - 1)
            groups.append(RowGroup(bounds[offset], bounds[stop], tuple(bounds[offset + 1:stop]), offset + 1, stop))
        return groups


def group_image(image_bytes, group):
    """
    Purpose: Build the image for one row group: a small full-page panel (outlined in red) above
    the full-width crop of the group, so the model sees the headers but extracts only the crop's rows.
    Input: image_bytes - the page image; group - the RowGroup to crop.
    Output: the combined JPEG as bytes.
    """
    with Image.open(BytesIO(image_bytes)) as original:
        original = original.convert('RGB')
        context = original.copy()
        context.thumbnail((1200, 1000))
        context_draw = ImageDraw.Draw(context)
        context_draw.rectangle((1, round(group.top * context.height / original.height), context.width - 2,
            min(context.height - 1, round(group.bottom * context.height / original.height))), outline='red', width=3)
        target = original.crop((0, group.top, original.width, group.bottom))
        width = max(context.width, target.width)
        canvas = Image.new('RGB', (width, context.height + target.height + 70), 'white')
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 6), 'CONTEXT: HEADERS ONLY - DO NOT EXTRACT ROWS FROM THIS PANEL', fill='black')
        canvas.paste(context, (0, 25))
        y = context.height + 40
        draw.text((10, y), 'TARGET: EXTRACT ONLY ROWS IN THE PANEL BELOW', fill='black')
        canvas.paste(target, (0, y + 25))
        output = BytesIO(); canvas.save(output, 'JPEG', quality=92)
        return output.getvalue()


def _combine(results, workflow, page_number):
    """
    Purpose: Merge the results of a page's row groups into one page result.
    Input: results - the per-group results (POPageResult for 'po', PageResult for 'techpack');
    workflow - 'po' or 'techpack'; page_number - the page they came from.
    Output: one page result. Raises RuntimeError for a Tech Pack when groups disagree on the style
    number, Tech Pack number or a colorway header name.
    """
    if workflow == 'po':
        combined = combine_po_pages([(page_number, result) for result in results])
        # Validate totals at the page/document level, not on incomplete row groups.
        for order in combined.orders:
            order.warnings = [warning for warning in order.warnings if not warning.startswith(
                ('Quantity validation incomplete:', 'Size quantity sum differs'))]
        kind = 'purchase_order' if combined.orders else ('empty' if all(result.page_kind == 'empty' for result in results) else 'other')
        return POPageResult(page_kind=kind, orders=combined.orders, warnings=combined.warnings)
    page = PageResult(section_found=any(result.section_found for result in results))
    headers = {}
    for result in results:
        for field in ('style_number', 'tech_pack_number'):
            current, incoming = getattr(page, field), getattr(result, field)
            if current and incoming and current != incoming:
                raise RuntimeError(f'Conflicting {field} between row groups; review the source page')
            if incoming:
                setattr(page, field, incoming)
        page.materials.extend(result.materials)
        page.warnings.extend(result.warnings)
        for header in result.colorway_headers:
            key = header.code or header.name
            if key in headers and headers[key].name and header.name and headers[key].name != header.name:
                raise RuntimeError('Conflicting colorway headers between row groups')
            if key not in headers or header.name:
                headers[key] = header
    page.colorway_headers = list(headers.values())
    return page


def extract_grouped(vlm, image_bytes, workflow, text='', *, groups_log=None, on_progress=None,
                    max_bands=6, max_calls=32):
    """
    Purpose: Extract one page with the model, splitting large tables into row groups. When a
    reply is cut off, that group is split in two at a row separator and retried (a layout request
    may propose more separators). Genuine repeated rows are kept in order.
    Input: vlm - the model client; image_bytes - the page image; workflow - 'techpack' or 'po';
    text - the page text (Tech Pack only); groups_log - a list that records each group's status;
    on_progress - callback given the combined result after each group; max_bands - bands per
    group; max_calls - the request cap per page (default 32).
    Output: the combined page result (PageResult or POPageResult). Raises RuntimeError when the cap
    is reached or no safe row boundary remains, and ValueError for an unknown workflow.
    """
    if workflow not in ('techpack', 'po'):
        raise ValueError('Unknown extraction workflow')
    groups = plan_groups(image_bytes, max_bands)
    results = []
    log = groups_log if groups_log is not None else []
    calls = 0
    layout_tried = False
    previous = getattr(vlm, 'current_group', None)

    def visit(group, identity, cropped):
        """
        Purpose: Extract one row group, and split it into two child groups if the reply was truncated.
        Input: group - the RowGroup; identity - its id such as '2.1'; cropped - True to send the
        context-plus-crop image, False to send the whole page.
        Output: nothing. Results are added to the shared list, and the log records the outcome.
        """
        nonlocal calls, layout_tried
        if calls >= max_calls:
            raise RuntimeError(f'Row-group request cap reached ({max_calls}); extraction is incomplete')
        calls += 1
        metadata = {'group': identity, 'band_start': group.band_start, 'band_end': group.band_end,
                    'crop_top': group.top, 'crop_bottom': group.bottom}
        entry = {**metadata, 'status': 'processing', 'result': None}
        log.append(entry)
        vlm.current_group = {**metadata, 'row_group_mode': cropped}
        try:
            image = group_image(image_bytes, group) if cropped else image_bytes
            # Full-page text could reintroduce rows outside the owned crop.
            result = vlm.extract(image, '' if cropped else text) if workflow == 'techpack' else vlm.extract_po(image)
            entry.update(status='completed', result=result.model_dump(mode='json'))
            results.append(result)
            if on_progress:
                on_progress(_combine(results, workflow, getattr(vlm, 'current_page', None) or 1))
        except OutputTokenLimitError as exc:
            children = group.split()
            if children is None and not layout_tried and hasattr(vlm, 'locate_table_rows'):
                layout_tried = True
                if calls >= max_calls:
                    entry['status'] = 'failed'
                    raise RuntimeError(f'Row-group request cap reached ({max_calls}); extraction is incomplete') from exc
                calls += 1
                try:
                    proposed = vlm.locate_table_rows(image_bytes, workflow)
                except Exception:
                    entry['status'] = 'failed'
                    raise
                cuts = _layout_cuts(image_bytes, proposed, group)
                if cuts:
                    group = RowGroup(group.top, group.bottom, tuple(cuts), group.band_start,
                                     group.band_start + len(cuts))
                    children = group.split()
            if children is None:
                entry['status'] = 'failed'
                raise RuntimeError('Output limit reached but no safe row boundary remains; extraction is incomplete') from exc
            entry['status'] = 'split'
            for index, child in enumerate(children, 1):
                visit(child, f'{identity}.{index}', True)
        except Exception:
            if entry['status'] != 'split':
                entry['status'] = 'failed'
            raise

    try:
        for index, group in enumerate(groups, 1):
            visit(group, str(index), len(groups) > 1)
        return _combine(results, workflow, getattr(vlm, 'current_page', None) or 1)
    finally:
        vlm.current_group = previous
