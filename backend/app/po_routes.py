"""PO upload, inspection and review, independently of Tech Pack processing."""
import hashlib
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .config import get_settings
from .database import SessionLocal
from .models import PurchaseOrderDocument, TechPack
from .po_schema import POCorrections, POExtraction, load_saved_extraction
from .po_merge import validate_totals, combine_po_pages
from .po_pipeline import process_purchase_order, association_warnings
from .storage import delete_prefix, get_bytes, put_bytes

router = APIRouter(prefix='/api/purchase-orders', tags=['Purchase orders'])


def summary(row):
    """
    Purpose: Build the short description of a PO that the list and detail endpoints return.
    Input: row - a PurchaseOrderDocument.
    Output: a dict with id, filename, status, error, page_count, tech_pack_id and created_at.
    """
    return {'id': str(row.id), 'filename': row.original_filename, 'status': row.status,
            'error': row.error_message, 'page_count': row.page_count,
            'tech_pack_id': str(row.tech_pack_id) if row.tech_pack_id else None,
            'created_at': row.created_at.isoformat() if row.created_at else None}


def find(session, doc_id, require_extraction=False):
    """
    Purpose: Load a PO document or stop the request with a 404.
    Input: session - a database session; doc_id - the PO's id; require_extraction - also require
    that an extraction exists.
    Output: the PurchaseOrderDocument. Raises HTTP 404 when it (or its required extraction) is missing.
    """
    row = session.get(PurchaseOrderDocument, doc_id)
    if row is None or (require_extraction and row.extraction is None):
        raise HTTPException(404, 'Purchase order or extraction not found')
    return row


def source_complete(row):
    """
    Purpose: Decide whether every PDF page was extracted successfully, which is required before approval.
    Input: row - a PurchaseOrderDocument.
    Output: True only when the status is needs_review or approved, processing finished, and every
    page from 1 to page_count has a completed result; otherwise False.
    """
    if row.status not in ('needs_review', 'approved') or not row.extraction or not row.page_count:
        return False
    raw = row.extraction.raw_page_results
    return (row.extraction.extracted_json.get('processing_complete') is True
            and len(raw) == row.page_count
            and {entry.get('page') for entry in raw} == set(range(1, row.page_count + 1))
            and all(entry.get('status') == 'completed' for entry in raw))


def review_data(session, row):
    """
    Purpose: Prepare a PO's saved extraction for display, refreshing the Tech Pack link warnings
    because the linked Tech Pack may have finished extracting after this PO did.
    Input: session - a database session; row - a PurchaseOrderDocument that has an extraction.
    Output: the extraction as a dict, with up-to-date warnings.
    """
    data = load_saved_extraction(row.extraction.extracted_json).model_dump(mode='json')
    data['warnings'] = [warning for warning in data['warnings']
        if warning != 'Uploaded alongside a Tech Pack; business-reference matching requires review'
        and not (warning.startswith('Contract ') and warning.endswith('Tech Pack reference differs from the linked extraction'))]
    data['warnings'].extend(association_warnings(session, row,
        POExtraction.model_validate(data).orders))
    return data


@router.post('/upload', status_code=202)
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                 tech_pack_id: UUID | None = Form(None)):
    """
    Purpose: Upload a PO PDF, store it, and queue its extraction in the background.
    Input: file - the PDF (multipart field 'file', within the size limit); tech_pack_id - optional id of a Tech Pack to link.
    Output: the PO's summary (HTTP 202). Raises 400 if it is not a PDF, 413 if too large, 404 if the linked Tech Pack
    does not exist, 503 if storage fails.
    """
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, 'PDF exceeds maximum upload size')
    if not data.startswith(b'%PDF-'):
        raise HTTPException(400, 'Upload must be a PDF file')
    filename = Path((file.filename or 'purchase-order.pdf').replace('\\', '/')).name[:255] or 'purchase-order.pdf'
    doc_id = uuid4()
    key = f'purchase-orders/{doc_id}/source/{filename}'
    with SessionLocal() as session:
        if tech_pack_id and session.get(TechPack, tech_pack_id) is None:
            raise HTTPException(404, 'Linked Tech Pack not found')
        try:
            put_bytes(key, data, 'application/pdf')
        except Exception as exc:
            raise HTTPException(503, 'Unable to save PDF to object storage') from exc
        row = PurchaseOrderDocument(id=doc_id, tech_pack_id=tech_pack_id, original_filename=filename,
            minio_key=key, sha256=hashlib.sha256(data).hexdigest(), status='queued')
        session.add(row)
        session.commit()
        result = summary(row)
    background_tasks.add_task(process_purchase_order, str(doc_id))
    return result


@router.get('')
def list_purchase_orders():
    """
    Purpose: List the most recent purchase orders, with the identifiers the sidebar searches on.
    Input: none.
    Output: up to 100 summaries, newest first, each with contract_count, contract_numbers and
    tech_pack_references (the full extraction is not included).
    """
    with SessionLocal() as session:
        rows = session.scalars(select(PurchaseOrderDocument).options(selectinload(PurchaseOrderDocument.extraction))
                               .order_by(PurchaseOrderDocument.created_at.desc()).limit(100)).all()
        items = []
        for row in rows:
            item = summary(row)
            # Searchable identifiers only; the full extraction is loaded on selection.
            orders = row.extraction.extracted_json.get('orders', []) if row.extraction else []
            item.update(contract_count=len(orders),
                        contract_numbers=[order.get('contract_number') for order in orders if order.get('contract_number')],
                        tech_pack_references=sorted({order.get('tech_pack_reference') for order in orders
                                                     if order.get('tech_pack_reference')}))
            items.append(item)
        return items


@router.get('/{doc_id}')
def details(doc_id: UUID):
    """
    Purpose: Return one PO with its full extraction for review.
    Input: doc_id - the PO's id.
    Output: the summary plus extraction, model name, request_usage and approval_ready (true when every
    page completed). Raises 404 if not found.
    """
    with SessionLocal() as session:
        row = find(session, doc_id)
        result = summary(row)
        result.update(extraction=review_data(session, row) if row.extraction else None,
                      model=row.extraction.model_name if row.extraction else None,
                      request_usage=row.extraction.extracted_json.get('request_usage', []) if row.extraction else [],
                      approval_ready=source_complete(row))
        return result


@router.delete('/{doc_id}')
def delete_purchase_order(doc_id: UUID):
    """
    Purpose: Permanently remove a PO: its row and extraction (cascade), then its stored PDF and page images.
    Input: doc_id - the PO's id.
    Output: {'ok': True}. Raises 404 if not found, and 409 while the PO is queued or processing.
    """
    with SessionLocal() as session:
        row = find(session, doc_id)
        if row.status in ('queued', 'processing'):
            raise HTTPException(409, 'Wait for extraction to finish before deleting')
        session.delete(row)
        session.commit()
    delete_prefix(f'purchase-orders/{doc_id}/')
    return {'ok': True}


@router.get('/{doc_id}/pdf')
def original(doc_id: UUID):
    """
    Purpose: Serve the PO's original PDF for viewing.
    Input: doc_id - the PO's id.
    Output: the PDF file (application/pdf). Raises 404 if not found, 503 if storage cannot return it.
    """
    with SessionLocal() as session:
        row = find(session, doc_id)
        try:
            data = get_bytes(row.minio_key)
        except Exception as exc:
            raise HTTPException(503, 'Unable to retrieve PDF') from exc
        return Response(data, media_type='application/pdf', headers={'Content-Disposition': 'inline; filename=purchase-order.pdf'})


@router.get('/{doc_id}/json')
def export(doc_id: UUID):
    """
    Purpose: Download the PO's complete extraction as a JSON file.
    Input: doc_id - the PO's id.
    Output: the extraction JSON as an attachment. Raises 404 if the PO or its extraction is missing.
    """
    with SessionLocal() as session:
        row = find(session, doc_id, True)
        return JSONResponse(review_data(session, row),
            headers={'Content-Disposition': f'attachment; filename="purchase-orders-{doc_id}.json"'})


@router.put('/{doc_id}/extraction')
def corrections(doc_id: UUID, payload: POCorrections):
    """
    Purpose: Save manual corrections to a PO's orders and recalculate the quantity warnings.
    Input: doc_id - the PO's id; payload - the corrected orders as {'orders': [...]}, whose
    source pages must refer to completed PDF pages.
    Output: {'ok': True, 'status': <new status>}. Raises 404 if not found, 409 while processing, 400 for invalid source pages.
    """
    with SessionLocal() as session:
        row = find(session, doc_id, True)
        if row.status in ('queued', 'processing'):
            raise HTTPException(409, 'Wait for processing before editing')
        saved = load_saved_extraction(row.extraction.extracted_json)
        valid_pages = {entry['page'] for entry in row.extraction.raw_page_results if entry.get('status') == 'completed'}
        for order in payload.orders:
            if any(page not in valid_pages for page in order.source_pages) or any(
                    size.source_page is not None and size.source_page not in valid_pages for size in order.size_rows):
                raise HTTPException(400, 'Source pages must refer to completed PDF pages')
            # Recalculate validation warnings; extraction evidence and usage remain unchanged.
            order.warnings = [warning for warning in order.warnings
                              if not warning.startswith(('Quantity validation incomplete:', 'Size quantity sum differs'))]
            validate_totals(order)
        saved.orders = payload.orders
        saved.warnings = [f'Page {page.page_number}: {warning}' for page in saved.page_results for warning in page.result.warnings]
        saved.warnings.extend(association_warnings(session, row, saved.orders))
        row.extraction.extracted_json = saved.model_dump(mode='json')
        row.extraction.warnings = saved.warnings
        if row.status != 'failed':
            row.status = 'needs_review'
        session.commit()
        return {'ok': True, 'status': row.status}


@router.post('/{doc_id}/approve')
def approve(doc_id: UUID):
    """
    Purpose: Mark a PO as approved after the user has checked it against the PDF.
    Input: doc_id - the PO's id.
    Output: {'ok': True, 'status': 'approved'}. Raises 400 if any page is incomplete or there are no orders, 404 if not found.
    """
    with SessionLocal() as session:
        row = find(session, doc_id, True)
        if not source_complete(row) or not row.extraction.extracted_json.get('orders'):
            raise HTTPException(400, 'Cannot approve empty or incomplete PO processing')
        row.status = 'approved'
        session.commit()
        return {'ok': True, 'status': row.status}


@router.post('/{doc_id}/retry', status_code=202)
def retry_failed(doc_id: UUID, background_tasks: BackgroundTasks):
    """
    Purpose: Queue a retry of a failed PO that continues from its unfinished pages, keeping completed ones.
    Input: doc_id - the PO's id.
    Output: the PO's summary (HTTP 202). Raises 404 if not found, 409 if it is not failed or has manual corrections
    that a retry would overwrite.
    """
    with SessionLocal() as session:
        # Serialize retry requests so two clicks cannot schedule the same failed PO.
        row = session.get(PurchaseOrderDocument, doc_id, with_for_update=True)
        if row is None:
            raise HTTPException(404, 'Purchase order not found')
        if row.status != 'failed':
            raise HTTPException(409, 'Only failed PO processing can be retried')
        if row.extraction:
            saved = load_saved_extraction(row.extraction.extracted_json)
            rebuilt = combine_po_pages([(page.page_number, page.result) for page in saved.page_results])
            if saved.orders != rebuilt.orders:
                raise HTTPException(409, 'This PO has manual corrections. Export them before starting a new extraction; retry will not overwrite edited results.')
        row.status, row.error_message = 'queued', None
        session.commit()
        result = summary(row)
    background_tasks.add_task(process_purchase_order, str(doc_id), True)
    return result
