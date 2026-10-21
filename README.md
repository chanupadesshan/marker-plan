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
| Related PO PDF | Extract contract number, Tech Pack reference, model/quality/color IDs, dates, quantities and size breakdowns | Upload, MinIO storage, extraction, review, corrections and approval implemented |
| Combined document set | Keep the Tech Pack and its related PO together for review | Paired upload persists an optional Tech Pack ID; business-reference matching still requires review |

PO-only and Tech Pack-only uploads are supported. A file containing multiple
contracts may reference different Tech Packs: uploading a pair does not prove
that every contract belongs to the selected Tech Pack.

## Using the upload panel

1. Select a **Tech Pack PDF**, a **PO PDF**, or both.
2. Click **Extract Wovens**, **Extract PO**, or **Extract documents**.
3. Use the result tabs to review the BOM and purchase orders independently.
4. Check values against source PDF pages, edit JSON under Technical details if
   needed, then approve each result manually.

An upload failure in one file does not prevent the other file from uploading.
If the Tech Pack upload fails, its PO is uploaded independently with a visible
association warning. Processing failures and approval statuses remain separate.

## Components

- **PDF**: PyMuPDF scans page text and renders page JPEGs. No hardcoded PDF page numbers.
- **VLM**: OpenRouter, default `qwen/qwen3-vl-235b-a22b-instruct` (configurable).
- **Validation**: Pydantic validates structured JSON and flags missing quantities/units.
- **Storage**: MinIO stores source PDFs and rendered BOM/PO page images.
- **Database**: PostgreSQL stores extracted JSONB, normalized page results, metadata, token usage, and material rows.
- **UI**: React/Vite displays Wovens tables and separate PO contract summaries/size tables, with PDF viewing, JSON export, corrections and manual approval. Token usage and JSON tools appear under Technical details.

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

- `GET /api/documents` — recent documents
- `POST /api/documents/upload` — upload PDF (multipart field `file`)
- `GET /api/documents/{id}` — metadata, status, extraction JSON
- `GET /api/documents/{id}/pdf` — source PDF
- `GET /api/documents/{id}/json` — download extracted JSON
- `PUT /api/documents/{id}/extraction` — save manually corrected JSON
- `POST /api/documents/{id}/approve` — mark verified after review

Purchase-order endpoints:

- `POST /api/purchase-orders/upload` — multipart `file`, optional `tech_pack_id`
- `GET /api/purchase-orders/{id}` — status, results, usage and approval readiness
- `GET /api/purchase-orders/{id}/pdf` — original PDF (use `#page=N` for a page)
- `GET /api/purchase-orders/{id}/json` — complete extraction download
- `PUT /api/purchase-orders/{id}/extraction` — corrections shaped as `{"orders": [...]}`
- `POST /api/purchase-orders/{id}/approve` — approve nonempty, fully processed results

## Purchase-order extraction workflow

1. Store the source PDF and queued metadata in dedicated PO tables.
2. Render and save **every page** as a full-page JPEG before the first model call.
   PO pages do not use the Wovens detector or section cropping.
3. Send images sequentially to OpenRouter with a PO-specific strict schema.
   Record purchase-order, empty or unrelated page outcomes explicitly. PDF text
   is not used because some documents have unusable character mappings.
4. Preserve printed strings, prefixes, dates and decimal punctuation. Blank
   prices/currencies/signatures remain null; the printed total is separate.
5. Group matching explicit contract identities only when headers are compatible.
   Preserve repeated size rows. Ambiguous identities/conflicts remain separate.
6. Warn about incomplete quantities or mismatching totals. Numeric validation
   accepts ungrouped decimals with comma or dot; ambiguous grouping is left for review.
7. Save completed page results and usage incrementally. A failed page leaves
   partial results available, but blocks approval even after manual corrections.

Fields include contract number, Tech Pack reference, model/quality/color IDs,
registration/shipping dates, total quantity, modified-by, signed-by, printed total
amount, currency, size/quantity/price/amount rows and page provenance. Missing
values are never inferred. No ERP updates, material-consumption calculations,
marker optimization or automatic cross-document matching are performed.

Each page uses a paid model request with bounded retries and a 6500-token output
allowance per attempt. Technical details reports provider usage and truncation;
missing counts are unavailable, not zero. Uploading and extracting transmits page
images to OpenRouter and its model provider. Use documents you are authorized to
send. Development tests mock inference and do not transmit private sample PDFs.

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

Restart the backend after updating to register the new additive PO tables.
Existing Tech Pack records and Docker volumes are retained.

## Tests

Failed OpenRouter responses are saved locally under `.venv/diagnostics/` (override
with `DIAGNOSTICS_DIR`). Files contain the generated response and request usage
metadata, without API keys, request prompts, or input images. They may contain
extracted document content and are excluded from source control by default.
The client requests strict structured output and a provider that supports the
requested parameters. A detected Wovens section with zero rows gets one corrective
retry, then fails clearly if the model still returns nothing. Every attempt is
included in the token usage panel. Existing results are not rerun automatically.

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

The tests need no OpenRouter API key, PostgreSQL server, or MinIO. They cover
Wovens detection/merging, PO grouping, strict responses, partial failures, approval
rules, paired uploads and review rendering. Full end-to-end extraction requires
a valid OpenRouter key and running services.

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
