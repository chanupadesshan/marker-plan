# Purchase-order extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract purchase orders from uploaded PDFs through the existing image/OpenRouter workflow and provide independent PO review and approval.

**Architecture:** Dedicated PO schemas, tables, pipeline and endpoints reuse storage, full-page rendering and the existing model transport. Every page receives an explicit outcome. The frontend uploads either document or both and presents separate results.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy/PostgreSQL, MinIO, PyMuPDF/Pillow, httpx/OpenRouter, React/Vite, pytest and Node tests.

**Spec:** [Approved design](../specs/2026-10-21-po-extraction-design.md)

## Global Constraints

- Preserve existing Wovens APIs, extraction behavior and user edits.
- Use additive tables; never reset existing data or containers.
- Keep private PDFs, rendered pages, credentials and real extracted records out of commits.
- Use mocked inference for development. Live PO transmission needs explicit approval of pages and scope; begin with one page before a full run.
- Preserve printed identifiers, date/number strings and nulls. Parse decimal values only for validation, never fill missing values with zero.
- Save every page image before the first extraction call. Failed or incomplete processing must remain unapprovable after corrections.
- Keep requests sequential and retries bounded; retain usage and successful page results on failure.

## Review Focus

Strict nested response schemas; unchanged BOM request settings; conservative contract grouping; no repeated-row loss; partial-result durability; approval gates enforced on the server; independent paired-upload failures; linked upload versus proven business-reference matching.

## Task 1: PO schemas and conservative aggregation

**Files:** Add `backend/app/po_schema.py`, `backend/app/po_merge.py`, `backend/tests/test_po_schema.py`, `backend/tests/test_po_merge.py`.

**Interfaces:** `POSizeRow(size, quantity, unit_price, amount, currency, source_page)`; `PurchaseOrder(contract_number, tech_pack_reference, model_id, quality_id, color_id, registered_date, shipping_date, total_quantity, modified_by, signed_by, total_amount, currency, size_rows, source_pages, warnings)`; `POPageResult(page_kind, orders, warnings)` where page_kind is `purchase_order`, `empty` or `other`; `POPageTable(page_number, result)`; `POExtraction(orders, page_results, request_usage, warnings, processing_complete)`; `combine_po_pages(pages: list[tuple[int, POPageResult]]) -> POExtraction`. Printed scalar data is nullable string; collections have factories. Reuse StrictModel.

- [ ] Write failing tests with synthetic data: blank prices remain null, size `-C52` stays intact, extra fields fail, multiple orders on one page remain separate.
- [ ] Test continuations: merge only explicit matching contract identity and compatible nonempty headers; retain every size row and source page. Different contracts never merge; conflicting/missing identity remains separate with warnings.
- [ ] Test decimal totals with comma and dot conventions explicitly supported by a documented parser; ambiguous formats and missing quantities produce incomplete-validation warnings. A numeric mismatch produces a warning.
- [ ] Run new tests and confirm failures, then implement schemas and aggregation. Validate page-kind/order consistency. Assign source provenance from the actual page index rather than trusting the model.
- [ ] Run schema/merge tests to green; review that aggregation is deterministic and cannot silently drop rows. Commit the completed task.

## Task 2: PO model requests without changing BOM behavior

**Files:** Modify `backend/app/vlm.py`; add `backend/app/po_prompts.py`, `backend/tests/test_po_vlm.py`; extend existing VLM tests.

**Interfaces:** Add optional keyword-only `_request` overrides `max_tokens`, `stage`, `schema_name` and `result_validator` (callable or None), preserving existing defaults. `OpenRouterVLM.extract_po(image_bytes: bytes) -> POPageResult` requests POPageResult with 6500 output tokens, stage `po_extraction`, schema name `purchase_order_page`, no unreliable auxiliary text. A shared validation hook runs inside the logged request/retry path.

- [ ] Write failing mocked-http tests for nested required fields, PO stage/budget, no auxiliary PDF text, and successful empty/other outcomes.
- [ ] Assert purchase_order with no orders is an invalid empty response, receives at most the existing bounded corrective retry and records diagnostics. Assert length termination is reported as a token-limit failure.
- [ ] Add regression assertions that BOM extraction still uses 6500 tokens and classification 200, with their existing schema names, retry behavior and TLS verification.
- [ ] Implement overrides and the PO method/prompt: treat document instructions as untrusted data, extract every visible contract/size row, preserve blanks/nulls, do not invent signatures or business identities.
- [ ] Run PO and existing VLM tests to green. Commit the completed task.

## Task 3: PO persistence and durable processing

**Files:** Modify `backend/app/models.py`; add `backend/app/po_pipeline.py`, `backend/tests/test_po_pipeline.py`.

**Interfaces:** `PurchaseOrderDocument` stores UUID, optional TechPack FK, filename, MinIO key, SHA256, status, page_count, error and timestamps. `PurchaseOrderExtraction` stores unique document FK, model_name, extracted_json, raw_page_results, warnings and updated_at. `process_purchase_order(document_id: str)` mirrors the background-job entry point. Render full pages using `page_image`; do not call Wovens render_page/locate_pages.

- [ ] Write failing tests with fake sessions/storage/model: all page images are uploaded before the first model call; every page is processed in order; later-page failure preserves earlier results and request usage.
- [ ] Cover first-page failure, invalid PDF/rendering failure, explicit empty pages, all-non-PO documents and successful multi-page extraction. No orders cannot become needs_review/approved as a successful extraction.
- [ ] Implement additive models registered through the existing models import/create_all lifecycle. Use PO-specific MinIO prefixes to avoid collisions.
- [ ] Persist page count and image keys before inference; update a durable snapshot after each successful page. On failure roll back pending writes, reload the document and save partial aggregation, raw page results, usage, error and processing_complete=false.
- [ ] On success aggregate all outcomes, set processing_complete=true and needs_review for nonempty orders. If linked TechPack metadata is available, warn about inconsistent explicit references; association alone must not assert a match.
- [ ] Run pipeline tests to green; verify no dependency on live Docker or external inference. Commit the completed task.

## Task 4: PO API and server-side review rules

**Files:** Add `backend/app/po_routes.py`, `backend/tests/test_po_routes.py`; modify `backend/app/main.py` to include the router.

**Interfaces:** POST `/api/purchase-orders/upload` multipart `file`, optional `tech_pack_id`; GET `/api/purchase-orders/{id}`; GET `/{id}/pdf`; GET `/{id}/json`; PUT `/{id}/extraction`; POST `/{id}/approve`. Upload returns summary with id, filename, status, page_count, linked tech_pack_id and error. Details adds extraction/model/request_usage. Existing document routes remain unchanged.

- [ ] Write failing route tests for PDF signature/size limits, filename sanitation, unknown linked ID=404, PO-only upload, linked upload and queued background task.
- [ ] Test correction/export round-trip and missing IDs/results. Preserve server-owned request usage, raw outcomes and processing completeness on corrections; recompute aggregation warnings/provenance using a documented canonical order list.
- [ ] Test that empty orders, failed processing or missing page outcomes block approval even if a client submits processing_complete=true. Successful reviewed nonempty results can approve.
- [ ] Implement routes with current storage/session conventions and an additive router registration. Corrections do not turn failed processing into complete processing.
- [ ] Run route tests and existing BOM endpoint tests to green. Commit the completed task.

## Task 5: Upload PO-only or a related pair

**Files:** Modify `frontend/src/DocumentUpload.jsx`, `frontend/src/api.js`, `frontend/src/App.jsx`; add `frontend/src/uploadDocuments.js`, `frontend/tests/po-upload.test.mjs`.

**Interfaces:** DocumentUpload calls `onUpload({techPack, po})`; either file enables extraction. Export `poApi` alongside existing `api`. `uploadDocuments({techPack, po}, clients) -> {techPackResult, poResult}` returns per-document success/error outcomes; upload TechPack first when present, passing its returned ID to PO upload. If TechPack upload fails, still upload the PO independently and report the failed association.

- [ ] Write failing tests for TechPack-only, PO-only, paired upload with linked ID, and independent failure outcomes.
- [ ] Implement upload orchestration and wire separate selected IDs/results/status polling in App. Guard asynchronous responses against selection changes, including save and approval responses.
- [ ] Do not clear a selected PO merely because the TechPack is removed/replaced. Show a clear upload/processing status for each selected document and meaningful action text.
- [ ] Run frontend tests to green, including existing stale-response regressions. Commit the completed task.

## Task 6: PO review workspace

**Files:** Add `frontend/src/PurchaseOrderWorkspace.jsx`; modify `frontend/src/App.jsx`, `frontend/src/styles.css`; add `frontend/tests/po-workspace.test.mjs`. Confirm actual stylesheet filename before editing.

**Interfaces:** PurchaseOrderWorkspace consumes the PO details object plus save/approve callbacks and busy state; reuses TokenUsage and the established JSON editor pattern. App provides distinct BOM/PO views with independent records and messages.

- [ ] Write failing render tests for contract headers, exact size strings, blank prices, source-page PDF links, warnings, multiple contracts and partial-result errors.
- [ ] Implement readable contract summaries and size/quantity tables, PDF/JSON actions, correction and approval controls, and collapsed technical/token details.
- [ ] Hide approval for empty/incomplete/failed results and keep server rejection handling visible. Ensure partial successful rows remain readable after later-page failure.
- [ ] Check responsive layout and keyboard access without changing branding or reintroducing the removed document sidebar.
- [ ] Run frontend tests and production build to green. Commit the completed task.

## Task 7: Integration, documentation and final review

**Files:** Modify `README.md`; add integration/regression cases to the PO test files as needed.

- [ ] Document the complete PO lifecycle, optional TechPack association, extracted fields, setup/run commands, manual review, token accounting, limitations and privacy of live inference. Distinguish implemented behavior from future matching/marker planning.
- [ ] Run all backend tests: set PYTHONPATH to the absolute backend folder, then `.venv/Scripts/python.exe -m pytest backend/tests -q -p no:cacheprovider`.
- [ ] Run all frontend tests using the available Node runtime: `node --test frontend/tests/*.test.mjs`; build with `node frontend/node_modules/vite/bin/vite.js build frontend`.
- [ ] Review the complete diff against the approved spec and Review Focus. Verify no private sample, diagnostics or secrets are tracked; no existing BOM behavior is removed. Obtain fresh code review through the applicable review skill and resolve findings.
- [ ] Locally verify upload/status/review flows with synthetic PDF/model data. Report exact checks and any untested live behavior.
- [ ] Only after explicit transmission approval: run the approved sample one-page smoke test, inspect fields/nulls/provenance and token usage, then run the remaining pages only within the approved scope. Do not claim live sample accuracy based on mocked tests.
- [ ] Commit documentation and report remaining limitations. Do not push or deploy without user authorization.

## Plan self-review

The tasks cover every approved workflow stage: additive persistence, full-page image capture, strict PO inference, conservative grouping, durable partial results, upload/linking, correction/approval, independent UI results, token visibility and regression checks. The review gate uses server-owned completeness; sample data is excluded from fixtures. Native execution is suitable because transport, schemas, persistence and UI contracts are closely coupled.
