# Purchase-order extraction for Marker Plan

Status: approved design. No PO extraction has been run against OpenRouter yet.

## Objective

Extend the existing Tech Pack and related PO upload flow so the PO is stored,
processed through JPEG page images and OpenRouter, validated, and displayed for
human review. Preserve the existing Wovens extraction behavior.

## Sample findings

The supplied private PO PDF contains 33 pages. Initial visual inspection
shows a contract/order and size breakdown on each of the first two pages, with
different contract numbers. Its extracted text contains invalid character
mappings; images must be the authoritative extraction input. Unreliable text must
not be supplied as trustworthy auxiliary evidence.

The first page has contract, Tech Pack, model, quality and color identifiers,
dates, a total quantity and prefixed size rows. Exact business values are omitted
from this repository document. The price, line amount and currency cells are
blank; their values remain null. A printed numeric order total is distinct from
those blank cells.

The supplied file can contain multiple Tech Pack references. Selecting it beside
one Tech Pack does not prove every contract in it refers to that Tech Pack.

## Approach

Reuse the current storage, rendering, TLS configuration, required response schema,
request-usage accounting and failed-response diagnostics. Add PO-specific schemas,
prompts, persistence, API endpoints, aggregation, and review UI. Do not reuse
Wovens section cropping, Wovens page classification, or material grouping for POs.

Keeping PO data in dedicated tables is preferred over placing it inside BOM JSON:
contracts have size/quantity rows and their own review lifecycle. A text-only
extractor is unsuitable for this sample's garbled text layer.

## Extracted data

Each purchase-order record contains nullable contract/order number, Tech Pack
reference, model ID, quality ID, color ID, registered date, shipping date, total
quantity, modified-by name, signed-by value, printed total amount, currency, source
pages, warnings and size rows.

Each size row contains the size exactly as printed, quantity, unit price, amount,
currency and source page. Preserve identifiers and leading punctuation as strings.
Do not invent absent supplier, customer, signature, price or currency values.
Preserve printed date/number text; any numeric validation uses explicit decimal
parsing and never treats missing quantities or prices as zero.

Keep separate contracts separate, even when their model, quality or color matches.
Allow multiple contracts on a page and contracts spanning pages. Consolidation
requires matching explicit order identity and compatible header values; ambiguous
records remain separate with warnings. Do not silently remove repeated size rows.

Warn when a fully numeric size breakdown differs from the declared total quantity.
Incomplete numeric data produces an incomplete-validation warning rather than a
false matching total. Flag conflicting header values and uncertain associations.

## Storage and API

Add dedicated purchase-order document and extraction tables without altering or
dropping existing Tech Pack tables. A PO document has filename, original MinIO key,
file hash, status, page count, timestamps, error and an optional foreign key to the
Tech Pack it was uploaded with. Its extraction stores structured JSON, page-level
results, usage and warnings.

Provide PO upload, details, original PDF, JSON download, corrections and approval
endpoints. Validate PDF signature and upload size using the current limits.
Unknown linked Tech Pack IDs return a clear error. Existing Tech Pack API clients
continue to work.

An uploaded pair is explicitly associated by document IDs. Reference mismatches
must be visible as warnings, not automatically corrected or asserted to match.
The first version does not perform BOM consumption calculations or order matching
across the rest of the repository.

## Processing lifecycle

1. Store the original PO PDF in MinIO and create a queued record.
2. Record page count and render/save all page images before model extraction.
3. Process every page using a PO prompt, not a Wovens keyword filter. Empty/non-PO
   pages have explicit page outcomes; discovered pages are not silently discarded.
4. Validate required response fields, order headers and size rows.
5. Aggregate conservatively and retain page provenance.
6. Save extracted PO data, warnings and token usage and mark needs_review.
7. Allow manual corrections, JSON export and explicit approval of nonempty results.

Process pages sequentially with bounded retries and the existing token/diagnostic
mechanisms. Persist usage and completed page results on failure. A missing or
failed page prevents approval of an apparently complete PO document; partial
results remain available for inspection. Saving page images first ensures a first
page failure does not prevent later images from being available.

## Frontend

Send the selected related PO to the new backend instead of retaining it only in
browser state. Support PO-only extraction for the supplied sample and paired
Tech Pack/PO extraction. Show distinct processing statuses for each document;
failure in one must not be presented as failure of the other.

Keep the current clean workspace. Provide BOM and purchase-order results as
separate views, with PO contract summaries, size/quantity tables, source page links,
JSON export, corrections, manual approval and collapsed request-usage details.
Keep user corrections synchronized with persisted data.

## Verification

Use mocked model responses to test strict schemas, multi-contract pages, contract
continuations, repeated rows, reference conflicts, quantity totals, missing prices,
token limits, empty responses, failures with partial results, PDF upload validation,
linking and existing BOM compatibility. Add frontend checks for paired and PO-only
selection and PO results, then run the existing backend/frontend tests and build.

Inspect the supplied PDF locally as a layout fixture without committing the
private sample or its extracted contents to tests. For a live sample run, PO page
images are sent to the configured OpenRouter/model provider; this is a paid request
per page plus any bounded retries. Do not run live inference until the user
explicitly approves that transmission and the sample-run scope. A one-page smoke
test should precede a full 33-page run.

## Not included

No inventory updates, ERP integration, marker optimization, automatic business
approval, supplier inference or automatic matching by filename.
