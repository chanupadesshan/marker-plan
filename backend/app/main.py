"""
this is the main entrypoint for the FastAPI application.
when pdf is uploaded, it check the fize size and file type, saves the original in MinIO, create a database record, and then starts the background processing of the document.
the background processing extracts the BOM data from the PDF, saves it in the database, and updates the status of the document record.
the API also provides endpoints to list documents, get document details, download the original PDF, download the extracted BOM data as JSON, and save corrections to the extracted data
"""


import hashlib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import BackgroundTasks, Depends, FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from .audit import edit_details, record, without
from .auth import ensure_first_admin, needs, prepare_upload_owner_columns, prepare_users_table, require_user
from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import TechPack, BomExtraction
from .extraction_progress import extraction_progress
from .observability import flush as flush_traces
from .ply_lookup import ply_info_for
from .storage import delete_prefix, ensure_bucket, get_bytes, put_bytes
from .usage_archive import archive_usage
from .techpack_pipeline import process_document, write_material_rows
from .techpack_schema import DocumentExtraction
from .techpack_merge import canonicalize_corrections


def prepare_material_category_column():
    """
    Purpose: Add the category column (wovens or knits) to a woven_materials table created before Knits were read
    (create_all never alters existing tables). Existing rows are Wovens.
    Input: none.
    Output: nothing; safe to run on every start.
    """
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE woven_materials ADD COLUMN IF NOT EXISTS category VARCHAR(10) NOT NULL DEFAULT 'wovens'"))


def recover_interrupted_documents():
    """
    Purpose: Extraction runs as an in-process background task, so a server restart silently kills it
    and leaves the row 'queued' or 'processing' forever. Mark those rows failed at start-up so the
    page stops showing a job that is not running.
    Input: none.
    Output: nothing. Interrupted Tech Packs and Purchase Orders are set to 'failed' with a message.
    """
    from .models import PurchaseOrderDocument
    message = 'Extraction was interrupted by a server restart. Upload the file again.'
    with SessionLocal() as session:
        for model in (TechPack, PurchaseOrderDocument):
            for row in session.scalars(select(model).where(model.status.in_(['queued', 'processing']))):
                row.status, row.error_message = 'failed', message
        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Purpose: Run start-up work before the API accepts requests: create any missing database tables
    and wait (up to about 40 seconds) for the MinIO bucket to be ready.
    Input: app - the FastAPI application.
    Output: yields once start-up is done; raises if storage never becomes available.
    """
    import time
    Base.metadata.create_all(engine)
    from .marker_plan_routes import recover_interrupted_plans
    recover_interrupted_plans()
    # create_all never alters existing tables, so add the newer columns before any query selects them.
    prepare_users_table(engine)
    prepare_upload_owner_columns(engine)
    prepare_material_category_column()
    recover_interrupted_documents()
    ensure_first_admin()
    # MinIO can still be starting even when the Docker service has launched.
    for attempt in range(20):
        try:
            ensure_bucket()
            break
        except Exception:
            if attempt == 19:
                raise
            time.sleep(2)
    yield
    flush_traces()


app = FastAPI(title="Wovens BOM Extraction API", version="0.1.0", lifespan=lifespan)
from .auth import router as auth_router
app.include_router(auth_router)
from .admin_routes import router as admin_router
app.include_router(admin_router)
# Everything below needs a signed-in user with the matching permission: 'view' for reading (GET) and 'edit' for
# anything that changes data. Only /api/health and /api/auth/login are open; /api/admin/* needs an admin.
from .po_routes import router as po_router
app.include_router(po_router, dependencies=[Depends(needs('purchase_orders'))])
from .ply_routes import router as ply_router
app.include_router(ply_router, dependencies=[Depends(needs('plies'))])
from .marker_plan_routes import router as marker_plan_router
app.include_router(marker_plan_router, dependencies=[Depends(needs('marker_plan'))])
from .usage_routes import router as usage_router
app.include_router(usage_router, dependencies=[Depends(needs('usage'))])
from .audit import router as audit_router
app.include_router(audit_router)
tech_pack_access = [Depends(needs('techpacks'))]


def record_summary(row: TechPack):
    """
    Purpose: Build the short description of a Tech Pack that the list and detail endpoints return.
    Input: row - a TechPack.
    Output: a dict with id, filename, status, error, page_count, selected_pages and created_at.
    """
    return {"id": str(row.id), "filename": row.original_filename,
            "status": row.status, "error": row.error_message,
            "page_count": row.page_count, "selected_pages": row.selected_pages,
            "created_at": row.created_at.isoformat() if row.created_at else None}


@app.get("/api/health")
def health():
    """
    Purpose: Let a monitor or a person check that the API is running.
    Input: none.
    Output: {'status': 'ok'}.
    """
    return {"status": "ok"}


@app.post("/api/documents/upload", status_code=202, dependencies=tech_pack_access)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), user=Depends(require_user)):
    """
    Purpose: Upload a Tech Pack PDF, store it, and queue its Wovens extraction in the background.
    Input: file - the PDF (multipart field 'file', within the size limit); user - the signed-in uploader, recorded for the usage report.
    Output: the Tech Pack's summary (HTTP 202). Raises 400 if it is not a PDF, 413 if too large, 503 if storage fails.
    """
    size = get_settings().max_upload_mb * 1024 * 1024
    payload = await file.read(size + 1)
    if len(payload) > size:
        raise HTTPException(413, f"PDF exceeds maximum size ({get_settings().max_upload_mb} MB)")
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(400, "Upload must be a PDF file")
    filename = Path((file.filename or "tech-pack.pdf").replace("\\", "/")).name[:255]
    doc_id = uuid.uuid4()
    key = f"{doc_id}/source/{filename}"
    try:
        put_bytes(key, payload, "application/pdf")
    except Exception as exc:
        raise HTTPException(503, "Unable to save PDF to object storage") from exc
    with SessionLocal() as session:
        row = TechPack(id=doc_id, original_filename=filename, minio_key=key,
                       sha256=hashlib.sha256(payload).hexdigest(), status="queued", uploaded_by=user.id)
        session.add(row)
        session.commit()
        result = record_summary(row)
    background_tasks.add_task(process_document, str(doc_id))
    return result


@app.get("/api/documents", dependencies=tech_pack_access)
def list_documents():
    """
    Purpose: List the most recent Tech Packs, with the identifiers the sidebar searches on.
    Input: none.
    Output: up to 100 summaries, newest first, each with style_number and tech_pack_number
    (the full extraction is not included).
    """
    with SessionLocal() as session:
        rows = session.scalars(select(TechPack).options(selectinload(TechPack.extraction))
                               .order_by(TechPack.created_at.desc()).limit(100)).all()
        items = []
        for row in rows:
            item = record_summary(row)
            # Searchable identifiers only; the full extraction is loaded on selection.
            extracted = row.extraction.extracted_json if row.extraction else {}
            item["style_number"] = extracted.get("style_number")
            item["design_numbers"] = extracted.get("design_numbers") or ([extracted["design_number"]] if extracted.get("design_number") else [])
            item["tech_pack_number"] = extracted.get("tech_pack_number")
            items.append(item)
        return items


@app.get("/api/documents/{doc_id}", dependencies=tech_pack_access)
def get_document(doc_id: uuid.UUID):
    """
    Purpose: Return one Tech Pack with its full extraction for review.
    Input: doc_id - the Tech Pack's id.
    Output: the summary plus extraction, model name, request_usage and ply_info (each material's related
    plies rows and maximum ply, looked up fresh from the plies table; kept outside the extraction so it
    is never saved back with corrections). Raises 404 if not found.
    """
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        item = record_summary(row)
        item["extraction"] = row.extraction.extracted_json if row.extraction else None
        item["model"] = row.extraction.model_name if row.extraction else None
        item['request_usage'] = row.extraction.extracted_json.get('request_usage', []) if row.extraction else []
        item['progress'] = extraction_progress(row.status, row.selected_pages,
            row.extraction.raw_page_results if row.extraction else [])
        item['ply_info'] = ply_info_for(session, row.extraction.extracted_json) if row.extraction else {}
        return item


@app.delete("/api/documents/{doc_id}", dependencies=tech_pack_access)
def delete_document(doc_id: uuid.UUID):
    """
    Purpose: Permanently remove a Tech Pack: its row, extraction and Wovens rows (cascade), then its stored files.
    Input: doc_id - the Tech Pack's id.
    Output: {'ok': True}. Raises 404 if not found, and 409 while it is queued or processing.
    """
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        if row.status in ("queued", "processing"):
            raise HTTPException(409, "Wait for extraction to finish before deleting")
        # What the extraction cost stays on the Usage page after the Tech Pack is gone.
        archive_usage(session, "techpack", row)
        session.delete(row)
        session.commit()
    # Linked purchase orders are kept; their tech_pack_id is set to NULL by the database.
    delete_prefix(f"{doc_id}/")
    return {"ok": True}


@app.get("/api/documents/{doc_id}/pdf", dependencies=tech_pack_access)
def download_original(doc_id: uuid.UUID):
    """
    Purpose: Serve the Tech Pack's original PDF for viewing.
    Input: doc_id - the Tech Pack's id.
    Output: the PDF file (application/pdf). Raises 404 if not found, 503 if storage cannot return it.
    """
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        try:
            content = get_bytes(row.minio_key)
        except Exception as exc:
            raise HTTPException(503, "Unable to retrieve PDF") from exc
        return Response(content, media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=tech-pack.pdf"})


@app.get("/api/documents/{doc_id}/json", dependencies=tech_pack_access)
def download_json(doc_id: uuid.UUID):
    """
    Purpose: Download the Tech Pack's extracted Wovens data as a JSON file.
    Input: doc_id - the Tech Pack's id.
    Output: the extraction JSON as an attachment. Raises 404 if the document or its extraction is missing.
    """
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None or row.extraction is None:
            raise HTTPException(404, "Extraction not available")
        return JSONResponse(row.extraction.extracted_json,
                            headers={"Content-Disposition": f'attachment; filename="wovens-{doc_id}.json"'})


@app.put("/api/documents/{doc_id}/extraction", dependencies=tech_pack_access)
def save_corrections(doc_id: uuid.UUID, payload: DocumentExtraction, user=Depends(require_user)):
    """
    Purpose: Save manually corrected Wovens data, keeping the combined materials and page tables
    consistent and rewriting the material rows. The change is recorded in the audit log with who made it.
    Input: doc_id - the Tech Pack's id; payload - the corrected DocumentExtraction (category must be Wovens).
    Output: {'ok': True, 'status': <new status>}. Raises 400 for a non-Wovens category or conflicting data,
    404 if not found, 409 while processing.
    """
    if payload.category.casefold() != "wovens":
        raise HTTPException(400, "Only Wovens BOM data is supported")
    try:
        payload = canonicalize_corrections(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None or row.extraction is None:
            raise HTTPException(404, "Document or extraction not found")
        if row.status in ('queued', 'processing'):
            raise HTTPException(409, 'Wait for processing before editing')
        payload.request_usage = row.extraction.extracted_json.get('request_usage', [])
        before, previous_status = row.extraction.extracted_json, row.status
        saved = payload.model_dump(mode="json")
        row.extraction.extracted_json = saved
        row.extraction.warnings = payload.warnings
        write_material_rows(session, doc_id, payload)
        if row.status != 'failed':
            row.status = "needs_review"
        skip = ('request_usage', 'warnings', 'page_tables')
        record(session, user, 'techpack.edit', 'techpack', doc_id, row.original_filename,
               edit_details(without(before, *skip), without(saved, *skip), previous_status, row.status))
        session.commit()
        return {"ok": True, "status": row.status}


@app.post("/api/documents/{doc_id}/approve", dependencies=tech_pack_access)
def approve_document(doc_id: uuid.UUID, user=Depends(require_user)):
    """
    Purpose: Mark a Tech Pack's extraction as approved after the user has checked it against the PDF.
    The approval is recorded in the audit log with who gave it.
    Input: doc_id - the Tech Pack's id.
    Output: {'ok': True, 'status': 'approved'}. Raises 400 if processing is incomplete or there are no
    materials, 404 if not found.
    """
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None or row.extraction is None:
            raise HTTPException(404, "Document or extraction not found")
        if row.status not in ('needs_review', 'approved'):
            raise HTTPException(400, 'Cannot approve incomplete Tech Pack processing')
        if not row.extraction.extracted_json.get("materials"):
            raise HTTPException(400, "Cannot approve an empty extraction")
        previous_status, row.status = row.status, "approved"
        record(session, user, 'techpack.approve', 'techpack', doc_id, row.original_filename,
               {'previous_status': previous_status, 'new_status': 'approved'})
        session.commit()
        return {"ok": True, "status": "approved"}
