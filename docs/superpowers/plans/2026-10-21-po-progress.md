# Execution ledger — plan: 2026-10-21-po-extraction.md

Using executing-plans and test-driven-development. Baseline: 21 backend and 5 frontend tests passed with permissions required by existing runtime paths.

Ruling: Work in the existing checkout on feature/po-extraction, preserving the user's running local workspace and untracked design documents. No changes are made on main. This avoids switching the user's application to a separate checkout; isolation is at branch level.

Pre-flight: schemas feed transport, aggregation, pipeline and routes; route summaries feed independent frontend state. Corrections use a dedicated orders-only payload so clients cannot edit processing evidence. This narrows the plan's correction interface to enforce the approved completeness rule.

Task 1: RED confirmed missing PO schema module; implemented PO models and deterministic aggregation.

Task 1: complete — 10 PO schema/grouping tests green. Commit b1ea16b.
Task 2: complete — 5 missing-method failures observed, then 6 PO VLM tests and existing backend tests passed (37 total). Commit f027bc3.
Task 3: complete — missing pipeline module observed, then 4 rendering/durability tests passed. Commit 94aea24.
Task 4: complete — missing router observed, then 9 route tests passed. Commit d44624d.
Task 5: complete — missing uploader observed, then 3 orchestration tests passed. Commit 8e25903.
Task 6: complete — missing workspace observed, then all 9 frontend tests passed. Commit a829544.
Task 7: in progress — README updated; complete suite and fresh reviewer requested.

Ruling: PO state lives in a keyed PurchaseOrderPanel rather than adding all PO editor/polling state directly to App. This keeps independent polling and prevents old document responses from updating a new panel; it costs one additional component.

Ruling: Use the existing checkout branch rather than a separate worktree so the running local app sees the approved changes. All commits remain local; no push or merge.

Final review: fresh reviewer found JSONB shallow-snapshot persistence and late Tech Pack reference warnings. Both were reproduced with failing tests, then fixed. Additional real SQLite ORM commit/reload integration verifies all completed page evidence is durable and approval succeeds without an external API.

Final: Ruling: Re-grade the two review minors as important — losing access to an existing PO in a workspace without history interrupts review; wrong material-specific recovery instructions can derail PO JSON retries. Preserve the prior PO until a successful replacement and make retry wording schema-neutral. Both regressions were observed failing before fixes; cost is a small shared prompt-wording change, covered by existing BOM tests.

Final: fixed JSONB persistence — observed pending versus completed regression RED→GREEN; real ORM reload and approval integration also passes.
Final: fixed late reference warnings — missing mismatch regression RED→GREEN; fresh details/export recalculate against linked metadata, UI reloads when Tech Pack status changes.
Final: fixed selection loss and recovery wording — missing selection export and incorrect materials prompt regressions RED→GREEN.

Task 7: complete — 54 backend tests, 10 frontend tests, production build and git diff whitespace check passed. One upstream Starlette TestClient deprecation warning remains; no dependency changes were needed. Private PO inference remains untested and was not run. Sample business values removed from tracked design notes.

Runtime verification: existing frontend visually inspected at localhost:5173. Restarted only the identified project backend; health returns ok and OpenAPI exposes six PO paths. Startup registered the additive tables successfully.

Integration decision: preserve feature/po-extraction and its local commits; no push or merge requested.
