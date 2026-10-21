"""
Background Extraction pipeline for the Wovens BOM Extractor. 
This module contains the functions that process a PDF document, extract the BOM data, and save it to the database.
"""

from uuid import UUID
from sqlalchemy import delete
from .config import get_settings
from .database import SessionLocal
from .models import TechPack, BomExtraction, WovenMaterial
from .techpack_pdf import locate_pages, render_page
from .storage import get_bytes, put_bytes
from .openrouter_client import OpenRouterVLM
from .techpack_merge import combine_pages, parse_quantity
from .techpack_schema import DocumentExtraction
from .techpack_wovens import normalize_wovens_page
from .table_groups import extract_grouped
from copy import deepcopy


def write_material_rows(session, document_id, document: DocumentExtraction):
    """
    Purpose: Save the extracted materials as searchable rows in the woven_materials table,
    replacing any rows saved earlier for the same document.
    Input: session - an open database session; document_id - the Tech Pack's id;
    document - the DocumentExtraction whose materials are written.
    Output: nothing. The rows are added to the session; the caller commits.
    """
    session.execute(delete(WovenMaterial).where(WovenMaterial.document_id == document_id))
    for item in document.materials:
        session.add(WovenMaterial(
            document_id=document_id,
            material_code=item.material_code,
            description=item.description,
            composition=item.composition,
            placement=item.placement,
            quantity=parse_quantity(item.quantity),
            unit=item.unit,
            colorways=[v.model_dump(mode="json") for v in item.colorways],
            source_pages=item.source_pages,
        ))


def process_document(document_id: str):
    """
    Purpose: Background job that reads a Tech Pack PDF, finds the Wovens BOM pages, extracts
    their materials with the model, and saves the result for review. Progress is saved after
    each group of rows; on any error the document is marked failed with a short message.
    Input: document_id - the Tech Pack's id as a string.
    Output: nothing. The outcome is stored on the document: status 'needs_review' (success)
    or 'failed', plus the extraction JSON, material rows, page images and token usage.
    """
    doc_uuid = UUID(document_id)
    vlm = None
    raw_pages = []
    with SessionLocal() as session:
        document = session.get(TechPack, doc_uuid)
        if document is None:
            return
        document.status = "processing"
        document.error_message = None
        session.commit()
        extracted_pages = []

        def save_snapshot(combined):
            """
            Purpose: Save the partial result so far, so completed work survives a later failure.
            Input: combined - the DocumentExtraction built from the pages finished so far.
            Output: nothing. The extraction row is created or updated and committed.
            """
            combined.request_usage = list(vlm.request_usage) if vlm else []
            extraction = document.extraction
            if extraction is None:
                extraction = BomExtraction(document_id=doc_uuid, model_name=get_settings().openrouter_model,
                    extracted_json={}, raw_page_results=[], warnings=[])
                document.extraction = extraction
                session.add(extraction)
            extraction.extracted_json = combined.model_dump(mode='json')
            extraction.raw_page_results = deepcopy(raw_pages)
            extraction.warnings = combined.warnings
            session.commit()

        try:
            data = get_bytes(document.minio_key)
            vlm = OpenRouterVLM()
            pages, total = locate_pages(data, vlm)
            document.page_count = total
            document.selected_pages = [p + 1 for p in pages]
            session.commit()
            for index in pages:
                vlm.current_page = index + 1
                image, text = render_page(data, index)
                key = f"{doc_uuid}/page-images/page-{index + 1}.jpg"
                put_bytes(key, image, "image/jpeg")
                entry = {'page': index + 1, 'image_key': key, 'groups': [], 'result': None, 'status': 'processing'}
                raw_pages.append(entry)
                def progress(partial):
                    """
                    Purpose: Callback run after each group of rows is extracted; records it and saves a snapshot.
                    Input: partial - the PageResult for the groups finished on the current page.
                    Output: nothing.
                    """
                    partial = normalize_wovens_page(partial, text)
                    entry['result'] = partial.model_dump(mode='json')
                    save_snapshot(combine_pages(extracted_pages + [(index + 1, partial)]))
                result = extract_grouped(vlm, image, 'techpack', text, groups_log=entry['groups'], on_progress=progress)
                result = normalize_wovens_page(result, text)
                extracted_pages.append((index + 1, result))
                entry.update(status='completed', result=result.model_dump(mode='json'))
            combined = combine_pages(extracted_pages)
            combined.request_usage = vlm.request_usage
            if pages and not combined.materials:
                raise RuntimeError('No Wovens material rows were extracted from the detected pages; extraction failed')
            if not pages:
                combined.warnings.append("No Wovens BOM pages were located; check PDF layout or enable visual page classification")
            extraction = document.extraction
            if extraction is None:
                extraction = BomExtraction(document_id=doc_uuid, model_name=get_settings().openrouter_model,
                                           extracted_json={}, raw_page_results=[], warnings=[])
                session.add(extraction)
            extraction.model_name = get_settings().openrouter_model
            extraction.extracted_json = combined.model_dump(mode="json")
            extraction.raw_page_results = raw_pages
            extraction.warnings = combined.warnings
            write_material_rows(session, doc_uuid, combined)
            # Extraction is unapproved until checked against the source PDF.
            document.status = "needs_review"
            session.commit()
        except Exception as exc:
            for entry in raw_pages:
                if entry.get('status') == 'processing':
                    entry['status'] = 'failed'
            session.rollback()
            document = session.get(TechPack, doc_uuid)
            if document:
                document.status = "failed"
                document.error_message = str(exc)[:1000]
                if vlm is not None:
                    extraction = document.extraction
                    if extraction is None:
                        extraction = BomExtraction(document_id=doc_uuid, model_name=get_settings().openrouter_model,
                                                   extracted_json=DocumentExtraction().model_dump(mode='json'),
                                                   raw_page_results=[], warnings=[])
                        session.add(extraction)
                    extraction.extracted_json = {**extraction.extracted_json, 'request_usage': vlm.request_usage}
                    extraction.raw_page_results = deepcopy(raw_pages)
                session.commit()
            # Console logging only; never log full PDF contents or API credentials.
            print(f"Extraction failed for {doc_uuid}: {type(exc).__name__}: {str(exc)[:200]}")
