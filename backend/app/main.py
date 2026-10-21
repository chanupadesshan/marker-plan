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
from fastapi import BackgroundTasks, FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import TechPack, BomExtraction
from .storage import ensure_bucket, get_bytes, put_bytes
from .pipeline import process_document, write_material_rows
from .schema import DocumentExtraction
from .merge import canonicalize_corrections


@asynccontextmanager
async def lifespan(app: FastAPI):
    import time
    Base.metadata.create_all(engine)
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


app = FastAPI(title="Wovens BOM Extraction API", version="0.1.0", lifespan=lifespan)


def record_summary(row: TechPack):
    return {"id": str(row.id), "filename": row.original_filename,
            "status": row.status, "error": row.error_message,
            "page_count": row.page_count, "selected_pages": row.selected_pages,
            "created_at": row.created_at.isoformat() if row.created_at else None}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/documents/upload", status_code=202)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
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
                       sha256=hashlib.sha256(payload).hexdigest(), status="queued")
        session.add(row)
        session.commit()
        result = record_summary(row)
    background_tasks.add_task(process_document, str(doc_id))
    return result


@app.get("/api/documents")
def list_documents():
    with SessionLocal() as session:
        rows = session.scalars(select(TechPack).order_by(TechPack.created_at.desc()).limit(100)).all()
        return [record_summary(row) for row in rows]


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: uuid.UUID):
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        item = record_summary(row)
        item["extraction"] = row.extraction.extracted_json if row.extraction else None
        item["model"] = row.extraction.model_name if row.extraction else None
        item['request_usage'] = row.extraction.extracted_json.get('request_usage', []) if row.extraction else []
        return item


@app.get("/api/documents/{doc_id}/pdf")
def download_original(doc_id: uuid.UUID):
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


@app.get("/api/documents/{doc_id}/json")
def download_json(doc_id: uuid.UUID):
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None or row.extraction is None:
            raise HTTPException(404, "Extraction not available")
        return JSONResponse(row.extraction.extracted_json,
                            headers={"Content-Disposition": f'attachment; filename="wovens-{doc_id}.json"'})


@app.put("/api/documents/{doc_id}/extraction")
def save_corrections(doc_id: uuid.UUID, payload: DocumentExtraction):
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
        payload.request_usage = row.extraction.extracted_json.get('request_usage', [])
        row.extraction.extracted_json = payload.model_dump(mode="json")
        row.extraction.warnings = payload.warnings
        write_material_rows(session, doc_id, payload)
        row.status = "needs_review"
        session.commit()
        return {"ok": True, "status": row.status}


@app.post("/api/documents/{doc_id}/approve")
def approve_document(doc_id: uuid.UUID):
    with SessionLocal() as session:
        row = session.get(TechPack, doc_id)
        if row is None or row.extraction is None:
            raise HTTPException(404, "Document or extraction not found")
        if not row.extraction.extracted_json.get("materials"):
            raise HTTPException(400, "Cannot approve an empty extraction")
        row.status = "approved"
        session.commit()
        return {"ok": True, "status": "approved"}
