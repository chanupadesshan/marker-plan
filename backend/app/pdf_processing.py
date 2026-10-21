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
from io import BytesIO
import pymupdf
from PIL import Image
from .config import get_settings
from .wovens import WOVENS_HEADING, NEXT_SECTION, scope_wovens_text

# match terms such as "Wovens","woven fabrics","woven fabric"
WOVENS = re.compile(r"\b(wovens|woven\s+fabrics?)\b", re.IGNORECASE)
# match terms such as "BOM", "Bill of Materials", "Material Consumption"
BOM = re.compile(r"\b(bom|bill\s+of\s+materials?|material\s+consumption)\b", re.IGNORECASE)
# match terms such as "Fabric", "Materials", "Shell", "Composition", "Qty", "Quantity"
FABRIC = re.compile(r"\b(fabrics?|materials?|shell|composition|qty|quantity)\b", re.IGNORECASE)


def page_image(page: pymupdf.Page, dpi: int = 220, clip=None) -> bytes:
    """
    convert a PDF pages into a JPEG image
    """
    dpi = min(max(dpi, 100), 300)
    pixmap = page.get_pixmap(dpi=dpi, alpha=False, clip=clip)
    img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def locate_pages(pdf_bytes: bytes, vlm=None) -> tuple[list[int], int]:
    """
    identify which pages contain Wovens BOM table, so the system doesn't try extracting materials from every page
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
        if get_settings().vision_page_classification and vlm is not None:
            for index in ambiguous:
                # Use a moderately sized image to locate category headings economically.
                image = page_image(pdf[index], dpi=145)
                vlm.current_page = index + 1
                if vlm.classify(image):
                    hits.add(index)
        return sorted(hits), len(pdf)


def render_page(pdf_bytes: bytes, page_index: int):
    """
    takes a PDF and a page index, then prepares that page for BOM extraction 
    It read the page's text, find the wovens section, and render an image of the page with the wovens section highlighted.
    """
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        page = pdf[page_index]
        text = page.get_text("text") or ""
        headings = []
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                label = ''.join(span['text'] for span in line['spans']).strip()
                if WOVENS_HEADING.fullmatch(label) or NEXT_SECTION.fullmatch(label):
                    headings.append((line['bbox'][1], label))
        headings.sort()
        start = next((y for y, label in headings if WOVENS_HEADING.fullmatch(label)), None)
        end = next((y for y, label in headings if start is not None and y > start and NEXT_SECTION.fullmatch(label)), None)
        clip = pymupdf.Rect(page.rect.x0, page.rect.y0, page.rect.x1, end) if end is not None else None
        return page_image(page, get_settings().page_dpi, clip=clip), scope_wovens_text(text)
