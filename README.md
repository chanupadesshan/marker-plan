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

The **Marker Plan** tab has no upload. Choose a Tech Pack by its TP number or filename;
files without an extracted TP number remain selectable. Then select materials and
individual PO contracts before generating a cutting plan. **Saved plans** lets you
reopen and download previous generations without making those selections again. **Open** navigates
to a dedicated saved-plan page at `/marker-plans/{id}`. It supports direct links, refresh,
Excel download and progress updates for running plans. **Back to Marker Plan** returns to the
Marker Plan tab. Saved-plan pages require Marker Plan view access.

Users with Marker Plan edit access can choose **Run again** or **Delete** in saved history
or on a saved-plan page. Run again opens a review form using the original PO/material snapshots
and current material ply limits; table length, minimum plies, search time and maximum plies
can be reviewed before **Generate new plan** creates a separate saved generation. Missing
ply records keep the saved limit with a note; a failed lookup blocks starting the rerun.
Delete asks for confirmation and removes only the finished saved plan and its download,
keeping source documents and other plans. Queued/running plans cannot be deleted or rerun.

Check values against the source PDF pages. For Tech Packs, use **Edit BOM** to correct style/tech pack numbers, material fields, quantities/units and colours in the table. Add or remove rows as needed, then **Save changes** or **Cancel**. Missing material codes/units and invalid quantities are marked before saving. Only users with Tech Pack edit access can edit or approve. Saved changes require review and approval again. The JSON download remains available under Technical details. Approve each result manually. A purchase order has an **Approve PO**
button both at the top and after its last contract. **Edit PO** opens contract fields and size/quantity tables, with add/remove controls for contracts and size rows. The editor displays the size quantity sum and marks missing values, invalid whole quantities and total mismatches before saving. Grouped totals such as `1,410` are accepted when they match the size quantities. **Save changes** returns an approved PO to review; **Cancel** discards the draft. Save failures keep the draft open. PO editing, retry and approval require Purchase Order edit access. Source pages and extraction evidence are preserved; JSON remains available for download.

Approving asks for confirmation
in an in-page dialog.

## Plies dashboard

A separate page at **http://localhost:5173/plies** (also linked as **Plies** in the top bar) for
the `plies` table. It lists every row with its id and three values, and lets you:

- **Search** across id, Column B, Column C and Column D (every word must match).
- **Add** a row with **Add ply**, **edit** it with the pencil button, or **delete** it with the
  trash button (after a confirmation dialog). Changes are saved to the database immediately.
- Page through the rows (25 per page). A newly added or edited row is highlighted.

Column B must be a whole number, Column C is required (up to 100 characters) and Column D is
optional; a blank Column D is stored as no value (NULL). The same rules are enforced by the server.

The columns keep neutral names (`col_b`, `col_c`, `col_d`) because the source CSV had no header.
To show different headings, edit `PLY_COLUMNS` in `frontend/src/plies.js`; to rename the database
columns, use `ALTER TABLE plies RENAME COLUMN ... TO ...` and update `Ply` in `backend/app/models.py`.
The table also has an auto-generated `id` primary key so a single row can be edited or deleted.

API (`backend/app/ply_routes.py`):

- `GET /api/plies` — all rows, ordered by id
- `POST /api/plies` — add a row (`{col_b, col_c, col_d}`), returns it with its id
- `PUT /api/plies/{id}` — replace a row's values
- `DELETE /api/plies/{id}` — delete a row

On an existing database the table must already exist with its `id` column. A fresh database
gets the table from `Base.metadata.create_all` (empty).

### Max ply in the Wovens table

After a Tech Pack is extracted, its Wovens table has a **Max ply** column (after Qty). For each
material it looks up the related rows of the `plies` table and shows the largest Column D number:

- A material is related to every plies row with the same code in Column C, ignoring a leading
  `R` and any colour suffix, so `R1371` matches `1371`, `R1371` and `R1371-9800`.
- Column D values count as their upper end: `70-75` is 75, `90-100` is 100, `80` is 80. With
  several related rows, the largest number wins (for example `R1936` with `50-60`, `80` and `60`
  shows 80). Column B is not used for matching.
- Under the number you see the related range (one row) or how many entries were used. Hover to
  list every related row. A dash means there is no related row, or it has no Column D value.
- The lookup runs each time the Tech Pack is loaded (`ply_info` in `GET /api/documents/{id}`,
  built by `backend/app/ply_lookup.py`), so edits made on the Plies dashboard show up right away.
  It is never saved inside the extraction or the exported JSON. A failing lookup (for example a
  missing `plies` table) shows dashes and never stops the Tech Pack from loading.

## Components

### Select materials for a marker plan

In **Marker Plan**, search for and open a Tech Pack. Tick the Wovens rows to use,
or use **Select all** and **Clear selection**. The **Selected materials** summary
shows their material codes, descriptions, quantities, maximum plies and PDF pages.
Repeated codes on different rows/pages can be selected independently.

Use **Search by material code** to filter with a full or partial code (case-insensitive).
**Select matches** adds the visible matches to existing selections. Filtering keeps
previously chosen materials selected and visible in the summary, even when hidden
from the source table. Clear the search to show every material again.

Choices are kept separately for each Tech Pack while the app remains open and
survive switching tabs or documents. Refreshing the page clears them. Editing a
source BOM row invalidates its prior selection rather than selecting different
data silently. Choices do not modify the extraction or save a marker plan to the
database. Failed/incomplete extractions cannot be used for material selection.

### Generate a cutting plan

Step 4 of **Marker Plan** appears once materials and purchase orders are selected. It plans,
for each selected material separately, the **marker size combinations** and the **lays (plies)**
that cut every PO size exactly: no shortage and no overproduction. It runs before Lectra nests
the pattern pieces, and it does not calculate marker length, nesting or fabric use.

Settings:

- **Usable table length (m)**, **normal minimum plies** and **search time per material** (1–300 s,
  default 20) apply to the whole order.
- Each material has a **consumption per garment** (m, cm, mm or yd; prefilled from the BOM when its
  unit is a length) and a **maximum plies per lay**. Capacity = floor(table length ÷ consumption),
  an estimate of garment sets on one marker before nesting.
- Maximum plies comes from the plies table. A single value (for example `80`) is prefilled. A range
  (`70-75`) or several related rows (`50-60`, `80`) is never guessed: the cell becomes a **Choose…**
  list of every allowed whole number (70, 71 … 75; or 50 … 60 and 80) and a plan cannot be generated
  until one is picked. **Other value…** allows a number outside the table. Ranges wider than 500
  list only their two ends. The Wovens table's **Max ply** column still shows the largest value.

The chosen POs' size rows are added together by size (labels are compared ignoring case and
surrounding spaces). Every quantity must be a whole number; a missing or fractional quantity stops
the request with a message naming the contract and row.

Rules every plan follows: exact quantity per size; each marker nonempty and within capacity; plies
positive, within the maximum and never increasing from one lay to the next; only the final lay may
be below the minimum; a lay never includes a size that is already complete. The solver first
minimizes unique markers, then lays where its search supports it. Every plan is checked by the
independent validator (`validate_plan`) before it is shown.

The aggregate pattern search tries mixed-size ratios, minimizes unique markers before lay count,
then splits each marker's total plies into valid individual lays. For matching demand, table length,
material settings and ply rules, a rerun starts from the best independently validated saved result.
A timeout, interrupted search or worse result retains that earlier plan. Each generation is still
saved separately. A restricted candidate pool or resource cap never proves an unrestricted minimum.

**Verified nesting (optional)** is available per material in generation and Run again forms. Add
actual size counts and marker length in metres from nesting output; width and efficiency are optional.
Confirm each ratio and length after physical edits. Every length must fit the table and sizes must
match the POs. When supplied, only those verified combinations are permitted; any optimality proof
applies to that catalogue. This does not perform geometric nesting or infer missing dimensions.

Results show, per material, the unique markers (IDs such as `B02-M01` = marker 1 of the second
selected material) with their size counts and lays, the full lay sequence, and required versus
produced quantity per size. Statuses:

| Shown as | Solver status | Meaning |
| --- | --- | --- |
| Minimum markers proven | `OPTIMAL` | Fewest unique markers proven. Lay-count proof is reported separately. |
| Valid plan · not proven minimal | `FEASIBLE` | Meets every rule, but the search was time-limited or restricted, so fewer markers may exist. |
| No plan possible | `INFEASIBLE` | The complete model proves no plan meets the rules. |
| Search time ran out | `UNKNOWN` | No plan found in time; this does not prove that none exists. |
| Too large to solve | `MODEL_TOO_LARGE` | The order exceeds the solver's resource limits. |
| Check settings / Solver error | `INVALID_INPUT` / `ERROR` | Impossible settings for that material, or a solver failure. Other materials are still planned. |

Solving runs in a background thread on the server, one material after another, so the page stays
usable; it shows live progress and polls for results. Every generation is saved separately in the
PostgreSQL `marker_plans` table, including selected PO/BOM snapshots, cutting settings, material
results and timestamps. Later source corrections or deletion do not rewrite saved plans.

**Saved plans** in the Marker Plan tab lists previous generations before any new selections are
made. Use **Open** to review the saved results and **Download Excel** for a complete, validated plan.
History is paginated, newest first, and can be refreshed. Saved inputs and results survive browser
refreshes and backend restarts. A server restart interrupts active solver threads: completed material
results are retained, unfinished materials get an explicit interruption error, and a new generation
is needed for a complete plan. Live per-second solver progress is not persisted.

Excel downloads contain exactly one **Marker plan** worksheet in the supplied production-sheet
structure and palette: a shared size-ratio table, stacked marker groups separated by orange rows,
one coloured plies column per selected BOM row, and matching per-material cut/marker-fabric/used-fabric
columns on the right. Identical marker ratios within each material are grouped into one row with
total plies, number of lays and the numbered per-lay ply breakdown. Total plies can exceed the
per-lay maximum because the original validated lays remain separate; grouping does not rerun or
change the saved plan. Repeated material codes remain separate through their fabric colours and group
IDs. The top block lists PO/colour/size demand; the bottom checks remaining quantities per size and
material. Formulas include cached totals. Verified marker lengths, widths and efficiency are exported
where supplied, with marker fabric use calculated from verified length and total plies. Other
dimensions, layer allowances and used-fabric totals remain blank. Excel length inputs are in cm
and fabric usage is in m.
Workbooks are generated from the stored snapshot without rerunning
the solver. Failed/incomplete or unsaved plans cannot be exported.

API: `POST /api/marker-plans` creates a saved generation; `GET /api/marker-plans?limit=50&offset=0`
lists history; `GET /api/marker-plans/{id}` reopens a snapshot; `GET /api/marker-plans/{id}/excel`
downloads its workbook. All use the existing Marker Plan permission. Install updated backend
requirements (including XlsxWriter) and restart the backend to create the additive table.

Solver code: `backend/app/marker_planner/` (`planner.py`, `pattern_search.py`, `compact_search.py`,
`flexible_search.py`, `shared_seed.py`; `solve_plan()` chooses its search method).
Integration: `backend/app/marker_plan.py` (input mapping and result shaping) and
`backend/app/marker_plan_routes.py` (API). UI: `frontend/src/MarkerCuttingPlan.jsx` and
`frontend/src/marker-plan.js`. It needs `ortools` (in `backend/requirements.txt`); after updating,
reinstall requirements and restart the backend.

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
# Explicit local development mode (PowerShell: $env:APP_ENV='local'; docker compose -f docker-compose.yml -f docker-compose.local.yml up --build)
APP_ENV=local docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Open:
- Frontend: http://localhost:5173
- FastAPI OpenAPI documentation: http://localhost:8000/docs
- Optional MinIO console: run `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d`, then open http://localhost:9001. The override publishes storage ports on loopback only; do not use it in production.

### Production storage configuration

The base Compose file does not publish PostgreSQL or MinIO ports to the host. The backend reaches them using the internal service names `postgres` and `minio`. Set `POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, and `MINIO_ROOT_PASSWORD` explicitly through a deployment secret mechanism. Generate unique credentials with a cryptographically secure generator; do not commit credentials or place production secrets in `.env.example`. The Compose interpolation environment can contain secrets, so restrict access to the deployment environment and avoid printing rendered configuration.

Provision a PostgreSQL application role distinct from `POSTGRES_USER`, and inject `DOCKER_DATABASE_URL` for that role. URL-encode its username and password, use `postgres` as the host, and grant only the database and schema access needed by the application. The current startup creates tables and applies schema alterations, so it needs appropriate schema ownership or DDL privileges until migrations are separated from runtime. Provision a MinIO bucket and a service identity distinct from the root user; inject `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` for that identity. Scope its policy to the configured bucket: bucket existence and listing plus object read, write, and delete. If the application must create the bucket, grant the additional create-bucket permission or create the bucket separately beforehand. Use different secrets for PostgreSQL and MinIO.

Provision the roles, policy, and bucket before starting the backend. Leave `APP_ENV` unset or set to `production`. Backend startup rejects missing and known development service credentials and rejects the configured bootstrap identities for backend access. Compose requires explicit bootstrap credentials but does not assess their strength or uniqueness; operators must ensure those credentials are unique and securely generated. The backend checks do not prove credentials are random or verify an externally configured identity's actual privileges. Protect the internal network and use TLS for traffic crossing an untrusted network; the supplied Compose MinIO connection is not encrypted. The development-oriented Compose setup also needs a production deployment review before internet exposure.

Existing named volumes retain their initialized database and MinIO credentials: changing environment values does not rotate them. Rotate credentials explicitly in the services and secret manager, update all application instances, and verify access before removing old credentials. Do not use the local port override in production.

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

Every endpoint below except `/api/health` and `/api/auth/login` needs a signed-in user: send
`Authorization: Bearer <token>` (a missing, forged, expired or disabled-user token gives `401`). Each area also needs
its permission, otherwise the answer is `403`: **view** allows reading (`GET`) and **edit** allows everything else
(edit includes view). Admins have edit on every area.

| Area | Permission key | Covers |
| --- | --- | --- |
| Tech Packs | `techpacks` | `/api/documents/*` |
| Purchase Orders | `purchase_orders` | `/api/purchase-orders/*` |
| Marker Plan | `marker_plan` | `/api/marker-plans/*` |
| Plies | `plies` | `/api/plies/*` |
| Usage | `usage` | `/api/usage/*` |

Sign-in endpoints (`backend/app/auth.py`):

- `POST /api/auth/login` — `{email, password}`; returns `{token, user}`. `401` with the same message for a wrong password
  or an unknown email; `403` when the password is right but the account is disabled
- `GET /api/auth/me` — who the token belongs to, with `is_admin` and effective `permissions`

There is no public registration. Admin-only user management (`backend/app/admin_routes.py`, also the **Users** page at
`/admin/users`):

- `GET /api/admin/users` — every user (never password hashes)
- `GET /api/admin/features` — the areas that can be granted
- `POST /api/admin/users` — `{email, full_name, password, is_admin, permissions: {techpacks: "view", plies: "edit", ...}}` (`409` if the email exists)
- `PUT /api/admin/users/{id}` — `{full_name, is_admin, is_active, permissions, password?}`; leave `password` out to keep it. Admins cannot demote or disable themselves
- `DELETE /api/admin/users/{id}` — admins cannot delete themselves

**First admin:** set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (and optionally `ADMIN_NAME`) in `.env`. At start-up that account
is created, or, if it already exists, made an active admin (its password is not changed). This is also the way back in if
every admin is locked out: set it to an existing email and restart.

Passwords are stored only as salted scrypt hashes. Tokens are signed with `AUTH_SECRET` and last `AUTH_TOKEN_HOURS`
(default 12). Production mode is the default. Operators must generate `AUTH_SECRET` with a cryptographically secure random number generator: for example, run `python -c "import secrets; print(secrets.token_hex(32))"` in a private environment, and securely transfer the result to a secrets manager. Avoid exposing it in terminal recordings, logs, tickets, or shell history. Inject it as the `AUTH_SECRET` environment variable at deployment; keep production secrets out of source control and do not put them in Compose files or committed `.env` files. Configure every application instance with the same key and leave `APP_ENV` unset or set it to `production`.

Production startup rejects missing, malformed, known development, low-diversity, repeated, and arithmetic-sequence keys. These checks cannot establish cryptographic randomness or detect every predictable value: secure generation and storage remain mandatory. Set `APP_ENV=local` explicitly only for local development; it allows the built-in development secret. Do not use local mode in production. To rotate a key, generate and store a new key the same way, update all instances through the deployment secret mechanism, and restart them in a coordinated rollout. Rotation invalidates existing tokens and requires users to sign in again. Permission changes take effect on the user's next request.
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

Cutting-plan endpoints (`backend/app/marker_plan_routes.py`):

- `POST /api/marker-plans` — `{orders: [{label, size_rows: [{size, quantity}]}], materials: [{material_code,
  description, placement, page_number, consumption, unit, max_plies}], table_length_m, min_plies,
  time_limit_seconds}`; returns the queued job (`202`) with the combined sizes/quantities and each
  material's capacity. `400` for unreadable PO quantities, `422` for invalid settings
- `GET /api/marker-plans/{id}` — job status, live progress per material, and each material's result
  (`status`, `message`, `marker_count`, `lay_count`, `secondary_optimal`, `marker_lower_bound`,
  `elapsed_seconds`, `progress`, `markers`, `lays`, `production`); `summary` once all are done

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
   space in threes (`1 002`). A printed total using comma/dot groups of three
   (`1,410` or `1.410`) is also checked as a grouped integer when the size-row sum
   supports that reading. Decimal parsing and the original printed values are preserved.
   Other ambiguous formats remain for review. Total warnings are refreshed when a saved
   PO is opened or exported; this does not change its approval or source data.
7. Save completed page results and usage incrementally. A failed page leaves
   partial results available, but blocks approval even after manual corrections.

Fields include **contract number, Tech Pack ID, model ID, quality ID, color ID,
total quantity, and size/quantity rows**. Page provenance, warnings and request
usage remain available as review metadata. Older saved results remain readable
with the narrower field set. Missing
values are never inferred. PO extraction performs no ERP updates, material-consumption
calculations or automatic cross-document matching; marker planning happens only in the
Marker Plan step (see "Generate a cutting plan").

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
$env:APP_ENV='local'
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d postgres minio
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
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"your-password"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/your/tech-pack.pdf"
```

JSON output is available from `GET /api/documents/{id}/json` after extraction.
