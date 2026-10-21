"""Render every PO page first, then extract sequentially with durable partial results."""
from uuid import UUID
from copy import deepcopy
import pymupdf
from .config import get_settings
from .database import SessionLocal
from .models import PurchaseOrderDocument, PurchaseOrderExtraction, TechPack
from .storage import get_bytes, put_bytes
from .techpack_pdf import trimmed_page_image
from .openrouter_client import OpenRouterVLM
from .po_merge import combine_po_pages
from .table_groups import extract_grouped
from .po_schema import POPageResult, load_saved_extraction


def association_warnings(session, document, orders):
    """
    Purpose: Warn when a PO was uploaded with a Tech Pack, or when a contract's Tech Pack ID
    differs from the linked Tech Pack's number. The link never proves the match.
    Input: session - a database session; document - the PurchaseOrderDocument; orders - its extracted orders.
    Output: a list of warning strings (empty when the PO has no linked Tech Pack).
    """
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


def process_purchase_order(document_id: str, resume: bool = False):
    """
    Purpose: Background job that renders every page of a PO PDF, then extracts the pages one
    at a time with the model. Results are saved after each page so a failure keeps the
    completed ones. On success the document needs review; on error it is marked failed.
    Input: document_id - the PO document's id as a string; resume - True to reuse completed
    pages and saved images from an earlier failed run (a retry).
    Output: nothing. The outcome is stored on the document: status 'needs_review' or 'failed',
    the extraction JSON, per-page results, page images and token usage.
    """
    doc_id = UUID(document_id)
    vlm = None
    pages, raw = [], []
    usage_history = []
    with SessionLocal() as session:
        document = session.get(PurchaseOrderDocument, doc_id)
        if document is None:
            return
        document.status, document.error_message = 'processing', None
        session.commit()
        if resume and document.extraction:
            raw = deepcopy(document.extraction.raw_page_results)
            usage_history = list(document.extraction.extracted_json.get('request_usage', []))

        def persist(complete=False):
            """
            Purpose: Save everything extracted so far and refresh the combined orders.
            Input: complete - True only for the final save, marking the extraction fully processed.
            Output: the combined POExtraction that was saved.
            """
            # Pending/failed pages can expose completed groups for inspection, but
            # source_complete still requires the entire page to finish.
            partial = [(entry['page'], POPageResult.model_validate(entry['result'])) for entry in raw
                       if entry['status'] != 'completed' and entry.get('result')]
            combined = combine_po_pages(pages + partial)
            combined.processing_complete = complete
            combined.request_usage = list(vlm.request_usage) if vlm else usage_history
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
            if resume:
                # Recover completed evidence before any source/storage operation can fail.
                for old in raw:
                    if old.get('status') == 'completed' and old.get('result'):
                        saved = load_saved_extraction({'page_results': [
                            {'page_number': old['page'], 'result': old['result']}]}).page_results[0].result
                        pages.append((old['page'], saved))
            data = get_bytes(document.minio_key)
            with pymupdf.open(stream=data, filetype='pdf') as pdf:
                document.page_count = len(pdf)
                if not len(pdf):
                    raise RuntimeError('PO PDF has no pages')
                session.commit()
                previous = {entry['page']: entry for entry in raw}
                raw = []
                for index, page in enumerate(pdf):
                    old = previous.get(index + 1)
                    if old and old.get('image_key'):
                        if old.get('status') == 'completed' and old.get('result'):
                            raw.append(old)
                            continue
                        if old.get('groups') or old.get('result'):
                            old.setdefault('previous_attempts', []).append({
                                'status': old.get('status'), 'groups': old.get('groups', []), 'result': old.get('result')})
                        old.update(status='pending', groups=[], result=None)
                        raw.append(old)
                        continue
                    key = f'purchase-orders/{doc_id}/page-images/page-{index + 1}.jpg'
                    put_bytes(key, trimmed_page_image(page, max(get_settings().page_dpi, 300)), 'image/jpeg')
                    raw.append({'page': index + 1, 'image_key': key, 'status': 'pending', 'result': None, 'groups': []})
            persist()
            vlm = OpenRouterVLM()
            vlm.request_usage = list(usage_history)
            for entry in raw:
                if entry['status'] == 'completed':
                    continue
                vlm.current_page = entry['page']
                def progress(result):
                    """
                    Purpose: Callback run after each group of rows; stores the partial page result and saves it.
                    Input: result - the POPageResult for the groups finished on the current page.
                    Output: nothing.
                    """
                    entry['result'] = result.model_dump(mode='json')
                    persist()
                result = extract_grouped(vlm, get_bytes(entry['image_key']), 'po',
                    groups_log=entry['groups'], on_progress=progress)
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
