"""PO upload, inspection and review, independently of Tech Pack processing."""
import hashlib
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .audit import edit_details, record
from .auth import require_user
from .config import get_settings
from .database import SessionLocal
from .models import PurchaseOrderDocument, TechPack
from .extraction_progress import extraction_progress
from .po_schema import POCorrections, POExtraction, load_saved_extraction
from .po_merge import validate_totals, combine_po_pages
from .po_pipeline import ID_MISMATCH_PREFIX, process_purchase_order, association_warnings, id_check, id_mismatches
from .po_screening import skipped_notes
from .usage_archive import archive_usage
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
    page from 1 to page_count has a completed result or was skipped as not belonging to the Tech Pack; otherwise False.
    """
    if row.status not in ('needs_review', 'approved') or not row.extraction or not row.page_count:
        return False
    raw = row.extraction.raw_page_results
    return (row.extraction.extracted_json.get('processing_complete') is True
            and len(raw) == row.page_count
            and {entry.get('page') for entry in raw} == set(range(1, row.page_count + 1))
            and all(entry.get('status') in ('completed', 'skipped') for entry in raw))


def review_data(session, row):
    """
    Purpose: Prepare a PO's saved extraction for display, refreshing the Tech Pack link warnings
    because the linked Tech Pack may have finished extracting after this PO did.
    Input: session - a database session; row - a PurchaseOrderDocument that has an extraction.
    Output: the extraction as a dict, with up-to-date warnings.
    """
    saved = load_saved_extraction(row.extraction.extracted_json)
    for order in saved.orders:
        validate_totals(order)
    data = saved.model_dump(mode='json')
    data['warnings'] = [warning for warning in data['warnings']
        if not warning.startswith(ID_MISMATCH_PREFIX) and warning != 'Uploaded alongside a Tech Pack; business-reference matching requires review'
        and not (warning.startswith('Contract ') and warning.endswith('Tech Pack reference differs from the linked extraction'))]
    data['warnings'].extend(association_warnings(session, row,
        POExtraction.model_validate(data).orders))
    return data


@router.post('/upload', status_code=202)
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                 tech_pack_id: UUID | None = Form(None), user=Depends(require_user)):
    """
    Purpose: Upload a PO PDF, store it, and queue its extraction in the background. A PO must be linked to an
    approved Tech Pack, because its Model ID and Quality ID are checked against that Tech Pack's style number and Quality IDs.
    Input: file - the PDF (multipart field 'file', within the size limit); tech_pack_id - the id of the approved Tech Pack to link;
    user - the signed-in uploader, recorded for the usage report.
    Output: the PO's summary (HTTP 202). Raises 400 if it is not a PDF or no Tech Pack is chosen, 413 if too large,
    404 if the linked Tech Pack does not exist, 409 if it is not approved yet, 503 if storage fails.
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
        if tech_pack_id is None:
            raise HTTPException(400, 'Choose the Tech Pack this purchase order belongs to')
        linked = session.get(TechPack, tech_pack_id)
        if linked is None:
            raise HTTPException(404, 'Linked Tech Pack not found')
        if linked.status != 'approved':
            raise HTTPException(409, 'Approve the Tech Pack extraction before uploading its purchase order')
        try:
            put_bytes(key, data, 'application/pdf')
        except Exception as exc:
            raise HTTPException(503, 'Unable to save PDF to object storage') from exc
        row = PurchaseOrderDocument(id=doc_id, tech_pack_id=tech_pack_id, original_filename=filename,
            minio_key=key, sha256=hashlib.sha256(data).hexdigest(), status='queued', uploaded_by=user.id)
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
            item['id_check'] = id_check(session, row, load_saved_extraction(row.extraction.extracted_json).orders) if row.extraction else 'unchecked'
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
        mismatches = id_mismatches(session, row, load_saved_extraction(row.extraction.extracted_json).orders) if row.extraction else []
        saved_orders = load_saved_extraction(row.extraction.extracted_json).orders if row.extraction else []
        result.update(extraction=review_data(session, row) if row.extraction else None, id_mismatches=mismatches,
                      id_check=id_check(session, row, saved_orders),
                      skipped_pages=[{'page': entry['page'], **{key: (entry.get('screen') or {}).get(key) for key in ('model_id', 'quality_id', 'contract_number')}}
                                     for entry in (row.extraction.raw_page_results if row.extraction else []) if entry.get('status') == 'skipped'],
                      model=row.extraction.model_name if row.extraction else None,
                      request_usage=row.extraction.extracted_json.get('request_usage', []) if row.extraction else [],
                      approval_ready=source_complete(row) and not mismatches)
        result['progress'] = extraction_progress(row.status, range(1, (row.page_count or 0) + 1),
            row.extraction.raw_page_results if row.extraction else [])
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
        # What the extraction cost stays on the Usage page after the PO is gone.
        archive_usage(session, 'po', row)
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
def corrections(doc_id: UUID, payload: POCorrections, user=Depends(require_user)):
    """
    Purpose: Save manual corrections to a PO's orders and recalculate the quantity warnings. The change is
    recorded in the audit log with who made it.
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
            validate_totals(order)
        before, previous_status = [order.model_dump(mode='json') for order in saved.orders], row.status
        saved.orders = payload.orders
        saved.warnings = [f'Page {page.page_number}: {warning}' for page in saved.page_results for warning in page.result.warnings]
        saved.warnings.extend(association_warnings(session, row, saved.orders))
        saved.warnings.extend(skipped_notes(row.extraction.raw_page_results))
        row.extraction.extracted_json = saved.model_dump(mode='json')
        row.extraction.warnings = saved.warnings
        if row.status != 'failed':
            row.status = 'needs_review'
        record(session, user, 'po.edit', 'po', doc_id, row.original_filename,
               edit_details({'orders': before}, {'orders': [order.model_dump(mode='json') for order in saved.orders]},
                            previous_status, row.status))
        session.commit()
        return {'ok': True, 'status': row.status}


@router.post('/{doc_id}/approve')
def approve(doc_id: UUID, user=Depends(require_user)):
    """
    Purpose: Mark a PO as approved after the user has checked it against the PDF. The approval is recorded in
    the audit log with who gave it.
    Input: doc_id - the PO's id.
    Output: {'ok': True, 'status': 'approved'}. Raises 400 if any page is incomplete or there are no orders, 404 if not found.
    """
    with SessionLocal() as session:
        row = find(session, doc_id, True)
        if not source_complete(row) or not row.extraction.extracted_json.get('orders'):
            raise HTTPException(400, 'Cannot approve empty or incomplete PO processing')
        mismatches = id_mismatches(session, row, load_saved_extraction(row.extraction.extracted_json).orders)
        if mismatches:
            raise HTTPException(400, 'Cannot approve: ' + '; '.join(m[len(ID_MISMATCH_PREFIX):] for m in mismatches)
                                + '. Correct the purchase order or upload the right one.')
        previous_status, row.status = row.status, 'approved'
        record(session, user, 'po.approve', 'po', doc_id, row.original_filename,
               {'previous_status': previous_status, 'new_status': 'approved'})
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


@router.post('/{doc_id}/extract-skipped', status_code=202)
def extract_skipped(doc_id: UUID, background_tasks: BackgroundTasks):
    """
    Purpose: Extract the pages that were skipped because their Model ID or Quality ID did not fit the Tech Pack, for when
    the page header was misread or the PO should be read in full anyway. Pages already extracted are kept.
    Input: doc_id - the PO's id.
    Output: the PO's summary (HTTP 202). Raises 404 if not found, 409 if it is queued, processing or approved, has no skipped
    pages, or has manual corrections that a new extraction would overwrite.
    """
    with SessionLocal() as session:
        row = session.get(PurchaseOrderDocument, doc_id, with_for_update=True)
        if row is None:
            raise HTTPException(404, 'Purchase order not found')
        if row.status not in ('needs_review', 'failed') or row.extraction is None:
            raise HTTPException(409, 'Skipped pages can be extracted while the PO is waiting for review or has failed')
        raw = deepcopy(row.extraction.raw_page_results)
        skipped = [entry for entry in raw if entry.get('status') == 'skipped']
        if not skipped:
            raise HTTPException(409, 'No page of this PO was skipped')
        saved = load_saved_extraction(row.extraction.extracted_json)
        rebuilt = combine_po_pages([(page.page_number, page.result) for page in saved.page_results])
        if saved.orders != rebuilt.orders:
            raise HTTPException(409, 'This PO has manual corrections. Export them before extracting more pages; this would not overwrite edited results.')
        for entry in skipped:
            entry.update(status='pending', result=None, groups=[])
        row.extraction.raw_page_results = raw
        row.status, row.error_message = 'queued', None
        session.commit()
        result = summary(row)
    background_tasks.add_task(process_purchase_order, str(doc_id), True)
    return result
