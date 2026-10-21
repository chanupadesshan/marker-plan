"""PO upload, inspection and review, independently of Tech Pack processing."""
import hashlib
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from .config import get_settings
from .database import SessionLocal
from .models import PurchaseOrderDocument, TechPack
from .po_schema import POCorrections, POExtraction
from .po_merge import validate_totals
from .po_pipeline import process_purchase_order, association_warnings
from .storage import get_bytes, put_bytes

router = APIRouter(prefix='/api/purchase-orders', tags=['Purchase orders'])


def summary(row):
    return {'id': str(row.id), 'filename': row.original_filename, 'status': row.status,
            'error': row.error_message, 'page_count': row.page_count,
            'tech_pack_id': str(row.tech_pack_id) if row.tech_pack_id else None,
            'created_at': row.created_at.isoformat() if row.created_at else None}


def find(session, doc_id, require_extraction=False):
    row = session.get(PurchaseOrderDocument, doc_id)
    if row is None or (require_extraction and row.extraction is None):
        raise HTTPException(404, 'Purchase order or extraction not found')
    return row


def source_complete(row):
    if row.status not in ('needs_review', 'approved') or not row.extraction or not row.page_count:
        return False
    raw = row.extraction.raw_page_results
    return (row.extraction.extracted_json.get('processing_complete') is True
            and len(raw) == row.page_count
            and {entry.get('page') for entry in raw} == set(range(1, row.page_count + 1))
            and all(entry.get('status') == 'completed' for entry in raw))


@router.post('/upload', status_code=202)
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...),
                 tech_pack_id: UUID | None = Form(None)):
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


@router.get('/{doc_id}')
def details(doc_id: UUID):
    with SessionLocal() as session:
        row = find(session, doc_id)
        result = summary(row)
        result.update(extraction=row.extraction.extracted_json if row.extraction else None,
                      model=row.extraction.model_name if row.extraction else None,
                      request_usage=row.extraction.extracted_json.get('request_usage', []) if row.extraction else [],
                      approval_ready=source_complete(row))
        return result


@router.get('/{doc_id}/pdf')
def original(doc_id: UUID):
    with SessionLocal() as session:
        row = find(session, doc_id)
        try:
            data = get_bytes(row.minio_key)
        except Exception as exc:
            raise HTTPException(503, 'Unable to retrieve PDF') from exc
        return Response(data, media_type='application/pdf', headers={'Content-Disposition': 'inline; filename=purchase-order.pdf'})


@router.get('/{doc_id}/json')
def export(doc_id: UUID):
    with SessionLocal() as session:
        row = find(session, doc_id, True)
        return JSONResponse(row.extraction.extracted_json,
            headers={'Content-Disposition': f'attachment; filename="purchase-orders-{doc_id}.json"'})


@router.put('/{doc_id}/extraction')
def corrections(doc_id: UUID, payload: POCorrections):
    with SessionLocal() as session:
        row = find(session, doc_id, True)
        if row.status in ('queued', 'processing'):
            raise HTTPException(409, 'Wait for processing before editing')
        saved = POExtraction.model_validate(row.extraction.extracted_json)
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
    with SessionLocal() as session:
        row = find(session, doc_id, True)
        if not source_complete(row) or not row.extraction.extracted_json.get('orders'):
            raise HTTPException(400, 'Cannot approve empty or incomplete PO processing')
        row.status = 'approved'
        session.commit()
        return {'ok': True, 'status': row.status}
