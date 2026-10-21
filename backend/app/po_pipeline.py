"""Render every PO page first, then extract sequentially with durable partial results."""
from uuid import UUID
from copy import deepcopy
import pymupdf
from .config import get_settings
from .database import SessionLocal
from .models import PurchaseOrderDocument, PurchaseOrderExtraction, TechPack
from .storage import get_bytes, put_bytes
from .pdf_processing import page_image
from .vlm import OpenRouterVLM
from .po_merge import combine_po_pages


def association_warnings(session, document, orders):
    if not document.tech_pack_id:
        return []
    linked = session.get(TechPack, document.tech_pack_id)
    reference = (linked.extraction.extracted_json.get('tech_pack_number')
                 if linked and linked.extraction else None)
    warnings = ['Uploaded alongside a Tech Pack; business-reference matching requires review']
    if reference:
        for order in orders:
            if order.tech_pack_reference and order.tech_pack_reference != reference:
                warnings.append(f'Contract {order.contract_number or "unknown"}: Tech Pack reference differs from the linked extraction')
    return warnings


def process_purchase_order(document_id: str):
    doc_id = UUID(document_id)
    vlm = None
    pages, raw = [], []
    with SessionLocal() as session:
        document = session.get(PurchaseOrderDocument, doc_id)
        if document is None:
            return
        document.status, document.error_message = 'processing', None
        session.commit()

        def persist(complete=False):
            combined = combine_po_pages(pages)
            combined.processing_complete = complete
            combined.request_usage = list(vlm.request_usage) if vlm else []
            combined.warnings.extend(association_warnings(session, document, combined.orders))
            extraction = document.extraction
            if extraction is None:
                extraction = PurchaseOrderExtraction(document_id=doc_id,
                    model_name=get_settings().openrouter_model, extracted_json={}, raw_page_results=[], warnings=[])
                document.extraction = extraction
                session.add(extraction)
            extraction.extracted_json = combined.model_dump(mode='json')
            # JSONB change detection needs an independent snapshot of nested entries.
            extraction.raw_page_results = deepcopy(raw)
            extraction.warnings = combined.warnings
            session.commit()
            return combined

        try:
            data = get_bytes(document.minio_key)
            with pymupdf.open(stream=data, filetype='pdf') as pdf:
                document.page_count = len(pdf)
                if not len(pdf):
                    raise RuntimeError('PO PDF has no pages')
                session.commit()
                for index, page in enumerate(pdf):
                    key = f'purchase-orders/{doc_id}/page-images/page-{index + 1}.jpg'
                    put_bytes(key, page_image(page, get_settings().page_dpi), 'image/jpeg')
                    raw.append({'page': index + 1, 'image_key': key, 'status': 'pending', 'result': None})
            persist()
            vlm = OpenRouterVLM()
            for entry in raw:
                vlm.current_page = entry['page']
                result = vlm.extract_po(get_bytes(entry['image_key']))
                # Assign provenance from the PDF, never the model's claimed page numbers.
                for order in result.orders:
                    order.source_pages = [entry['page']]
                    for row in order.size_rows:
                        row.source_page = entry['page']
                entry.update(status='completed', result=result.model_dump(mode='json'))
                pages.append((entry['page'], result))
                persist()
            combined = persist()
            if not combined.orders:
                raise RuntimeError('No purchase orders were extracted; review the source PDF and page outcomes')
            document.status = 'needs_review'
            persist(complete=True)
        except Exception as exc:
            session.rollback()
            document = session.get(PurchaseOrderDocument, doc_id)
            if document is None:
                return
            document.status = 'failed'
            document.error_message = str(exc)[:1000]
            for entry in raw:
                if vlm and entry['page'] == vlm.current_page and entry['status'] == 'pending':
                    entry['status'] = 'failed'
            persist(complete=False)
            print(f'PO extraction failed for {doc_id}: {type(exc).__name__}')
