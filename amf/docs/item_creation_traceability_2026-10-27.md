# Item Creation result links and lifecycle — 27 October 2026

AMF `0.7.3` extends the reviewed workflow without changing the numbering allocator, standard compatibility matrix or recipe generation. Current status is maintained in the [improvement tracker](item_creation_improvements.md).

## Syringe selection

The child-table Syringe selector accepts six-character Item codes `70X___`, where `X` is a digit from 1 to 9 or a letter and each underscore represents one further character. Its fixed server expression is `^70[1-9A-Za-z]...$`. Thus `708000`, `709000`, `70E000` and `70F000` can appear regardless of Item Group. Zero or punctuation in the third position, a retired leading slash or an extra character does not match; `700025` is excluded. Search includes the Item code, name and reference, honors Item read permissions and uses bound SQL parameters and bounded pagination.

This is a catalogue selector. Existing server-side engineering compatibility, identity and enabled-Item checks still determine which selected configurations can be released. Body selection retains `5_1___`.

## Execution records and reverse search

The read-only **Items and BOM Revisions** child table records every executed Item action, selected BOM revision, BOM action, previous revision and completion time. The original execution JSON remains retained. Both records are written in the same request transaction; a link-writing failure propagates and rolls back execution.

**Search Execution Results** opens the **Item Creation Results** report for the request. **Item Creation History** on Item and BOM forms opens the same report filtered to that record. The BOM filter searches both the selected revision and the replaced revision. The report includes cancelled requests and amendment predecessors, and filters every result through its parent request's read permissions. Item/BOM read permission is also required. Exact reference columns have database indexes.

Direct child edits, standalone cancellation and deletion are rejected. Parent API saves cannot alter the result table. Requests with review/execution history, cancelled requests and amendments are retained.

## Cancellation

System Managers receive cancellation and amendment permission, consistent with the existing creation/review role. Native **Cancel** asks for a reason and states the retention policy. The server verifies the currently submitted state under a row lock, protects the approved definition and history, and records the reason, user and time. A second cancellation cannot overwrite the first decision.

Cancellation withdraws the request. Generated Items, submitted BOMs, default revision selections, review history, result links and suffix reservations are retained. It does not disable Items, cancel BOMs, restore former default revisions or release identifiers. The user explicitly chose to review retirement separately.

## Amendments

On a cancelled request, **Create Amendment** asks for an engineering reason and creates a draft linked through `amended_from`. Native amendments are also normalized and validated on insertion. The draft reuses the original head and the current head BOM's actual plug/seat selections. Existing Item identity remains protected. Use a separate new request for a different head family.

Review history, approval fields, execution results and cancellation details start empty in the amendment. Save the intended changes, refresh the complete plan, enable replacement proposals when a recipe differs, record a fresh engineering review and submit normally. The predecessor and amendment reason are included in the approval fingerprint. Further reason/definition changes invalidate that approval. Existing ordinary requests retain their original hash format.

A locked predecessor permits one active draft/submitted amendment. An existing draft must be completed or revised instead of creating a parallel sibling. Once its submitted amendment is cancelled, the next amendment follows that request. The predecessor link cannot be changed after saving. Submitted request edits are rejected; changes proceed through cancellation and fresh review.

## Migration and verification

`amf.patches.v12_0.install_item_creation_traceability` reloads the result child table before the parent, reloads the report and indexes existing recorded execution JSON. It is safe to repeat and does not infer results for older requests without execution snapshots. It never edits historical Items/BOMs or releases reservations. The previous workflow patch remains registered before it.

Verification includes 132 focused/regression Python tests, 15 read-only site regression tests and expanded actual form-script tests. Two targeted schema/report migration passes, repeated result backfill, a real seven-Item/seven-BOM cancellation and amendment case with two replacement BOMs, permission-filtered reverse searches and immutable result checks passed. Live digit/letter syringe searches and Guest denials passed. An injected failure after result insertion propagated and rolled back the complete execution. Real write-path checks prohibit internal commits and roll back temporary business records, result rows, registry entries and generated files.

Use the normal deployment process to load Python and form scripts together, apply registered patches and reload web/worker processes. No broad migration or process restart was run during these targeted checks.
