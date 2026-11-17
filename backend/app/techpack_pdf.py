"""
Locate and render Wovens BOM pages from a PDF document.
 This module uses PyMuPDF to read the PDF, extract text, and render images of the pages. 
 It also uses regular expressions to identify pages that contain Wovens BOM data based on specific keywords and headings. 
 The extracted text and images can be used for further processing or visual review.
Functions:
- page_image: Render a PDF page to a JPEG image.
- locate_pages: Identify pages in the PDF that contain Wovens BOM data.
- render_page: Extract text and render an image of a specific page in the PDF.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import pymupdf
from PIL import Image
from .config import get_settings
from .openrouter_client import fork
from .techpack_wovens import BOM_TITLE, NEXT_SECTION, is_fabric_heading, scope_wovens_text

# match terms such as "Wovens","woven fabrics","woven fabric", "Knits", "knitted fabrics" (both are read)
WOVENS = re.compile(r"\b(wovens|woven\s+fabrics?|knits|knitted\s+fabrics?)\b", re.IGNORECASE)
# match terms such as "BOM", "Bill of Materials", "Material Consumption"
BOM = re.compile(r"\b(bom|bill\s+of\s+materials?|material\s+consumption)\b", re.IGNORECASE)
# match terms such as "Fabric", "Materials", "Shell", "Composition", "Qty", "Quantity"
FABRIC = re.compile(r"\b(fabrics?|materials?|shell|composition|qty|quantity)\b", re.IGNORECASE)


def page_image(page: pymupdf.Page, dpi: int = 220, clip=None) -> bytes:
    """
    Purpose: Render one PDF page (or part of it) as a JPEG image.
    Input: page - a PyMuPDF page; dpi - resolution, limited to 100-300 (default 220);
    clip - optional rectangle in PDF points to render instead of the whole page.
    Output: the JPEG file contents as bytes.
    """
    dpi = min(max(dpi, 100), 300)
    pixmap = page.get_pixmap(dpi=dpi, alpha=False, clip=clip)
    img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def content_clip(page: pymupdf.Page, margin: float = 18, probe_dpi: int = 72):
    """
    Purpose: Find the area of a page that has printed content, ignoring white margins.
    Input: page - a PyMuPDF page; margin - extra space in PDF points kept around the content;
    probe_dpi - the low resolution used for the scan.
    Output: a pymupdf.Rect in PDF points inside the page, or None for a blank page.
    """
    pixmap = page.get_pixmap(dpi=probe_dpi, alpha=False)
    gray = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples).convert("L")
    box = gray.point(lambda value: 255 if value < 240 else 0).getbbox()
    if box is None:
        return None
    scale = 72 / probe_dpi
    rect = pymupdf.Rect(box[0] * scale, box[1] * scale, box[2] * scale, box[3] * scale)
    rect = pymupdf.Rect(rect.x0 - margin, rect.y0 - margin, rect.x1 + margin, rect.y1 + margin)
    return rect & page.rect


def trimmed_page_image(page: pymupdf.Page, dpi: int = 300) -> bytes:
    """
    Purpose: Render only the printed content of a page, so sparse pages give the model larger text.
    Input: page - a PyMuPDF page; dpi - resolution (default 300).
    Output: the cropped JPEG as bytes (the whole page if it is blank).
    """
    return page_image(page, dpi, clip=content_clip(page))


def locate_pages(pdf_bytes: bytes, vlm=None) -> tuple[list[int], int]:
    """
    Purpose: Find which pages contain a Wovens BOM table, so materials are not extracted from every page.
    Pages with both a Wovens and a BOM keyword count at once; unclear or image-only pages are
    checked visually with the model when that setting is on.
    Input: pdf_bytes - the PDF file contents; vlm - the model client used for the visual check (optional).
    Output: a tuple (page_indexes, total_pages): zero-based indexes of the Wovens pages in order,
    and the PDF's page count.
    """
    hits, ambiguous = set(), []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page_index in range(len(pdf)):
            text = pdf[page_index].get_text("text") or ""
            has_wovens = bool(WOVENS.search(text))
            has_bom = bool(BOM.search(text))
            if has_wovens and has_bom:
                hits.add(page_index)
            elif has_wovens or (has_bom and FABRIC.search(text)) or len(text.strip()) < 35:
                ambiguous.append(page_index)
        if get_settings().vision_page_classification and vlm is not None and ambiguous:
            # Use a moderately sized image to locate category headings economically. The images are rendered here, one
            # at a time (PyMuPDF is not thread safe); the model is then asked about several pages at once.
            images = [(index, page_image(pdf[index], dpi=145)) for index in ambiguous]

            def check(item):
                index, image = item
                child = fork(vlm)
                child.current_page = index + 1
                return index, child.classify(image), child

            pool = ThreadPoolExecutor(max_workers=min(get_settings().extraction_concurrency, len(images)))
            try:
                answers = [future.result() for future in [pool.submit(check, item) for item in images]]
            except BaseException:
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            pool.shutdown()
            for index, found, child in answers:
                vlm.request_usage.extend(child.request_usage)
                if found:
                    hits.add(index)
        return sorted(hits), len(pdf)


def document_titles(pdf_bytes: bytes) -> list[tuple[str, str]]:
    """
    Purpose: Read every BOM page title such as '1459 - 1845 - BOM' from the PDF's text layer. One Tech Pack can hold
    several designs, each with its own title, and a title is printed on pages the Wovens search does not pick.
    Input: pdf_bytes - the PDF file contents.
    Output: the distinct (style_number, design_number) pairs, in page order (empty for an image-only PDF).
    """
    found = {}
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
            for page in pdf:
                for match in BOM_TITLE.finditer(page.get_text("text") or ""):
                    found.setdefault((match[1], match[2]), None)
    except Exception:
        # The titles are extra evidence; an unreadable PDF fails later, in page location, with its own message.
        return []
    return list(found)


def render_page(pdf_bytes: bytes, page_index: int):
    """
    Purpose: Prepare one page for extraction: render its image, cut off everything below the Wovens and
    Knits sections when a heading of another category (such as Buttons) follows, and limit the text layer the same way.
    Input: pdf_bytes - the PDF file contents; page_index - zero-based page number.
    Output: a tuple (jpeg_bytes, fabric_text): the page image and the text scoped to the Wovens and Knits sections.
    """
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        page = pdf[page_index]
        text = page.get_text("text") or ""
        headings = []
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                label = ''.join(span['text'] for span in line['spans']).strip()
                if is_fabric_heading(label) or NEXT_SECTION.fullmatch(label):
                    headings.append((line['bbox'][1], label))
        headings.sort()
        start = next((y for y, label in headings if is_fabric_heading(label)), None)
        end = next((y for y, label in headings if start is not None and y > start and NEXT_SECTION.fullmatch(label)), None)
        clip = pymupdf.Rect(page.rect.x0, page.rect.y0, page.rect.x1, end) if end is not None else None
        scoped = scope_wovens_text(text)
        # The title above the Wovens heading ('1459 - 1845 - BOM') is cut off by the scoping but names the style and design.
        title = BOM_TITLE.search(text)
        if title and not BOM_TITLE.search(scoped):
            scoped = f"{title[0]}\n{scoped}"
        return page_image(page, get_settings().page_dpi, clip=clip), scoped
