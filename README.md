# Marker Plan

Marker Plan is a garment document data-extraction project. Its purpose is to collect
**Bill of Materials (BOM) data from Tech Packs** and **purchase-order data from the
related Purchase Orders (POs)**, and present structured results for human review.

The Tech Pack describes the garment's materials; the related PO supplies the
ordering information. The intended workflow brings both documents together as one
document set. The current extraction implementation focuses on the **Wovens BOM**
inside a Tech Pack.

## Purpose and current scope

| Document / capability | Purpose | Current implementation |
| --- | --- | --- |
| Tech Pack PDF | Extract the Wovens BOM: material codes, descriptions, composition, placement, quantities, units, and colorways | Backend extraction, storage, review, corrections, and approval implemented |
| Related PO PDF | Extract purchase-order information such as order number, supplier, ordered items, quantities, and delivery details where present | File selection UI implemented; backend storage and extraction are not implemented yet |
| Combined document set | Keep the Tech Pack and its related PO together for review | Grouped upload panel implemented; no persistent Tech Pack-to-PO association yet |

The PO fields above describe the intended scope, not an existing extraction schema.
Selecting a PO currently keeps the file in the browser session only. It is not
uploaded, saved in MinIO or PostgreSQL, or sent to OpenRouter. Refreshing the page
clears that selection.

## Using the upload panel

1. Select the **Tech Pack PDF** in the Tech Pack field.
2. Select its **related PO PDF**, when available, in the Related PO field.
3. Click **Extract Wovens** to upload and process the Tech Pack.
4. Review the Wovens tables against the original PDF, correct values if necessary,
   and approve the result manually.

Only the Tech Pack is processed by the current backend. The related PO remains a
local selection for the UI. Replacing an already selected Tech Pack clears its PO
selection so an old PO is not accidentally shown with a different Tech Pack.

## Components

- **PDF**: PyMuPDF scans page text and renders page JPEGs. No hardcoded PDF page numbers.
- **VLM**: OpenRouter, default `qwen/qwen3-vl-235b-a22b-instruct` (configurable).
- **Validation**: Pydantic validates structured JSON and flags missing quantities/units.
- **Storage**: MinIO stores source PDFs and rendered BOM page images.
- **Database**: PostgreSQL stores extracted JSONB, normalized page results, metadata, token usage, and material rows.
- **UI**: React/Vite groups Tech Pack and related PO selection in one panel, displays Wovens tables with one row per material and separate colorway columns, and provides PDF viewing, JSON export, corrections, and manual approval. Token usage and JSON tools appear under Technical details.

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

These endpoints currently operate on Tech Pack documents and Wovens BOM results.
There is no PO upload or PO extraction endpoint yet.

- `GET /api/documents` — recent documents
- `POST /api/documents/upload` — upload PDF (multipart field `file`)
- `GET /api/documents/{id}` — metadata, status, extraction JSON
- `GET /api/documents/{id}/pdf` — source PDF
- `GET /api/documents/{id}/json` — download extracted JSON
- `PUT /api/documents/{id}/extraction` — save manually corrected JSON
- `POST /api/documents/{id}/approve` — mark verified after review

## Local Python environment (PowerShell)

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The root `requirements.txt` includes the backend dependencies. You can also use
`.\.venv\Scripts\python.exe` directly without activating the environment.

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

The tests need no OpenRouter API key, PostgreSQL server, or MinIO: they cover dynamic page detection and material/colorway merging. Full end-to-end extraction requires a valid OpenRouter key and running services.

## Known MVP limitations / next steps

- Add backend upload, validation, and storage for PO PDFs; persist their association with the related Tech Pack.
- Define and implement a purchase-order extraction schema and pipeline, then provide a review interface for the extracted PO data.
- Detection is heuristic + a visual check. Unusual page headings, multi-page continuation tables without repeated headings, and low-quality scans can still be missed. Review the detected page list. For rigorous completeness add a document-wide page classifier and manual page selection.
- JSON Schema response support varies by OpenRouter route/provider; verify the chosen model/provider accepts structured outputs. The default model and key are configured via `.env`.
- LLM extraction is probabilistic. Schema validity is **not** data correctness. Review and correct codes, quantities, units, and colorway mappings against original pages.
- `BackgroundTasks` is a dev/MVP choice. For production use a durable queue (Redis/RQ or Celery), retries/idempotency, per-document locks, progress events, and migrations (Alembic).
- Authentication/authorization, rate limiting, upload malware scanning, logging/monitoring, TLS, hardened container credentials, pagination, audit history, and role-based approval are not included. **Do not expose this demo directly on the internet.**
- External API processing sends PDF page images to OpenRouter/model providers; confirm document confidentiality and processing permissions.
- Tech Pack extraction currently handles Wovens only. Other BOM categories, such as Knits and Trims, require separate extraction support. PO extraction is a separate document workflow and remains planned.

## Example source PDF notes

The shared sample Tech Pack (style 7196, TP 28156) has Wovens on **physical PDF pages 37 and 43** (zero-based indexes 36 and 42). Six Wovens materials occur across colorways 8833, 8853, 9933, and 9955. These positions are **not hardcoded** in the application. This example is for validation only.

## Upload with curl

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "file=@/path/to/your/tech-pack.pdf"
```

JSON output is available from `GET /api/documents/{id}/json` after extraction.
