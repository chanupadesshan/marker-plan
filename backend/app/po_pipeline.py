"""Render every PO page first, screen them against the Tech Pack, then extract the rest side by side with durable partial results."""
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from uuid import UUID
from copy import deepcopy
import pymupdf
from .config import get_settings
from .database import SessionLocal
from .models import PurchaseOrderDocument, PurchaseOrderExtraction, TechPack
from .storage import get_bytes, put_bytes
from .techpack_pdf import trimmed_page_image
from .openrouter_client import OpenRouterVLM, fork
from .po_merge import combine_po_pages
from .table_groups import extract_grouped
from .po_schema import POPageResult, load_saved_extraction
from .po_screening import same_id, screen_pages, skipped_notes


ID_MISMATCH_PREFIX = 'ID mismatch: '


_same_id = same_id


def expected_ids(session, document):
    """
    Purpose: The identifiers a PO is checked against: its linked Tech Pack's style number and design IDs.
    Input: session - a database session; document - the PurchaseOrderDocument.
    Output: (style_number, design_ids): (None, []) when there is no linked Tech Pack or it has none.
    """
    linked = session.get(TechPack, document.tech_pack_id) if document.tech_pack_id else None
    expected = linked.extraction.extracted_json if linked and linked.extraction else {}
    designs = expected.get('design_numbers') or ([expected['design_number']] if expected.get('design_number') else [])
    return expected.get('style_number'), designs


def id_mismatches(session, document, orders):
    """
    Purpose: Find contracts whose Model ID differs from the linked Tech Pack's style number, or whose
    Quality ID is not one of its design IDs (a Tech Pack can hold several designs). A value missing on either side is not compared.
    Input: session - a database session; document - the PurchaseOrderDocument; orders - its extracted orders.
    Output: a list of 'ID mismatch: ...' messages (empty when everything matches or there is no linked Tech Pack).
    """
    style, designs = expected_ids(session, document)
    problems = []
    for order in orders:
        label = f'Contract {order.contract_number or "unknown"}: '
        if order.model_id and style and not _same_id(order.model_id, style):
            problems.append(f'{ID_MISMATCH_PREFIX}{label}Model ID {order.model_id} does not match the Tech Pack style number {style}')
        if order.quality_id and designs and not any(_same_id(order.quality_id, design) for design in designs):
            problems.append(f'{ID_MISMATCH_PREFIX}{label}Quality ID {order.quality_id} does not match the Tech Pack Quality ID'
                            f'{"s" if len(designs) > 1 else ""} {", ".join(designs)}')
    return problems


def id_check(session, document, orders):
    """
    Purpose: Sort a PO by how its IDs compare with its Tech Pack, so the review screen can list it under the right heading.
    Input: session - a database session; document - the PurchaseOrderDocument; orders - its extracted orders.
    Output: 'mismatch' (a contract's Model ID or Quality ID is wrong), 'no_design' (the style matches but no contract has a
    Quality ID), 'match' (the style matches and a Quality ID is one of the design IDs), or 'unchecked' (no contracts yet, no
    linked Tech Pack, or the Tech Pack or PO has no style number to compare).
    """
    if not orders or not document.tech_pack_id:
        return 'unchecked'
    if id_mismatches(session, document, orders):
        return 'mismatch'
    linked = session.get(TechPack, document.tech_pack_id)
    style = linked.extraction.extracted_json.get('style_number') if linked and linked.extraction else None
    if not style or not any(order.model_id for order in orders):
        return 'unchecked'
    return 'match' if any(order.quality_id for order in orders) else 'no_design'


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
    return warnings + id_mismatches(session, document, orders)


def process_purchase_order(document_id: str, resume: bool = False):
    """
    Purpose: Background job that renders every page of a PO PDF, screens the pages against the linked Tech Pack (pages whose
    Model ID or Quality ID do not fit are skipped, not extracted), then extracts the remaining pages one
    at a time with the model. Results are saved after each page so a failure keeps the
    completed ones. On success the document needs review; on error it is marked failed.
    Input: document_id - the PO document's id as a string; resume - True to reuse completed
    pages, skipped pages and saved images from an earlier run (a retry, or extracting the skipped pages).
    Output: nothing. The outcome is stored on the document: status 'needs_review' or 'failed',
    the extraction JSON, per-page results, page images and token usage.
    """
    doc_id = UUID(document_id)
    vlm = None
    pages, raw = [], []
    usage_history = []
    # Each page read by a worker has its own model client (children) so usage and page numbers do not mix;
    # failed_pages notes which page's read failed.
    children, failed_pages = {}, []
    with SessionLocal() as session:
        document = session.get(PurchaseOrderDocument, doc_id)
        if document is None:
            return
        document.status, document.error_message = 'processing', None
        session.commit()
        if resume and document.extraction:
            raw = deepcopy(document.extraction.raw_page_results)
            usage_history = list(document.extraction.extracted_json.get('request_usage', []))

        def snapshot():
            """
            Purpose: Copy the per-page records while worker threads may still be adding to them.
            Input: none.
            Output: a deep copy of raw (retried a few times if a page's thread changed a record mid-copy).
            """
            for _ in range(5):
                try:
                    return deepcopy(raw)
                except RuntimeError:
                    time.sleep(0.05)
            return deepcopy(raw)

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
            # The usage so far: history and page screening, then each page's own requests in page order.
            combined.request_usage = ([*vlm.request_usage, *(use for page in sorted(children) for use in list(children[page].request_usage))]
                                      if vlm else usage_history)
            combined.warnings.extend(association_warnings(session, document, combined.orders))
            combined.warnings.extend(skipped_notes(raw))
            extraction = document.extraction
            if extraction is None:
                extraction = PurchaseOrderExtraction(document_id=doc_id,
                    model_name=get_settings().openrouter_model, extracted_json={}, raw_page_results=[], warnings=[])
                document.extraction = extraction
                session.add(extraction)
            extraction.extracted_json = combined.model_dump(mode='json')
            # JSONB change detection needs an independent snapshot of nested entries.
            extraction.raw_page_results = snapshot()
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
                        if (old.get('status') == 'completed' and old.get('result')) or old.get('status') == 'skipped':
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
            vlm.trace_document_id, vlm.trace_name = document_id, 'purchase-order-extraction'
            vlm.request_usage = list(usage_history)
            # Pages not yet screened are checked against the Tech Pack's style number and design IDs; those that do not fit are skipped.
            style, designs = expected_ids(session, document)
            if style and any(entry['status'] == 'pending' and 'screen' not in entry for entry in raw):
                with pymupdf.open(stream=data, filetype='pdf') as pdf:
                    outcome = screen_pages(pdf, style, designs, vlm)
                for record in outcome:
                    entry = raw[record['page'] - 1]
                    if entry['status'] != 'pending' or 'screen' in entry:
                        continue
                    entry['screen'] = {key: record[key] for key in ('decision', 'model_id', 'quality_id', 'contract_number', 'source')}
                    if record['decision'] == 'skip':
                        entry.update(status='skipped', result=None, groups=[])
                persist()
            # The pages still to read are read side by side, each by a worker with its own model client. Only this thread
            # touches the database session: workers hand over their results and wait until each has been saved.
            todo = [entry for entry in raw if entry['status'] not in ('completed', 'skipped')]
            if todo:
                events, stop = queue.Queue(), threading.Event()
                pool = ThreadPoolExecutor(max_workers=max(1, min(len(todo), get_settings().extraction_concurrency)))
                entries, futures = {entry['page']: entry for entry in todo}, {}

                def read_page(entry, image, child):
                    """
                    Purpose: Read one page with the model, in a worker thread.
                    Input: entry - the page's progress record; image - its image; child - its own model client.
                    Output: the page's POPageResult. After each group of rows it hands the partial result to the main thread and
                    waits until that has been saved, so a group is stored before the next one starts.
                    """
                    def progress(partial):
                        saved = threading.Event()
                        events.put(('partial', entry['page'], partial, saved))
                        while not saved.wait(0.25):
                            if stop.is_set():
                                raise RuntimeError('Extraction was stopped')
                    return extract_grouped(child, image, 'po', groups_log=entry['groups'], on_progress=progress)

                def complete(number, result):
                    """
                    Purpose: Store a page that has been read.
                    Input: number - the page number; result - its POPageResult.
                    Output: nothing. The page is marked completed and everything is saved.
                    """
                    # Assign provenance from the PDF, never the model's claimed page numbers.
                    for order in result.orders:
                        order.source_pages = [number]
                        for row in order.size_rows:
                            row.source_page = number
                    entries[number].update(status='completed', result=result.model_dump(mode='json'))
                    pages.append((number, result))
                    persist()

                try:
                    for entry in todo:
                        child = children[entry['page']] = fork(vlm)
                        child.current_page = entry['page']
                        future = futures[entry['page']] = pool.submit(read_page, entry, get_bytes(entry['image_key']), child)
                        future.add_done_callback(lambda done, number=entry['page']: events.put(('done', number, done, None)))
                    finished = 0
                    while finished < len(todo):
                        kind, number, payload, saved = events.get()
                        entry = entries[number]
                        if kind == 'partial':
                            entry['result'] = payload.model_dump(mode='json')
                            persist()
                            saved.set()
                            continue
                        try:
                            result = payload.result()
                        except BaseException:
                            failed_pages.append(number)
                            raise
                        complete(number, result)
                        finished += 1
                except BaseException:
                    # Do not wait for pages still being read: tell them to stop and report the failure now,
                    # but first keep the pages that had already been read.
                    # A page that is about to finish gets a moment to do so (its group results are still saved as they
                    # arrive); slow ones are left behind.
                    deadline = time.monotonic() + 1.0
                    try:
                        while time.monotonic() < deadline and not all(future.done() for future in futures.values()):
                            try:
                                kind, number, payload, saved = events.get(timeout=0.05)
                            except queue.Empty:
                                continue
                            if kind == 'partial':
                                entries[number]['result'] = payload.model_dump(mode='json')
                                persist()
                                saved.set()
                    except Exception:
                        pass  # the original failure is what gets reported
                    stop.set()
                    pool.shutdown(wait=False, cancel_futures=True)
                    for number, future in futures.items():
                        if future.done() and not future.cancelled() and future.exception() is None and entries[number]['status'] != 'completed':
                            try:
                                complete(number, future.result())
                            except Exception:
                                break  # the original failure is what gets reported
                    raise
                pool.shutdown()
            combined = persist()
            if not combined.orders:
                if raw and all(entry['status'] == 'skipped' for entry in raw):
                    raise RuntimeError(f'No page of this PO matches the Tech Pack (style number {style}'
                                       f'{", Quality IDs " + ", ".join(designs) if designs else ""}). '
                                       'Check that it is the right PO, or extract all of its pages anyway.')
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
                if entry['page'] in failed_pages and entry['status'] == 'pending':
                    entry['status'] = 'failed'
            persist(complete=False)
            print(f'PO extraction failed for {doc_id}: {type(exc).__name__}')
