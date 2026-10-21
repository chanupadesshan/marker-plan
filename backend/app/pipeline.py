"""
Background Extraction pipeline for the Wovens BOM Extractor. 
This module contains the functions that process a PDF document, extract the BOM data, and save it to the database.
"""

from uuid import UUID
from sqlalchemy import delete
from .config import get_settings
from .database import SessionLocal
from .models import TechPack, BomExtraction, WovenMaterial
from .pdf_processing import locate_pages, render_page
from .storage import get_bytes, put_bytes
from .vlm import OpenRouterVLM
from .merge import combine_pages, parse_quantity
from .schema import DocumentExtraction
from .wovens import normalize_wovens_page


def write_material_rows(session, document_id, document: DocumentExtraction):
    """
    writes individual material records to postgres for a given document_id and DocumentExtraction object.
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
    processes a PDF document by extracting the BOM data and saving it to the database.
    """
    doc_uuid = UUID(document_id)
    vlm = None
    with SessionLocal() as session:
        document = session.get(TechPack, doc_uuid)
        if document is None:
            return
        document.status = "processing"
        document.error_message = None
        session.commit()
        try:
            data = get_bytes(document.minio_key)
            vlm = OpenRouterVLM()
            pages, total = locate_pages(data, vlm)
            document.page_count = total
            document.selected_pages = [p + 1 for p in pages]
            session.commit()
            extracted_pages = []
            raw_pages = []
            for index in pages:
                vlm.current_page = index + 1
                image, text = render_page(data, index)
                key = f"{doc_uuid}/page-images/page-{index + 1}.jpg"
                put_bytes(key, image, "image/jpeg")
                result = normalize_wovens_page(vlm.extract(image, text), text)
                extracted_pages.append((index + 1, result))
                raw_pages.append({"page": index + 1, "image_key": key, "result": result.model_dump(mode="json")})
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
                session.commit()
            # Console logging only; never log full PDF contents or API credentials.
            print(f"Extraction failed for {doc_uuid}: {type(exc).__name__}: {str(exc)[:200]}")
