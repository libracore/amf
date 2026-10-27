# Item Creation improvement tracker

Updated: 27 October 2026. Evidence: [audit](item_creation_audit_2026-10-27.md), [catalogue specification](item_creation_catalogue_specification_2026-10-27.md).

| Improvement | Status | Scope / next action |
| --- | --- | --- |
| Shared suffix allocation | Implemented and tested | Global three-character reservations and six-character alphanumeric identifiers. |
| Complete preview and engineering review | Implemented and tested | One read-only plan, exact recipe differences/parent impact, protected review history and dependency-aware stale-review rejection. Reviewed requests/history cannot be deleted through document APIs. |
| Explicit compatibility rules | Implemented and tested | Individual standard body/syringe selections, reference/volume/material identity checks, head-type/LV/HV rules; disabled-product-only combinations excluded. New families/custom compatibility require a reviewed rule update. |
| Complete raw-material BOMs | Implemented and tested | Explicit stock, positive quantity and current stock UOM for every newly machined component; no guessed stock choice/consumption. Five Items/five BOMs for a complete new head. |
| Guided form and accurate previews | Implemented and tested | Guided sections, full-width Product Configurations table, code-based Body (`5_1___`) and Syringe (`70____`) selectors, variant chooser, complete shared plan, readable stock names, safe rendering, stale-response handling and live errors. |
| Simpler execution and performance | Implemented and tested | Pure shared recipes, bulk/cache-limited dependency reads, pinned BOM revisions and request-owned transactions without monkey-patching database methods. |
| Formal application-wide permission policy | Proposed | Retain existing authorized roles for this work; audit other helpers and define broader role separation separately. |
| Structured engineering specifications | Partly improved; further work proposed | Safe ordinary/custom-name handling, compound channel descriptions and contextual material names implemented. Dedicated geometry/material fields remain proposed. |
| Versioned engineering recipe templates | Foundation implemented; further work proposed | Versioned code rules and recorded per-request approval implemented. A maintained engineering-template DocType and its own release workflow remain proposed. |
| Traceability and lifecycle | Partly implemented | Protected review snapshots and structured Item/BOM results implemented. Searchable reverse links/result child tables and broader amendment/cancellation policy remain proposed. |
| Company-wide defaults and costing policy | Partly implemented | Explicit company/warehouse validation and removal of guessed component valuation seeds implemented. Broader settings/costing policy remain separate. |
| Historical catalogue corrections | Proposed | Review the 37 Product/head disagreements and engineering exceptions; no automatic data repair. |
| Platform migration | Proposed | Separate migration project for the patched v12 application and its dependencies. |

Implementation and user instructions: [engineering workflow record](item_creation_engineering_workflow_2026-10-27.md).

Verification: 121 focused/regression Python tests and 15 initialized-site Work Order/report tests passed; guided-form Node tests passed. Real rollback-only lifecycle checks cover approval, automatic submission, replacements, original parent-link preservation, changed request/dependency rejection, failure propagation, immutable review history and QR/registry cleanup. The largest standard selection created 27 Items/27 submitted BOMs in about 35 seconds; a live read-only seven-Item preview took about 0.3 seconds initially (about 0.02 seconds with warm caches).

Release verification: the registered `0.7.2` migration was executed twice directly on `site1.local`. Both passes verified all three schemas, the full-width table and alphanumeric Work Order metadata; Item, BOM and Item Creation counts stayed unchanged. Its Patch Log entry remains pending for the next standard migration. The 121 Python tests, 15 read-only site tests and guided-form checks were rerun successfully before commit.

The broader stock-repair test group has two pre-existing failures: the manufacture wrapper's expected 2024 date differs from the unchanged 2026 default, and the serialized wrapper's expected dry-run flag differs from its unchanged default. Both failures were reproduced with the baseline `custom_try` helper restored in memory. They are outside this update; the full financial Stock Entry fixture suite was not run on the business site.

Deployment: included in AMF `0.7.2`, with registered migration `amf.patches.v12_0.install_item_creation_engineering_workflow`. It reloads the child tables and Item Creation form, including the full-width configuration table, and updates the Work Order fields for alphanumeric codes. It performs no historical Item/BOM repair or reservation backfill. The three affected schemas were already reloaded on `site1.local` without broad migration. Web/worker process reload and browser refresh must deploy the Python/form changes together. No pending 4D BOMs or paused cost writers were activated.
