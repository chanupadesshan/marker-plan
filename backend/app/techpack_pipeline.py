"""
Background Extraction pipeline for the Wovens BOM Extractor. 
This module contains the functions that process a PDF document, extract the BOM data, and save it to the database.
"""

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID
from sqlalchemy import delete
from .config import get_settings
from .database import SessionLocal
from .models import TechPack, BomExtraction, WovenMaterial
from .techpack_pdf import document_titles, locate_pages, render_page
from .storage import get_bytes, put_bytes
from .openrouter_client import OpenRouterVLM, fork
from .techpack_merge import add_titles, combine_pages, parse_quantity
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
            category=item.category,
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
        # Pages are read in worker threads, each with its own copy of the model client. `current` holds the latest result
        # (finished or partial) of every page, `children` those clients. Only this thread touches the database session.
        current, children = {}, {}

        def usage_so_far():
            """
            Purpose: Every model request made so far: the page checks, then each page's requests in page order.
            Input: none.
            Output: a new list of request-usage records.
            """
            return [*(vlm.request_usage if vlm else []), *(use for page in sorted(children) for use in list(children[page].request_usage))]

        def copy_pages():
            """
            Purpose: Copy the per-page progress records while worker threads may still be adding to them.
            Input: none.
            Output: a deep copy of raw_pages (retried a few times if a page's thread changed a record mid-copy).
            """
            for _ in range(5):
                try:
                    return deepcopy(raw_pages)
                except RuntimeError:
                    time.sleep(0.05)
            return deepcopy(raw_pages)

        def save_snapshot(combined):
            """
            Purpose: Save the partial result so far, so completed work survives a later failure.
            Input: combined - the DocumentExtraction built from the pages finished so far.
            Output: nothing. The extraction row is created or updated and committed.
            """
            combined.request_usage = usage_so_far()
            extraction = document.extraction
            if extraction is None:
                extraction = BomExtraction(document_id=doc_uuid, model_name=get_settings().openrouter_model,
                    extracted_json={}, raw_page_results=[], warnings=[])
                document.extraction = extraction
                session.add(extraction)
            extraction.extracted_json = combined.model_dump(mode='json')
            extraction.raw_page_results = copy_pages()
            extraction.warnings = combined.warnings
            session.commit()

        try:
            data = get_bytes(document.minio_key)
            # Every BOM page title in the PDF names a style and design, including pages that are not extracted.
            titles = document_titles(data)
            combine = lambda items: add_titles(combine_pages(items), titles)
            vlm = OpenRouterVLM()
            vlm.trace_document_id, vlm.trace_name = document_id, 'tech-pack-extraction'
            pages, total = locate_pages(data, vlm)
            document.page_count = total
            document.selected_pages = [p + 1 for p in pages]
            session.commit()
            events, stop, entries = queue.Queue(), threading.Event(), {}
            pool = ThreadPoolExecutor(max_workers=max(1, min(len(pages), get_settings().extraction_concurrency)))

            def read_page(page_number, image, text, entry, child):
                """
                Purpose: Read one page with the model, in a worker thread.
                Input: page_number; image and text - the rendered page; entry - its progress record; child - its own model client.
                Output: the page's normalized PageResult. After each row group it hands the partial result to the main
                thread and waits until that has been saved, so a group is stored before the next one starts.
                """
                def progress(partial):
                    saved = threading.Event()
                    events.put(('partial', page_number, normalize_wovens_page(partial, text), saved))
                    while not saved.wait(0.25):
                        if stop.is_set():
                            raise RuntimeError('Extraction was stopped')
                result = extract_grouped(child, image, 'techpack', text, groups_log=entry['groups'], on_progress=progress)
                return normalize_wovens_page(result, text)

            try:
                for index in pages:
                    page_number = index + 1
                    image, text = render_page(data, index)
                    key = f"{doc_uuid}/page-images/page-{page_number}.jpg"
                    put_bytes(key, image, "image/jpeg")
                    entry = {'page': page_number, 'image_key': key, 'groups': [], 'result': None, 'status': 'processing'}
                    raw_pages.append(entry)
                    entries[page_number] = entry
                    child = children[page_number] = fork(vlm)
                    child.current_page = page_number
                    pool.submit(read_page, page_number, image, text, entry, child).add_done_callback(
                        lambda future, number=page_number: events.put(('done', number, future, None)))
                finished = 0
                while finished < len(pages):
                    kind, page_number, payload, saved = events.get()
                    if kind == 'partial':
                        current[page_number] = payload
                        entries[page_number]['result'] = payload.model_dump(mode='json')
                        save_snapshot(combine(sorted(current.items())))
                        saved.set()
                    else:
                        result = payload.result()  # raises this page's error, which fails the document as before
                        current[page_number] = result
                        entries[page_number].update(status='completed', result=result.model_dump(mode='json'))
                        finished += 1
                        save_snapshot(combine(sorted(current.items())))
            except BaseException:
                # Do not wait for pages still being read: tell them to stop and report the failure now.
                stop.set()
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            pool.shutdown()
            combined = combine(sorted(current.items()))
            combined.request_usage = usage_so_far()
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
                    extraction.extracted_json = {**extraction.extracted_json, 'request_usage': usage_so_far()}
                    extraction.raw_page_results = copy_pages()
                session.commit()
            # Console logging only; never log full PDF contents or API credentials.
            print(f"Extraction failed for {doc_uuid}: {type(exc).__name__}: {str(exc)[:200]}")
