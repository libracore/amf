# Item Creation improvement tracker

Updated: 27 October 2026. Evidence: [audit](item_creation_audit_2026-10-27.md), [catalogue specification](item_creation_catalogue_specification_2026-10-27.md).

| Improvement | Status | Scope / next action |
| --- | --- | --- |
| Shared suffix allocation | Implemented and tested | Global three-character reservations and six-character alphanumeric identifiers. |
| Complete preview and engineering review | Implemented and tested | One read-only plan, exact recipe differences/parent impact, protected review history and dependency-aware stale-review rejection. Reviewed requests/history cannot be deleted through document APIs. |
| Explicit compatibility rules | Implemented and tested | Individual standard body/syringe selections, reference/volume/material identity checks, head-type/LV/HV rules; disabled-product-only combinations excluded. New families/custom compatibility require a reviewed rule update. |
| Complete raw-material BOMs | Implemented and tested | Explicit stock, positive quantity and current stock UOM for every newly machined component; no guessed stock choice/consumption. Five Items/five BOMs for a complete new head. |
| Guided form and accurate previews | Implemented and tested | Guided sections, full-width Product Configurations table, code-based Body (`5_1___`) and Syringe (`70X___`, X a digit 1–9 or a letter) selectors, variant chooser, complete shared plan, readable stock names, safe rendering, stale-response handling and live errors. |
| Simpler execution and performance | Implemented and tested | Pure shared recipes, bulk/cache-limited dependency reads, pinned BOM revisions and request-owned transactions without monkey-patching database methods. |
| Formal application-wide permission policy | Proposed | Retain existing authorized roles for this work; audit other helpers and define broader role separation separately. |
| Structured engineering specifications | Partly improved; further work proposed | Safe ordinary/custom-name handling, compound channel descriptions and contextual material names implemented. Dedicated geometry/material fields remain proposed. |
| Versioned engineering recipe templates | Foundation implemented; further work proposed | Versioned code rules and recorded per-request approval implemented. A maintained engineering-template DocType and its own release workflow remain proposed. |
| Traceability and lifecycle | Implemented and tested | Immutable result child rows, Item/BOM reverse links and a permission-filtered results report. Reasoned cancellation retains generated records/reservations; one active amendment per predecessor reuses its head family and requires fresh review. Retirement stays a separate engineering decision, as requested. |
| Company-wide defaults and costing policy | Partly implemented | Explicit company/warehouse validation and removal of guessed component valuation seeds implemented. Broader settings/costing policy remain separate. |
| Historical catalogue corrections | Proposed | Review the 37 Product/head disagreements and engineering exceptions; no automatic data repair. |
| Platform migration | Proposed | Separate migration project for the patched v12 application and its dependencies. |

Implementation and user instructions: [engineering workflow record](item_creation_engineering_workflow_2026-10-27.md).

Traceability extension: [result links and lifecycle policy](item_creation_traceability_2026-10-27.md). AMF `0.7.3` adds a registered additive migration and indexes only existing recorded execution JSON. Ordinary approval hashes and recipe execution remain compatible. A real rollback-only case created seven Items/seven submitted BOMs, retained them on cancellation, and submitted two replacement BOMs through a fresh amendment review in about 12 seconds. Direct result edits/deletion and duplicate active amendments were rejected; old/new revision searches and repeated result backfill passed.

Traceability release verification: 132 focused/regression Python tests, 15 read-only site regression tests and the expanded form/reverse-link Node tests passed. Live digit/letter syringe queries and Guest denials passed in a read-only transaction. An injected failure after writing all seven result links propagated and rolled back Items, BOMs, requests, result rows, reservations and QR files.

AMF `0.7.4` selector clarification: the third character must be 1–9 or a letter, excluding `0`. Live read-only checks verified `700025` is excluded and `709000`/`70E000` are included; 34 focused Python tests and the form tests passed. This code-format filter is separate from the compatibility matrix. The omission of U syringes `704000`/`709000` was inferred from disabled historical Products, not a demonstrated physical incompatibility; extending that matrix is pending the user's engineering clarification. No compatibility rule was changed by this selector correction.

Verification: 121 focused/regression Python tests and 15 initialized-site Work Order/report tests passed; guided-form Node tests passed. Real rollback-only lifecycle checks cover approval, automatic submission, replacements, original parent-link preservation, changed request/dependency rejection, failure propagation, immutable review history and QR/registry cleanup. The largest standard selection created 27 Items/27 submitted BOMs in about 35 seconds; a live read-only seven-Item preview took about 0.3 seconds initially (about 0.02 seconds with warm caches).

Release verification: the registered `0.7.2` migration was executed twice directly on `site1.local`. Both passes verified all three schemas, the full-width table and alphanumeric Work Order metadata; Item, BOM and Item Creation counts stayed unchanged. Its Patch Log entry remains pending for the next standard migration. The 121 Python tests, 15 read-only site tests and guided-form checks were rerun successfully before commit.

The broader stock-repair test group has two pre-existing failures: the manufacture wrapper's expected 2024 date differs from the unchanged 2026 default, and the serialized wrapper's expected dry-run flag differs from its unchanged default. Both failures were reproduced with the baseline `custom_try` helper restored in memory. They are outside this update; the full financial Stock Entry fixture suite was not run on the business site.

Deployment: AMF `0.7.3` registers `amf.patches.v12_0.install_item_creation_traceability` after the existing `0.7.2` workflow patch. It reloads the four child/parent schemas, installs the results report, indexes recorded execution results and clears metadata/script caches. It performs no historical Item/BOM repair or reservation backfill. Targeted schema/report migration was verified twice on `site1.local`; no broad migration ran. Deploy Python/form code together with the installation's normal web/worker reload and browser refresh. No pending 4D BOMs or paused cost writers were activated.
