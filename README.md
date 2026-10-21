# Marker Plan

Marker Plan is a garment document data-extraction project. Its purpose is to collect
**Bill of Materials (BOM) data from Tech Packs** and **purchase-order data from the
related Purchase Orders (POs)**, and present structured results for human review.

The Tech Pack describes the garment's materials; the related PO supplies the
ordering information. The intended workflow brings both documents together as one
document set. Both the **Wovens BOM** and **purchase-order contracts and size rows**
have independent extraction and review workflows.

## Purpose and current scope

| Document / capability | Purpose | Current implementation |
| --- | --- | --- |
| Tech Pack PDF | Extract the Wovens BOM: material codes, descriptions, composition, placement, quantities, units, and colorways | Backend extraction, storage, review, corrections, and approval implemented |
| Related PO PDF | Extract contract number, Tech Pack ID, model/quality/color IDs, total quantity and size/quantity breakdowns | Upload, MinIO storage, extraction, review, corrections and approval implemented |
| Combined document set | Keep the Tech Pack and its related PO together for review | The API accepts an optional `tech_pack_id` on PO upload; the sidebar uploads each document independently, so it does not link them. Business-reference matching still requires review |

Tech Packs and POs are uploaded, extracted, reviewed and approved independently.
A file containing multiple contracts may reference different Tech Packs, so an
association between a PO and a Tech Pack never proves that every contract belongs to it.

## Using the sidebar

The left sidebar has three tabs: **Tech Pack**, **Purchase Order** and **Marker Plan**.
The Tech Pack and Purchase Order tabs each have:

1. **Upload and extract**: choose a PDF, then click **Extract Wovens** or **Extract PO**.
2. **Search**: filters that tab's list as you type; every word must match. Tech Packs
   match on file name, style number, Tech Pack number and status. POs match on file
   name, contract number, Tech Pack ID and status.
3. **Extracted list**: every saved extraction, newest first, with its status. Statuses
   refresh automatically while an extraction is running. Click a row to review it.
4. **Delete**: the trash icon on each row permanently deletes that document after a
   confirmation dialog. It removes the database rows (including the extraction and, for
   Tech Packs, the Wovens material rows) and the stored PDF and page images. It cannot be
   undone. Items that are queued or processing cannot be deleted until they finish. A PO
   uploaded alongside a deleted Tech Pack is kept and becomes unlinked.

The **Marker Plan** tab has no upload. It has one search box that searches every Tech
Pack and purchase order together and groups the results by type. Searching a Tech Pack
number finds the Tech Pack and the POs that reference it. Picking a result opens it in
the main area and keeps you on the Marker Plan tab, so you can move between results;
the delete button works there too.

Check values against the source PDF pages, edit JSON under Technical details if
needed, then approve each result manually. A purchase order has an **Approve PO**
button both at the top and after its last contract. Approving asks for confirmation
in an in-page dialog.

## Components

### Backend filenames

Files in `backend/app/` use prefixes to identify the document workflow:

| Tech Pack files | Purpose |
| --- | --- |
| `techpack_schema.py` | Wovens extraction data shapes |
| `techpack_pipeline.py` | Tech Pack background extraction |
| `techpack_pdf.py` | Wovens page detection/cropping and PDF rendering helpers |
| `techpack_merge.py` | Combine extracted Wovens materials |
| `techpack_wovens.py` | Wovens section boundaries and colorway normalization |

| PO files | Purpose |
| --- | --- |
| `po_schema.py` | Purchase-order data shapes |
| `po_pipeline.py` | PO background extraction |
| `po_prompts.py` | PO model instructions |
| `po_merge.py` | Group contracts and validate quantities |
| `po_routes.py` | PO upload and review endpoints |

Shared files include `openrouter_client.py` (model requests for both workflows),
`models.py` (database tables), `storage.py`, `database.py`, `config.py`, and
`main.py` (application entry point and Tech Pack endpoints). PO processing also
reuses the rendering helpers in `techpack_pdf.py` (`trimmed_page_image` crops each
PO page to its printed content and renders it at 300 DPI or higher).
`table_groups.py` and `table_layout_schema.py` provide shared row-group extraction.

- **PDF**: PyMuPDF scans page text and renders page JPEGs. No hardcoded PDF page numbers.
- **VLM**: OpenRouter, default `qwen/qwen3-vl-235b-a22b-instruct` (configurable).
- **Validation**: Pydantic validates structured JSON and flags missing quantities/units.
- **Storage**: MinIO stores source PDFs and rendered BOM/PO page images.
- **Database**: PostgreSQL stores extracted JSONB, normalized page results, metadata, token usage, and material rows.
- **UI**: React/Vite. A three-tab sidebar (Tech Pack / Purchase Order / Marker Plan) handles upload, search, the list of extracted documents and deletion; the main area displays Wovens tables and PO contract summaries/size tables, with PDF viewing, JSON export, corrections and manual approval. Token usage and JSON tools appear under Technical details.
  Key files in `frontend/src/`: `Sidebar.jsx`, `documentSearch.js` (search), `ConfirmDialog.jsx` and `useConfirm.jsx` (confirmation dialogs).

## Start with Docker

```bash
cp .env.example .env
# Replace OPENROUTER_API_KEY and database/MinIO credentials in .env
# No API key is committed to source control.
docker compose up --build
```

Open:
- Frontend: http://localhost:5173
- FastAPI OpenAPI documentation: http://localhost:8000/docs
- MinIO console: http://localhost:9001

Upload a PDF. Initial processing happens in a FastAPI background task (not a durable worker). Watch status become `needs_review`, inspect the material/colorway table, compare against the source PDF, correct JSON if necessary, and approve manually.

## Implemented Tech Pack extraction workflow

1. `POST /api/documents/upload`: validate PDF signature + size, store in MinIO, create DB record.
2. `locate_pages()`: scan all pages for Wovens/BOM; classify ambiguous and image-only pages visually through OpenRouter.
3. Render detected page images as JPEG and upload images to MinIO.
4. Extract Wovens material rows and ALL colorway columns; stop before next category such as `Knits`.
5. Pydantic validates JSON; merge matching materials across different BOM pages without losing colorway-specific fields.
6. Save extracted document JSONB, normalized per-page results, request usage, warnings, and searchable material rows in PostgreSQL.
7. Display materials in React and allow corrections. **Not automatically approved.**

## API

Tech Pack / Wovens endpoints:

- `GET /api/documents` — recent documents (latest 100) with `style_number` and `tech_pack_number` for search
- `POST /api/documents/upload` — upload PDF (multipart field `file`)
- `DELETE /api/documents/{id}` — permanently delete the document, its extraction, material rows and stored files (`409` while queued or processing)
- `GET /api/documents/{id}` — metadata, status, extraction JSON
- `GET /api/documents/{id}/pdf` — source PDF
- `GET /api/documents/{id}/json` — download extracted JSON
- `PUT /api/documents/{id}/extraction` — save manually corrected JSON
- `POST /api/documents/{id}/approve` — mark verified after review

Purchase-order endpoints:

- `GET /api/purchase-orders` — recent POs (latest 100) with `contract_count`, `contract_numbers` and `tech_pack_references` for search
- `POST /api/purchase-orders/upload` — multipart `file`, optional `tech_pack_id`
- `DELETE /api/purchase-orders/{id}` — permanently delete the PO, its extraction and stored files (`409` while queued or processing)
- `GET /api/purchase-orders/{id}` — status, results, usage and approval readiness
- `GET /api/purchase-orders/{id}/pdf` — original PDF (use `#page=N` for a page)
- `GET /api/purchase-orders/{id}/json` — complete extraction download
- `PUT /api/purchase-orders/{id}/extraction` — corrections shaped as `{"orders": [...]}`
- `POST /api/purchase-orders/{id}/approve` — approve nonempty, fully processed results
- `POST /api/purchase-orders/{id}/retry` — resume a failed document, keeping completed pages and usage history

## Purchase-order extraction workflow

1. Store the source PDF and queued metadata in dedicated PO tables.
2. Render and save **every page** as a JPEG before the first model call. Each page
   is cropped to its printed content (many PO pages are mostly white) and rendered
   at 300 DPI or higher so small numbers stay legible. PO pages do not use the
   Wovens detector or section cropping.
3. Send images sequentially to OpenRouter with a PO-specific schema. PO requests use
   JSON-object mode with the schema supplied in the prompt, and the backend validates
   every field locally. Strict `json_schema` decoding is deliberately not used for POs:
   with the default model it produced empty-string quantities and blank-line loops.
   A blank quantity string is rejected and retried; null means genuinely unreadable.
   Record purchase-order, empty or unrelated page outcomes explicitly. PDF text
   is not used because some documents have unusable character mappings.
4. Preserve printed identifiers, size prefixes and decimal punctuation. Missing
   requested values remain null; prices, monetary amounts, dates and signatures
   are not part of the extraction.
5. Group matching explicit contract identities only when headers are compatible.
   Preserve repeated size rows. Ambiguous identities/conflicts remain separate.
6. Warn about incomplete quantities or mismatching totals. Numeric validation
   accepts ungrouped decimals with comma or dot, and whole numbers grouped by a
   space in threes (`1 002`). Ambiguous comma/dot grouping is left for review.
7. Save completed page results and usage incrementally. A failed page leaves
   partial results available, but blocks approval even after manual corrections.

Fields include **contract number, Tech Pack ID, model ID, quality ID, color ID,
total quantity, and size/quantity rows**. Page provenance, warnings and request
usage remain available as review metadata. Older saved results remain readable
with the narrower field set. Missing
values are never inferred. No ERP updates, material-consumption calculations,
marker optimization or automatic cross-document matching are performed.

Each page uses a paid model request with bounded retries and a 6500-token output
allowance per attempt. Technical details reports provider usage and truncation;
missing counts are unavailable, not zero. Uploading and extracting transmits page
images to OpenRouter and its model provider. Use documents you are authorized to
send. Development tests mock inference and do not transmit private sample PDFs.

## Large tables and output limits

Both workflows split large ruled tables into groups of up to six separator bands
(including any header/footer bands). Each request receives a full-page context
panel for matching headers and a separate full-width target crop. Only target
rows are extracted. Crops have disjoint ownership; identical physical rows are
retained rather than removed by value.

If a response ends with `finish_reason=length`, its incomplete JSON is discarded
and that group is split at a known row separator. Successful smaller groups
replace the truncated parent. The output allowance is not increased.

For unruled tables that truncate, one additional layout-only model request proposes
logical row gaps. Its output allowance is 1800 tokens. The backend checks proposed
cuts against actual whitespace corridors before using them. If no safe boundary
remains, the page fails explicitly rather than accepting truncated data or making
a blind crop through text. Complex merged cells and faint/irregular layouts can
still require review.

Each page is capped at 32 group/layout operations; transport/schema retries remain
bounded separately. Small pages normally need one extraction request. Larger
tables, layout detection and splitting add paid requests and processing time.
Technical details shows page, row-group ID (for example `2.1`) and token usage for
each attempt. Group IDs describe extraction regions, not guaranteed row counts.

Completed group snapshots are saved incrementally. Failed/incomplete processing
cannot be approved, including after editing partial results. No existing document
is automatically reprocessed after a code update; upload it again to use grouping.

PO responses dominated by whitespace or containing a run of identical complete
contract blocks are treated as malformed generation rather than oversized tables.
They get one compact single-line JSON retry with the same model and output allowance.
PO requests already use JSON-object mode with the schema in the prompt, and the
backend enforces every field through its strict response validator. Repeated size rows within an
order and distinct contract blocks are preserved; suspected looping output is
rejected and re-extracted, never silently deduplicated. Both attempts retain token
usage and diagnostics. Repeated malformed output fails explicitly without invoking
row splitting. This recovery stays within the existing three-attempt request cap
and does not change the Tech Pack request path.

Use **Retry failed pages** on a failed PO to reuse its source PDF and saved images,
skip completed pages, and retain previous token usage. A failed page is reprocessed
from its beginning; completed groups from that page are not blindly reused. Retry
is blocked when aggregated orders contain manual corrections, so those edits are
not silently replaced by older page evidence. Export edited results before starting
a new extraction instead.
Retries are manual and make additional paid requests only for unfinished pages.

## Local Python environment (PowerShell)

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The root `requirements.txt` includes the backend dependencies. You can also use
`.\.venv\Scripts\python.exe` directly without activating the environment.

To run the app locally with only PostgreSQL and MinIO in Docker:

```powershell
docker compose up -d postgres minio
# In .env set DATABASE_URL to your localhost PostgreSQL URL and credentials.
# Set MINIO_ENDPOINT=localhost:9000, MINIO_ACCESS_KEY and MINIO_SECRET_KEY
# to match MINIO_ROOT_USER and MINIO_ROOT_PASSWORD used by Docker.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

In another terminal (Node.js/npm must be on PATH):

```powershell
cd frontend
npm install
npm run dev
```

Restart the backend after updating to register new routes (for example the list and
delete endpoints) and the additive PO tables. `uvicorn` without `--reload` keeps
serving the old code until restarted. Existing Tech Pack records and Docker volumes
are retained.

## Tests

Failed OpenRouter responses are saved locally under `.venv/diagnostics/` (override
with `DIAGNOSTICS_DIR`). Files contain the generated response and request usage
metadata, without API keys, request prompts, or input images. They may contain
extracted document content and are excluded from source control by default.
Tech Pack requests use strict structured output and a provider that supports the
requested parameters (PO requests use JSON-object mode, see above). A detected Wovens section with zero rows gets one corrective
retry, then fails clearly if the model still returns nothing. Every attempt is
included in the token usage panel. Existing results are not rerun automatically.

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

The tests need no OpenRouter API key, PostgreSQL server, or MinIO. They cover
Wovens detection/merging, PO grouping, strict responses, partial failures, approval
rules, list/delete endpoints and review rendering. Full end-to-end extraction requires
a valid OpenRouter key and running services.

Frontend tests (sidebar, search, dialogs and PO review rendering) run with Node.js:

```bash
cd frontend
npm install
npm test
```

## Known MVP limitations / next steps

- Detection is heuristic + a visual check. Unusual page headings, multi-page continuation tables without repeated headings, and low-quality scans can still be missed. Review the detected page list. For rigorous completeness add a document-wide page classifier and manual page selection.
- JSON Schema response support varies by OpenRouter route/provider; verify the chosen model/provider accepts structured outputs. The default model and key are configured via `.env`.
- LLM extraction is probabilistic. Schema validity is **not** data correctness. Review and correct codes, quantities, units, and colorway mappings against original pages.
- `BackgroundTasks` is a dev/MVP choice. For production use a durable queue (Redis/RQ or Celery), retries/idempotency, per-document locks, progress events, and migrations (Alembic).
- Authentication/authorization, rate limiting, upload malware scanning, logging/monitoring, TLS, hardened container credentials, pagination, audit history, and role-based approval are not included. **Do not expose this demo directly on the internet.**
- External API processing sends PDF page images to OpenRouter/model providers; confirm document confidentiality and processing permissions.
- Tech Pack extraction handles Wovens only. Other BOM categories, such as Knits and Trims, require separate support. PO extraction processes every page but still depends on visual readability and model accuracy.

## Example source PDF notes

The shared sample Tech Pack (style 7196, TP 28156) has Wovens on **physical PDF pages 37 and 43** (zero-based indexes 36 and 42). Six Wovens materials occur across colorways 8833, 8853, 9933, and 9955. These positions are **not hardcoded** in the application. This example is for validation only.

## Upload with curl

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@/path/to/your/tech-pack.pdf"
```

JSON output is available from `GET /api/documents/{id}/json` after extraction.
