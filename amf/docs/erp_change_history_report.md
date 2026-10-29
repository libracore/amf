# AMF ERP Release Notes

Generated on: 2026-10-29

Change history through: 2026-10-29

Latest reviewed commit: `6728986`

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

Latest release: `v2026.10.3`

Release status: Ready for validation

Release audience: AMF ERP users, department leads, management, operations, finance, logistics, quality, sales and support teams.

## Purpose

This document is the business-facing release notes and change history for the AMF ERP custom app.

It summarizes the main ERP changes developed in the AMF custom app from the beginning of the recorded development history to 2026-10-29. The report is based on the `apps/amf` git history, which starts on 2022-09-19, and on the current AMF app structure, including custom DocTypes, reports, pages, hooks and documentation.

This is intentionally not a technical commit-by-commit changelog. It records committed changes in `apps/amf` as a release communication document for the main modifications, novelties and functional areas added over time. Standard Frappe and ERPNext framework changes are not listed unless they were reflected in AMF custom development.

## Version Management

### Version Format

Use a business release version for company communication:

- Format: `vYYYY.MM.N`
- Example: `v2026.07.1`
- `YYYY` is the release year.
- `MM` is the release month.
- `N` is the sequence number for that month.

Use the next sequence number when several communication-worthy releases are published in the same month. Use the next month number when a new monthly release is published.

Historical development milestones already recorded in the project, such as `v0.4.0`, `v0.6.0`, `v0.6.1`, `v0.6.5` and `v0.7.0`, are preserved in the release history where they exist.

### Release States

- Draft: release notes are being prepared.
- Ready for validation: release notes are complete and waiting for business or technical review.
- Published: release is available in the live system and can be communicated to the company.
- Superseded: a newer release has replaced this release as the latest company communication.

### Current Version Register

| Release | Status | Period | Main Focus |
| --- | --- | --- | --- |
| `v2026.10.3` | Ready for validation, latest | 2026 Q4, Oct 26-29 | Reviewed Item Creation and lifecycle, RVM/LV/HV variants, staged FFTest, BOM cost analysis, private exports, inventory lifecycle and Acoustic Mixer setup. |
| `v2026.10.2` | Superseded | 2026 Q4, Oct 13-26 | Monthly inventory checks, Purchase Receipt GL precision, customer-description cleanup, Sales Order letterhead, guarded stock corrections and 4D interface variants. |
| `v2026.10.1` | Superseded | 2026 Q4, Oct 5-12 | Issue classification and history, FFTest P202 serial flow, Tool Maintenance subgroups, timer alerts, selected BOM repricing and MAT.1021 batch traceability. |
| `v2026.09.2` | Superseded | 2026 Q3 | Standard print format deployment, AMF Issue Test to Issue traceability, and AMF Control Center Premium software offerings. |
| `v2026.09.1` | Superseded | 2026 Q3 | Organizational Modification Request governance, Sales Order and commercial-invoice printing, focused Weekly Operations KPIs and a guarded RVM.3300 stock-history correction. |
| `v2026.08.4` | Superseded | 2026 Q3 | Governed Product and purchased-item descriptions, Loan Order printing, PostFinance import compatibility, custom-item R&D review controls and process-owned Issue classification. |
| `v2026.08.3` | Superseded | 2026 Q3 | Loan Order commercial settlement, DHL Express shipment creation, Delivery Note commercial invoice and packaging formats, Weekly Operations Report slides and legacy weekly email cleanup. |
| `v2026.08.2` | Superseded | 2026 Q3 | Recursive default BOM versioning, 4B/4C BOM family-coherence repairs, Issue timeline/resolution layout refinements and receipt batch tracking for item `70E000`. |
| `v2026.08.1` | Superseded | 2026 Q3 | Tool-only maintenance planning, maintenance history, preventive maintenance dashboard, automatic Item maintenance summaries, P202-O BOM creation and receipt batch tracking for item `70E000`. |
| `v2026.07.1` | Published | 2026 Q3 | Procurement cash forecast, global inventory dashboard, issue management, item dashboards, component drawing register, bank reconciliation automation and serial-number tools. |
| `v2026.06.0` | Superseded | 2026 Q2 | Loan Orders, landed cost behavior, work order automation, KPI dashboards, procurement tools and AI-assisted reporting. |
| `v2026.03.0` | Superseded | 2026 Q1 | Swiss VAT handling, customs mapping, planning quantities, batch quantity retrieval and costing support. |
| `v0.7.0` | Superseded | 2025 Q4 | Production Tracking, Timer Production, automatic Quality Inspections, drawing-based QA and HS Code support. |
| `v0.6.5` | Superseded | 2025 Q2 | Satisfaction scoring, customer reporting, planning and rating reports, leave balances and ERPNext-related Stock Entry fixes. |
| `v0.6.0` / `v0.6.1` | Superseded | 2025 Q1 | Safety Stock, Work Order creation, labels, drawing matching, customer surveys and Global Quality Inspection. |
| `v0.4.0` | Superseded | 2024 Q3 | Master CRM, Sales Actions, campaign lists, Gravity Forms, Brevo integration and CRM analytics. |
| Foundation releases | Superseded | 2022-2024 | Core reporting, planning, labels, QR codes, inventory visibility, logistics, purchasing and CRM foundations. |

## Latest Release: `v2026.10.3`

Release date: 2026-10-29

Release status: Ready for validation

Committed change window: 2026-10-26 to 2026-10-29

Reviewed commit range: `fcad8a3..6728986` (17 new commits after the previous report cutoff).

AMF app version at reviewed commit: `0.7.12`

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

### Summary

This release makes Item Creation a reviewed engineering workflow. Users choose individual configurations, inspect the complete Item/BOM plan, record engineering review and submit the approved definition in one transaction. The workflow supports existing heads, Product-only requests, selectable seat pins and controlled Product code/reference overrides, with permanent identifier reservations and searchable execution history.

Supported configurations now include the approved LV U syringes, explicit HV/HD choices, RVM Mini base/RS485/CAN and additional RVM body variants. New NM/TH Products use `421xxx` and new P201-O RS485 Products use `422xxx`; matching historical Products retain their existing codes. A separate FFTest module adds serial-aware staged production for `4D` products, including the received-stock path for purchased `5D0000`.

Costing teams gain BOM Cost Breakdown views, while private report inputs and exports move to permission-controlled database records. Monthly inventory checks gain manager cancellation/deletion and one-time installation setup. An Acoustic Mixer migration creates or validates two dedicated Products with CHF 2,500 BOM unit costs. These notes describe committed code and migrations; deployment and live workflow validation remain separate release steps.

### Highlights

- Added a complete Item/BOM preview, recorded engineering review and dependency checks before Item Creation submission. Changed inputs, dependencies or compatibility rules require a fresh review.
- Added shared head/component suffix reservations, independent Product codes, collision-aware suggestions and reviewed Product Reference overrides. Existing heads can reuse their actual components or supply Product-only requests.
- Expanded configuration selection with explicit LV/HV/HD guidance, approved U syringes, selectable seat pins, RVM Mini interfaces and RVM body variants; corrected the new NM/TH and RS485 prefixes.
- Added protected execution result rows, Item/BOM reverse searches and reasoned request cancellation/amendment. Cancelling a request retains its generated Items, BOMs and identifier reservations.
- Added an opt-in FFTest `4D` module with preview, serial/batch checks, stage reuse and rollback across stock stages, plus a local manual test helper.
- Added BOM Cost Breakdown analysis covering planned/actual Work Order costs, averages, recursive BOM reconciliation and latest-purchase costing with optional historical process costs.
- Added private database artifacts and authenticated exports, with invoice rates separated by currency and private DHL text attachments.
- Added manager lifecycle controls for monthly inventory checks and one-time setup, plus a guarded Acoustic Mixer Product/BOM migration targeting CHF 2,500 unit costs.

### Change Notes

| Area | Change | Brief Explanation |
| --- | --- | --- |
| Item Creation review | One complete plan approved before execution. | Users select exact configurations, raw-stock Items and consumption quantities, then inspect new/reused Items, BOM differences and affected parents. A System Manager records the plan and review notes; submission rechecks dependencies and creates/submits the approved BOMs in order. Changed inputs or dependencies invalidate approval while preserving review history. |
| Numbering and existing heads | Reserved component families and flexible Product identities. | New heads/components share a permanently reserved suffix, with decimal then alphanumeric allocation that respects retired codes. Existing heads may reuse independently numbered components, and Create Products Only pins their current revisions. Product codes can be suggested or overridden within the correct prefix; a unique reviewed Product Reference can resolve a conflict without renaming its existing owner. |
| Configuration selection | More explicit hardware choices and compatibility checks. | The chooser displays LV/HV/HD requirements, supports the approved U syringes on standard LV bodies and lets users select seat pins and exact raw stock. RVM choices include Mini base/RS485/CAN and supported enabled body variants. New NM/TH and RS485 Products use `421xxx` and `422xxx`, while historical matches and the `430xxx` namespace for body `531000` are preserved. |
| Creation traceability | Searchable results, cancellation and amendments. | Protected result rows record each Item action and selected/replaced BOM revision, with reverse links from Item/BOM and a permission-filtered Item Creation Results report. System Managers can cancel a request with a reason, retaining generated records and reservations. One active amendment per predecessor can proceed through a fresh engineering review. |
| Quotations and downstream tools | Configuration matching and alphanumeric codes aligned. | Quotation lookup checks the actual body/head/syringe composition of a submitted active BOM and shares the RVM reference/prefix rules. Batch setup, drawings, machining/yield reports and Work Order calculations recognize the extended alphanumeric identifiers. Arbitrary custom-reference Products remain directly selectable by Item Code where automatic discovery does not apply. |
| FFTest `4D` production | Serial-aware staged flow in a separate module. | The flow reads the product's linked BOMs, reuses an available intermediate serial or manufactures the necessary stages, and returns the final-product Stock Entry. Purchased `5D0000` must already be received with an available serial; it is consumed into `5D1___` rather than manufactured. Preview, batch/warehouse checks and rollback protect the sequence; the production caller must explicitly select the new module to activate it. |
| BOM costing | Multiple source-linked analysis views added. | BOM Cost Breakdown compares planned and actual Work Order costs, averages by reference and excluded observations, and expands recorded child BOM links with reconciliation differences. Latest Purchase views calculate current BOM trees from qualifying receipts, optionally adding historical process evidence. These report views analyze costs without applying a repricing proposal. |
| Private data and exports | Database-backed artifacts and restricted downloads. | Reviewed BOM inputs and generated reports are stored as immutable, checksum-verified AMF Data Artifacts included in database backups. Downloads require System Manager and document read permission; invoice-rate exports also require invoice read access and keep currencies separate. DHL text exports become private Delivery Note attachments requiring write access to the note. |
| Monthly inventory lifecycle | Manager cancellation/deletion and one-time setup. | Stock/System Managers can cancel a check, close its assignment and release references, or delete it while Frappe retains its Deleted Document record. Linked stock vouchers remain intact with their checklist backlink cleared and an audit comment. Installation now uses after-install setup or a versioned patch, preserving saved settings instead of rerunning feature setup on every migration. |
| Acoustic Mixer | Dedicated Products and CHF 2,500 BOM cost targets. | A guarded migration creates or validates `45D040-AM` and `46F055-AM`, based on pinned source BOMs, plus dedicated non-stock allocation Items `GX.RD-1000`/`GX.RD-1001`. Refreshed material costs plus each allocation yield CHF 2,500 per unit; conflicting existing records stop migration. Later component-cost changes require allocation review to retain that target; no stock or Item Price transactions are created by the patch. |

### User Impact

- Item Creation users must save, refresh the complete plan and obtain engineering review before submission. Earlier draft approvals need a fresh preview/review under the current rules; a preview or code suggestion alone does not execute creation.
- Engineers can reuse an existing head through Create Products Only, select exact pins/raw stock and resolve Product code/reference conflicts within the reviewed plan. Existing recipes that differ require an explicit replacement proposal.
- Users can inspect Item Creation History from an Item or BOM. Request cancellation withdraws the request but retains its generated masters and BOMs; further engineering changes use an amendment and fresh review.
- FFTest operators need the caller configured for the new module before using the staged `4D` flow. Purchased `5D0000` requires a received serial; the manual helper uses the browser's ERP session to preview or launch the selected test page.
- Stock Managers can cancel or delete monthly checks without reversing their stock corrections. The scheduler respects a deleted month's check; a replacement requires an explicit Generate Current Month action.
- Costing and finance users can compare cost sources and request authorized artifact downloads. The Acoustic Mixer CHF 2,500 value is a BOM cost target, distinct from a selling price.

### Validation Notes

This report update was checked against the committed range above. The following are recommended release checks, not new live tests performed while updating this document:

- Test a new head family and an existing-head Product-only request: review raw stock/UOMs, pin selection, exact child revisions and replacement differences, then confirm approval becomes stale when inputs or dependencies change.
- Verify code collision/retirement handling, a reviewed reference override and the final RVM prefixes: `421` for NM/TH, `422` for P201-O RS485 and `4D0/4D1/4D2` for Mini. Confirm historical matching Products retain their identities and resolve correctly in Quotations.
- Check Item Creation result searches, request cancellation and a single active amendment, ensuring generated masters, submitted BOMs and reservations remain traceable.
- In an isolated stock test, preview the `4D` flow for a received `5D0000` serial and an existing intermediate serial; verify batches, Work Order scope and rollback after a later-stage failure. Confirm the intended caller/module is selected before any real posting.
- Compare BOM Cost Breakdown totals with their BOM, receipt and Work Order sources. Test authorized and denied artifact/rate downloads, currency separation and private DHL attachment access.
- Exercise monthly-check cancellation/deletion and a deliberate replacement, verifying assignments close and stock vouchers remain valid. Confirm repeated installation preserves existing settings and does not generate checks or notifications.
- After applying the Acoustic Mixer patch, verify both default BOMs and allocation Items against the pinned sources and CHF 2,500 unit-cost target. Apply registered feature patches and the normal process/browser reloads before business validation.

## Executive Summary

Since the beginning of development, the AMF ERP has evolved from a custom reporting and page layer into a broader operational system covering manufacturing, planning, inventory, purchasing, logistics, sales, CRM, quality, finance support and management reporting.

The main evolution areas are:

- Production planning, Work Order automation and manufacturing follow-up.
- Tool maintenance planning, preventive status and intervention history across Tool subgroups.
- Reviewed Item/BOM creation with configuration selection, identifier reservations, execution history and amendments, plus governed descriptions, purchased-part classification and custom-item review controls.
- QR code, barcode, label and production sticker generation.
- Inventory visibility, safety stock, stock forecasting, monthly physical checks and replenishment support.
- Purchasing and procurement follow-up.
- Delivery Note, shipping, DHL tracking, DHL shipment creation and logistics tools.
- CRM, contact management, sales actions, campaign lists and external form/email integrations.
- Quality inspection, process-owned Issue classification and party history, organizational change control, customer feedback and satisfaction surveys.
- Finance and compliance support such as VAT, HS codes, customs values, landed cost, Purchase Receipt GL precision, custom ledgers and PostFinance reconciliation.
- Operational dashboards, KPI reporting and AI-assisted reporting.
- Weekly operations slide reporting with controlled production, delivery, QC and shipping scope.
- Customer-facing Sales Order, Loan Order, Delivery Note and commercial-invoice document formats.
- Source-linked BOM cost analysis, reviewed material repricing, receipt batch tracing and FFTest serial/stock-flow controls.
- Operator-session timer alerts with linked ToDos and optional email.
- User interface improvements, document hooks, automation scripts and administrative utilities.

## Release History

### 2026 - Advanced Planning, Finance, Compliance, Dashboards And AI Reporting

#### `v2026.10.3` - 2026 Q4, Oct 26-29 - Latest

- Item Creation releases `0.7.2` through `0.7.12` introduced complete reviewed plans, protected engineering decisions and submission that rebuilds the approved dependencies before creating Items and submitting BOMs. Raw-stock selection, consumption quantities, exact child revisions and replacement differences are visible before approval.
- Head/component suffixes now use shared permanent reservations that respect occupied, disabled and retired identifiers, with decimal and alphanumeric allocation. Products may have independent codes while their references/BOMs identify the selected head; related batch, drawing, Work Order and manufacturing-report tools accept those alphanumeric codes.
- Existing heads can reuse their actual independently numbered components, or serve Create Products Only requests. Suggestions reuse matching enabled Products where possible; optional Product code and reference overrides participate in validation and fresh review rather than changing historical owners.
- Configuration selection now shows individual LV/HV/HD choices and head requirements, permits the approved U syringes on standard LV bodies, filters syringe identifiers correctly, and supports selectable seat pins. New plug/seat raw-stock quantities are editable with their current stock UOM displayed.
- RVM selection expanded to Mini base/RS485/CAN and supported enabled body variants. The final numbering correction gives new NM/TH Products `421xxx` and new P201-O RS485 Products `422xxx`, retains Mini `4D0/4D1/4D2`, and preserves historical matches under their existing codes.
- Quotation resolution now shares the RVM references/prefixes and verifies the actual body/head/syringe tuple in a valid submitted active BOM. A mismatching catalogue result is reported for engineering review.
- Item Creation Result records, the Item Creation Results report and reverse Item/BOM history links provide protected execution traceability. Reasoned cancellation retains generated records and reservations; amendments require a fresh review and are limited to one active successor per predecessor.
- A separate FFTest module adds staged, serial-aware production for `4D` products with read-only preview, batch/warehouse checks, intermediate reuse and rollback across stock stages. Purchased `5D0000` requires an existing received serial and skips raw-body manufacture; other manufactured raw variants retain their necessary first stage.
- A loopback manual FFTest helper builds preview/test-page URLs and receives results through the logged-in browser workflow. Activation requires an explicit caller change to the new module; the committed addition does not itself switch the existing production page.
- BOM Cost Breakdown adds planned/actual, average, excluded-record, recursive and latest-purchase views, with optional historical process costing, source references and reconciliation differences. Companion audit/proposal tools cover material readiness, disabled dependencies and selected BOM cost changes.
- AMF Data Artifact stores private report inputs/outputs as immutable, checksum-verified database records. A migration imports the reviewed site-specific BOM inputs before repricing; authenticated downloads, currency-separated invoice-rate exports and private DHL text attachments replace public runtime export files.
- Monthly Inventory Checks gain manager cancellation and deletion, assignment closure and preservation of stock correction vouchers. Cancelled checks release references; the scheduler does not automatically recreate a deleted current-month check.
- Monthly inventory initialization moves from a recurring migration hook to after-install setup and a once-only versioned patch. Missing defaults are initialized without requiring the operating company/warehouse/assignee to exist yet; generation still requires valid runtime settings.
- A guarded Acoustic Mixer migration creates or validates `45D040-AM` and `46F055-AM` with pinned source recipes and dedicated non-stock allocations reaching CHF 2,500 BOM unit costs. Existing conflicts stop execution and the patch creates no stock or selling-price transactions.
- Focused tests and committed audit records cover creation/review/lifecycle behavior, configuration variants, FFTest serial handling, private artifacts, BOM costing, inventory lifecycle and Acoustic Mixer migration. Their recorded verification is distinct from deployment validation of this report.

#### `v2026.10.2` - 2026 Q4, Oct 13-26

- Monthly Inventory Settings and Check DocTypes added for ten randomly selected references per company and month. Eligible Item Groups, specific exclusions and active Production warehouses are configurable; automatic generation is disabled until reviewed and enabled.
- Each check records a selection audit and warehouse-level stock/rate snapshots, assigns a counter by ToDo/email, and requires explicit counts and confirmations. Stale snapshots force refresh and recount; simultaneous or repeated generation cannot create duplicate monthly checks.
- Linked draft Stock Reconciliations support ordinary-item differences without direct ledger writes. Batch/serial items use manual identity-aware vouchers, and final verification requires submitted stock effects and matching balances; cancellation of a correction reopens the check.
- Purchase Receipt GL precision guard now filters entries that round to zero after merging, including on returns and later stock-ledger reposts, while preserving postable totals and accounting dimensions. The separately discovered MAT.1011 historical valuation discrepancy is not changed by this fix.
- Customer-facing Item descriptions have internal evidence labels and HTML comments removed by migration. Purchased-item description generation now keeps those markers out and preserves existing clean catalog facts.
- Sales Order confirmation format now renders the selected default Letter Head without its prior embedded header, avoiding double branding.
- Site-specific migration for item `110137` attaches the original stock movements to batch `CTD694 AMF` and removes a duplicate 30-unit balance after asserting the source documents and ledger rows.
- Site-specific `OF-02883` migration changes the recorded 20-unit material consumption from `520000` to `520006`, adds a compensating Repack and clears the extra `520006` stock balance; it validates the original Work Order and ledger state before applying.
- `4D` interface migration creates `4D1` RS485 and `4D2` CAN Item variants for eligible sources, copies selling prices and attachments, and creates corresponding BOMs with the correct interface body. Six BOMs stay pending because their source valve heads are disabled; existing matching records are preserved.
- Focused tests added for GL precision, description cleanup, monthly inventory selection/locking/reconciliation, and `4D` variant migration. An FFTest diagnostic-page backup was committed for recovery; it does not change the active flow.

#### `v2026.10.1` - 2026 Q4, Oct 5-12

- `Other` Issue Type workflow added on Issue and AMF Issue Test. A user names a new reusable type and assigns an enabled accountable process; the saved Issue receives that process and its owners.
- AMF Issue Test intake now displays customer or supplier history, including classification, status, affected Items and related documents. Linked legacy Issues are grouped with their source test records.
- Generated legacy Issues now copy customer, supplier, contact and reporter details from AMF Issue Test, and a setup task repairs those fields for existing linked cases.
- FFTest P202 stock flow now maps a finished `5D1000` serial to its existing numeric `5D0000` source serial and validates serial location, Work Order capacity and batch inputs before stock movement.
- A read-only FFTest preview endpoint and diagnostic Web Page installer show planned Stock Entries and validation results. The real flow remains a separate, permission-checked action.
- Extended Tool Maintenance to Item Group `Tool` and all its descendants, including Assembly tool, Dimensional Measuring tool, Electrical Testing Instruments, Machinery, Machining tool and Pressure/flow Testing Instruments.
- The dashboard, Item maintenance sections, plan/log Item selectors, server validation, workbook matching and daily summaries now use the same current Item Group hierarchy; new and nested subgroups are included automatically.
- Creating or moving a subgroup refreshes maintenance summaries for its affected Items. Items and subgroups with maintenance records can move within Tool; moving them outside Tool requires those records to be removed or reassigned first.
- Corrected the maintenance Details query so intervention history and plan procedures load correctly on ERPNext v12.
- Timer Production now checks active sessions every 15 minutes and records a single alert after four hours. It creates an operator ToDo, sends email to the operator or configured fallback address, and closes its alert/ToDo when the session ends.
- A reviewed migration was added for 61 selected current default BOMs and their qualifying made-child route. Material rates use eligible submitted Purchase Receipts or child BOM costs; changed BOM rows, totals and explosion quantities are verified after update.
- The BOM migration requires the saved proposal to match current Items, BOMs and receipts, and requires ERPNext and AMF automatic cost writers to be paused before it writes.
- MAT.1021 migration patches preserve the `PREC-02877` purchase receipt batch and separate the original `STE-14142` stock receipt batch from its later `STE-18224` subcontractor transfer, with exact source and ledger assertions.
- Automated tests added or extended for Issue integration and history, FFTest serial mapping, Tool Maintenance group hierarchy and timer alert behavior.

#### `v2026.09.2` - 2026 Q3

- Sales Order and Organizational Modification Request print formats were moved into standard Frappe Print Format records, replacing the earlier installer and after-migrate setup hooks. This keeps the approved formats in the app's normal migration path.
- Sales Order branding was refined to use the default letterhead logo, with its stylesheet source retained in the repository. The OMR print stylesheet was also retained and given explicit page margins for more reliable PDF output.
- New AMF Issue Test records now create a linked legacy Issue, carrying key subject, type, urgency and impact values so existing Issue-based links remain usable and traceable.
- Four AMF Control Center Premium software Items were added for included, complimentary, discounted and standard license offers, with CHF prices of 0, 0, 490 and 990 in the 2026 S2 selling price list.

#### `v2026.09.1` - 2026 Q3

- Organizational Modification Request and Organizational Modification Action DocTypes added for controlled C2 significant and C3 major changes.
- OMR preparation covers the proposed change, motivation, change types, impacted domains, failure risks, preventive controls, training/documentation needs and effectiveness criteria.
- Named implementation actions now carry responsible users, deadlines, completion flags and completion dates; all actions must be complete before implementation can be recorded.
- Submission requires an approval decision plus change-responsible and Quality signatures, while C3 changes also require General Management approval.
- Submitted OMRs support actual implementation, effectiveness review and Quality closure, with automatic statuses and mandatory additional actions when a change is not effective.
- French controlled print format `AMF.0053 - Organizational Modification Request` added with a dedicated PDF button and direct access from the AMF module.
- Sales Order custom fields and property fixtures synchronized so customer PO, AMF contact, shipping, order-type, remaining-quantity, display and payment-schedule configuration migrate consistently.
- `Standard Branding AMF 2026` Sales Order format added as the default, presenting customer/order details, delivery dates, remaining quantities, pricing, totals, terms and commercial messages; its deployment was subsequently moved to a standard Frappe Print Format record in `v2026.09.2`.
- Delivery Note commercial-invoice letterhead changed from repeatable-header behavior to a single document letterhead with controlled first-page spacing.
- Weekly Operations output-versus-plan restricted to `Production` Sales Orders; `GX` items excluded from On Time Delivery and incoming-QC backlog calculations.
- Weekly Operations scheduled generation no longer sends email automatically; generated slides remain available for deliberate manual distribution.
- Guarded RVM.3300 correction added for duplicate receipt `PREC-02960`, including downstream batch reassignment, a 100/67-unit split between valid receipts, obsolete-batch removal and final stock verification.
- Tests added for OMR validation, approvals, implementation and closure, with Weekly Operations tests updated for Production-only metrics, `GX` exclusions and manual email distribution.

#### `v2026.08.4` - 2026 Q3

- Product Item descriptions standardized into customer-facing, customs and internal production layers derived from product configuration and the preferred active submitted BOM.
- Description generation covers established pump and valve families, special products and Valve Heads, validates output length/content and avoids creating a production basis for Products without a BOM.
- Purchased-item description migration added for active physical items with submitted purchase history, combining Item master data, supplier part numbers, purchase evidence and reviewed supplier/manufacturer references.
- Existing production notes are preserved in the generated internal description, non-physical/service placeholders are excluded and a review CSV records the generated results and evidence basis.
- Stable `Part` child groups added for fasteners, bearings and bushings, springs, seals, fluidic components, motion components, sensors, electrical/electronic parts, thermal components and mechanical parts.
- Loan Order print format added with borrower/contact details, loan period, equipment descriptions, optional declared values, purpose and terms; final wording identifies a separately shared and signed Loan Agreement.
- Loan Order print preparation updated to use the standard Item customer description and to present submitted orders as issued customer copies.
- PostFinance reconciliation updated for both multi-account and single-account CSV layouts, with strict IBAN/currency consistency checks for supported accounts.
- Sales and Purchase Invoice references with an omitted first dash are normalized for invoice lookup and Payment Entry reference extraction.
- `Custom Item` field and synchronization added so custom Valve Heads flag Products that use them in active submitted default BOMs.
- Quotations and Sales Orders now show a controlled R&D review warning for custom items, suppressing duplicate warnings until the affected item set changes.
- `AMF Issue Process` DocType added to govern process codes, scope, enabled status and primary/secondary accountable owners.
- Canonical active Issue Types and automatic routing added across quality, marketing, sales/service, procurement, manufacturing, information systems, logistics, maintenance and R&D.
- Subject-based Issue Type suggestions added to Issue and AMF Issue Test using governed multilingual terms and sufficiently confirmed user classifications; users retain final control over application.
- Issue outcomes are separated from problem classifications, legacy types remain available for history but inactive for new selection, and the Issue form layout was refined for product, batch, repair and warranty information.
- Automated tests added for purchased-item descriptions, Part classification, custom-item propagation/warnings and Issue classification/suggestion behavior.

#### `v2026.08.3` - 2026 Q3

- Loan Order commercial settlement added for submitted customer Loan Orders after equipment has been loaned out.
- Customer billing decisions now support `Spare Parts Only` and `Full Product Purchase`, with draft Sales Invoice creation from the Loan Order.
- Spare-parts-only settlement can dismantle loaned products through a value-neutral Repack, invoice the spare components and prepare a return Delivery Note for the remaining components.
- Full-product-purchase settlement can create the settlement Delivery Note and invoice the outstanding customer-owned items without rebuilding the transaction manually.
- Loan Order settlement documents now carry backlinks across Sales Invoice, Delivery Note, Stock Entry and child rows for audit traceability.
- DHL Express Shipment workflow added for submitted non-return Delivery Notes whose carrier is DHL.
- DHL draft building, transport product lookup, MyDHL validation and confirmation-gated AWB creation added with payload fingerprints and environment tracking.
- DHL Shipment audit fields added for validation status, creation status, message reference, tracking URL, piece tracking numbers, payload fingerprints and returned documents.
- MyDHL Settings expanded with separate shipment API credentials, endpoint selection, shipper account and fallback shipper contact values.
- Delivery Note commercial invoice and 2026 packaging print formats added, with installer patches and Delivery Note print-button routing.
- Weekly Operations Report DocType added for generated PDF/PNG production and supply slides, including stored JSON diagnostics.
- Weekly operations data collection added for delivery performance, overdue deliveries, machining queue, open Work Orders, incoming QC backlog and shipping status.
- Operations KPI Report Settings expanded with weekly slide configuration, manual generation, scheduled defaults and optional weekly email distribution.
- Legacy weekly open-issue and standard-item availability email reports disabled to avoid duplicate uncontrolled report emails.
- 2026 packaging branding layout refined to fit item details, images and serial tables more compactly.
- Tests added for Loan Order settlement, DHL shipment payload/creation behavior, weekly operations reporting and disabled legacy email reports.

#### `v2026.08.2` - 2026 Q3

- Recursive default BOM versioning added for bottom-up propagation of default child BOM changes.
- BOM update job can be queued on the long worker and protected with a database lock.
- New submitted BOM versions are created and promoted instead of editing submitted BOMs in place.
- Item default BOM fields and AMF BOM snapshots are aligned when default BOMs are repaired.
- 4B/4C BOM family-coherence repair tooling added for stale disabled component links, invalid child BOM links and expected special-component quantities.
- Issue custom layout refreshed with support timeline and resolution fields.
- Batch tracking and automatic per-receipt Batch creation activated for syringe item `70E000`.
- Tests added for recursive BOM updates, BOM family coherence and receipt batch setup.

#### `v2026.08.1` - 2026 Q3

- Tool Maintenance workflow added for items in Item Group `Tool`.
- Tool-only maintenance fields added to Item records, including equipment details, responsibility, safety information, instructions, dates, status and summary counts.
- Tool Maintenance Plan DocType added for preventive and one-time maintenance planning.
- Tool Maintenance Log DocType added for intervention history and completion tracking.
- Tool Maintenance planner page added at `/app/tool-maintenance` for operational follow-up.
- Item form buttons added for Maintenance Planner, New Maintenance Plan and Log Intervention.
- P202-O BOM creation added for six-character `4D` items, using validated P201-O/`42` BOM templates and replacing the source body with item `5D1000`.
- Maintenance spreadsheet metadata imported into Tool Item fields where item matching was safe and unambiguous.
- Automatic lifecycle updates added so Tool item summaries refresh when tools, plans or logs are created, edited, completed, moved or deleted.
- Daily maintenance summary refresh added so due and overdue status remains current as dates age.
- Safeguard added to prevent moving Tool items with maintenance records out of Item Group `Tool`.
- Batch tracking and automatic per-receipt Batch creation activated for syringe item `70E000`.

#### `v2026.07.1` - 2026 Q3

- Purchase Order Cash Forecast report added to support procurement cash planning by combining unbilled Purchase Order commitments and unpaid supplier invoices linked to Purchase Orders, with cumulative one-month, one-quarter and one-year views in CHF, EUR and USD plus a detailed drill-down view.
- Purchase receipt return support updated.
- Issue management functionality added or expanded.
- Estimated manufacturing time added to Work Orders.
- Item dashboards and item creation tools updated.
- Component Drawing Register added.
- Leave entry behavior updated.
- Delivery Note behavior updated.
- Global Inventory Dashboard, procurement tools and stock analysis algorithms added.
- Bank reconciliation automation and serial-number mixer work added.
- Sales Invoice trend reporting updated.

#### `v2026.06.0` - 2026 Q2

- Item management and Delivery Note behavior updated.
- Stock Entry repair and landed cost behavior added or improved.
- Loan Order functionality introduced and linked to operational documents.
- Sales Order, Delivery Note and Issue links improved.
- Batch disabling and batch management updated.
- Machining reports and machining stickers added.
- Ledger-related updates added.
- Safety Stock behavior updated.
- ATR batch handling added.
- Marketing-related updates added.
- Item cleanup utilities added.
- Work Order auto-creation and Work Order planning creation improved.
- SCM dashboard created or refreshed.
- KPI dashboards and dashboard popups updated.
- Sales Order creation hotfix added.
- Quotation logic refactored.
- Work Order scrap handling added.
- AI Integration Report and AI Report features introduced.
- Repair batching, OTIF exclusion handling and hook updates added.

#### `v2026.03.0` - 2026 Q1

- Sales Invoice custom behavior added.
- Stock and rate override logic improved.
- Swiss VAT handling added.
- Customs country mapping and tariff assignment improved.
- Delivery Note serial-number protection and customs field corrections added.
- Planning DocType expanded with available and used quantity fields.
- Batch quantity retrieval added to planning.
- Leave Balance Overview improved to include previous-period balances.
- Project ID handling updated.
- Item management, BOM child behavior, planning and purchase invoice support updated.
- Costing-related updates added.

### 2025 - Quality, Production Tracking, BOM Costing And Satisfaction Management

#### `v0.7.0` - 2025 Q4

- Production Tracking and Timer Production features introduced.
- Item Creation expanded with additional head item/head check fields.
- Sales Order to Delivery Note lead-time and serial-number delivery support added.
- Log Entry versioning behavior refined.
- Quality Inspection and Stock Entry rate handling improved, including scrap-related handling.
- Pump BOM update functionality added with UI and backend support.
- Item valuation updates based on BOM costs added.
- Timer Production UI, operator validation and operator time retrieval added.
- Work Order QR codes connected to the production timer page.
- Automatic Quality Inspection generation added for batches and Work Orders.
- Drawing-based Quality Inspection support added.
- QA Template Table and Drawings Quality Inspection DocTypes added.
- HS Code DocType and customs tariff number auto-completion added.
- FFTEST search capability added.
- Release milestone `v0.7.0` recorded.

#### 2025 Q3

- BOM update logic improved, including recursive default BOM updates.
- Item creation continued to evolve.
- Accessory defaults and item pricing checks added.
- Item No Price 2025 report added.
- Margin reporting updated.
- Delivery Note and Stock Entry behavior improved.
- BOM valuation-rate updates added.
- AMF-specific General Ledger reporting introduced.
- Customer Feedback DocType added.

#### `v0.6.5` - 2025 Q2

- Item creation workflows improved.
- Stock Entry behavior patched for an ERPNext-related issue.
- Planning and rating reports updated.
- Customer reporting and TBO reporting added.
- Leave Balance Overview report introduced.
- Global satisfaction score features added.
- Release milestone `v0.6.5` recorded.

#### `v0.6.0` / `v0.6.1` - 2025 Q1

- Safety Stock and Work Order creation automation improved.
- BOM and Stock Entry behavior updated.
- Zebra label support added.
- Planning tools expanded.
- Drawing matching utilities introduced.
- Item actions and item update tools added.
- Release milestones `v0.6.0` and `v0.6.1` recorded.
- Price list cleanup and new reporting work added.
- Customer and referral survey work began.
- Raw material batch handling introduced.
- Global Quality Inspection features added.
- CRM, CSAT and NPS tracking expanded.
- Contact email uniqueness added.

### 2024 - CRM Expansion, Logistics Tracking, Item Creation And Planning

#### 2024 Q4

- Contact form handling and CRM workflows continued to mature.
- Item Stock Summary report added.
- Item Creation DocType introduced.
- Serial checks and batch disabling tools added.
- Campaign list logic, contact filtering and duplicate prevention improved.
- Gravity Forms and Brevo synchronization refined.
- Work Order and Orders to Fulfill behavior updated.
- Customer-to-organization conversion and contact-company handling improved.
- Brevo campaign DocType, campaign synchronization and contact statistics added.
- Stock-related behavior updated.

#### `v0.4.0` - 2024 Q3

- Item creation and BOM creation tools expanded substantially.
- Item Master and Product Master tooling evolved through multiple versions.
- Log Entry support introduced.
- Master CRM module added.
- Sales Action and Sales Activity features introduced.
- Contact management improved with statuses, customer linking, duplicate checks and dashboard extensions.
- Sales journey and quotation workflow introduced.
- Address list, campaign list and duplicate contact reporting added.
- EUR.1 form checks introduced.
- Barcode, DataMatrix and sticker handling improved.
- Translation and customer naming customizations added.
- Brevo integration introduced.
- Gravity Forms integration introduced, including form entries and automated lead/contact workflows.
- CRM sales analytics added.
- CRM milestone `v0.4.0` recorded.

#### 2024 Q2

- Production PDF generation added.
- Forecast stock availability reporting introduced.
- Item Master update tooling expanded.
- Supplier and QR code handling improved.
- Inventory turnover reporting revised.
- DHL tracking functionality expanded with settings and tracking information.
- Logistics tracking page added.
- Quotation Dashboard introduced.

#### 2024 Q1

- New operational reports added, including production and job-cost comparison views.
- FFTEST rate and availability tooling improved.
- Reorder level notifications and weekly stock notifications added.
- Email and hook behavior refined.
- Planning was migrated and stabilized on the server.
- Safety stock testing and visualization improved.
- Sales Order stock checks and operations dashboards introduced.
- Potential assemblies reporting added.
- Label, barcode and production sticker formats expanded.
- Delivery Note serial-number and item-description handling improved.

### 2023 - Core Operations, Planning, Labels And Stock Reporting

#### 2023 Q4

- KPI reporting and daily safety check features added.
- Serial-number handling improved.
- Item information expanded with warehouse visibility.
- Safety stock logic and Work Order serial-number behavior improved.
- Common UI utilities and navbar styling refined.
- DHL export functionality introduced.
- Stock Entry hooks and planning updates added.
- Item image creation/update support introduced.
- Inventory Turnover Ratio report added.

#### 2023 Q3

- Purchase Order checking, updating and notification utilities added.
- Invoice template adjusted.
- Planning web pages and item information pages expanded.
- Packaging, batch and serial-number rules improved.
- Item QR code generation refined.
- Contact form creation introduced.
- FFTEST tooling introduced.

#### 2023 Q2

- Production Master Planner work began and was iterated heavily.
- QR code generation introduced for operational documents and items.
- BOM creation and Work Order creation utilities added and improved.
- Inventory Turnover reporting introduced.
- Produced versus delivered and purchased versus manufactured reporting added.
- Delivered Items report and SCM dashboard created.
- Delivery Note API and Delivery Note Item customizations started.
- Common client-side AMF utilities introduced.
- Web pages for planning and item information introduced.
- Email and form-triggered utilities added.
- Staff production assignment and item information behavior improved.
- Requirements and dependency setup cleaned up.

#### 2023 Q1

- Repository and app structure stabilized after initial uploads.
- Early security fixes and minor operational improvements applied.
- Label utilities and Google Charts loading support introduced.
- Navigation links to custom reports added.
- Development environment visual distinction added.

### 2022 - Foundation

- Initial AMF custom ERP app created.
- Base report and page structure imported.
- Early operational corrections and setup work added.

## Functional Area Summary

### Manufacturing And Production

- Production Master Planner, planning pages and planning DocType enhancements.
- Work Order creation, assignment, serial-number behavior and automation.
- P202-O BOM creation for the `4D` finished goods family.
- 4B/4C BOM family coherence repairs and recursive default BOM versioning.
- Production tracking with operator timers and Work Order QR access.
- Four-hour operator-session alerts with ToDo follow-up and optional email.
- FFTest P202 serial mapping, Work Order checks and a read-only stock-flow preview with a separately installed diagnostic page.
- Opt-in staged FFTest production for serialized `4D` products, including received purchased-body serials, intermediate reuse and a local manual test helper.
- Estimated manufacturing time and production cost/time tracking support.
- Tool maintenance planning, due-date tracking and intervention history.
- Machining reports and production stickers.

### Inventory, Stock And Procurement

- Inventory turnover, stock summary, projected stock and stock/revenue reporting.
- Safety stock, reorder level, stock forecasting and shortage visibility.
- Purchase Order checking, late purchase reporting and procurement dashboards.
- Batch handling, raw material batches, ATR batches and batch disabling.
- Receipt-specific batch creation for selected purchased stock items.
- Stock Entry hooks, repairs, scrap behavior and valuation/rate updates.
- Monthly random inventory checks with ten references, warehouse-level counts, explicit confirmation, linked stock corrections and final ledger verification.
- Manager cancellation/deletion of inventory checks with preserved correction vouchers, assignment closure and one-time installation setup.
- Guarded correction tooling for the duplicate RVM.3300 receipt and its downstream batch/ledger history.
- Separate MAT.1021 batch references for the purchase receipt and original stock/subcontractor flow.
- Guarded stock-history corrections for item `110137` and Work Order `OF-02883`.

### Item, BOM And Product Master

- Item Master, Product Master and Item Creation workflows.
- Complete engineering plans and recorded review before Item/BOM creation, with controlled replacement proposals and dependency checks.
- Shared new-head/component suffix reservations, independent Product codes/references, existing-head reuse and Product-only creation.
- Individual LV/HV/HD and RVM Mini/interface configurations, selectable raw stock and seat pins, and corrected NM/TH `421` and RS485 `422` Product prefixes.
- Protected creation results, Item/BOM history searches and request cancellation/amendment with generated records retained.
- BOM creation, P202-O BOM creation, BOM child updates, pump BOM updates, 4B/4C repairs and recursive BOM updates.
- Governed customer, customs and internal production descriptions for Product Items.
- Evidence-based descriptions and stable child-group classification for purchased physical items.
- Customer-facing Item description cleanup that removes internal evidence metadata while retaining catalog wording.
- `4D1` RS485 and `4D2` CAN variants with corresponding BOMs where source components are eligible.
- Custom Valve Head propagation and R&D review controls for custom Products in selling documents.
- Item valuation from BOM costs.
- Acoustic Mixer Product/BOM migration using dedicated non-stock allocations to reach a CHF 2,500 unit-cost target.
- Reviewed material repricing for 61 selected default BOM roots and qualifying made-child BOMs.
- Drawing match and component drawing register support.
- Item maintenance fields and automatic maintenance summaries for Tool and all its subgroups.
- Item pricing and item category controls.

### Logistics And Delivery

- Delivery Note API and Delivery Note customizations.
- Serial-number transfer to Delivery Notes.
- DHL export, tracking and MyDHL Express shipment creation.
- Private DHL text attachments with Delivery Note write-permission checks.
- Logistics tracking page and tracking settings.
- Delivery Note commercial invoice and packaging branding print formats, including single-letterhead commercial-invoice rendering.
- Sales Order to Delivery Note lead-time reporting.
- Loan Order support, document links and commercial settlement invoicing.

### CRM, Sales And Marketing

- Master CRM module introduced.
- Contact enhancements, statuses, duplicate prevention and customer linking.
- Sales actions, sales activities, sales journey and quotation workflow.
- Custom-item warnings on Quotations and Sales Orders requiring R&D review.
- Quotation Product resolution aligned with reviewed body/head/syringe BOM composition and RVM interface references.
- AMF Control Center Premium license Items for included, complimentary, discounted and standard offers in the CHF selling price list.
- Default `Standard Branding AMF 2026` Sales Order output with customer, delivery, remaining-quantity, price and totals presentation.
- Gravity Forms integration for external form entry handling.
- Brevo integration, campaign lists, campaign synchronization and contact statistics.
- Customer, referral and satisfaction survey features.

### Quality And Issue Management

- Global Quality Inspection and related inspection tables.
- Automatic Quality Inspection generation for batches and Work Orders.
- Drawing-based inspection support.
- Preventive Tool maintenance plans and maintenance intervention history.
- Customer Feedback and satisfaction scoring.
- Governed Issue processes, canonical Issue Types, accountable-owner routing and subject-based classification suggestions.
- User-created Issue Types through `Other`, plus customer/supplier Issue history and traceable AMF Issue Test to legacy Issue links.
- Issue outcomes separated from classifications, with inactive legacy types retained for historical records.
- Root cause and quality investigation support.
- Organizational Modification Requests with C2/C3 risk assessment, approvals, implementation actions, effectiveness review and Quality closure.

### Finance, Compliance And Administration

- AMF-specific General Ledger reporting.
- Swiss VAT handling.
- HS Code and customs tariff support.
- Customs-oriented Delivery Note commercial invoice output.
- Landed Cost Voucher-related behavior.
- Purchase Receipt GL precision filtering for zero-rounded entries, including later reposts.
- Sales Invoice custom behavior.
- Bank reconciliation automation with multi-account and single-account PostFinance CSV support.
- Authenticated invoice-rate exports with currency separation and administrative/invoice permission checks.
- Expense claim and administrative scripts.

### Reporting, Dashboards And AI

- Operational, sales, procurement, stock, production, delivery and quality reports added over time.
- BOM Cost Breakdown for planned/actual, average, recursive and latest-purchase/process analysis, with source references and explicit reconciliation differences.
- Permission-filtered Item Creation Results reporting and immutable private AMF Data Artifact storage for report inputs and outputs.
- SCM, quotation, global inventory, operations KPI and planning dashboards introduced or improved.
- Weekly Operations Report slides with Production-order scope, non-`GX` delivery/QC filters and manual email distribution.
- AI-assisted operations reporting added with controlled evidence-backed insights.
- Document AI import structures added for document parsing and extraction workflows.

### User Experience And Technical Enablement

- Custom pages, common JavaScript utilities and UI refinements added.
- DHL Shipment form actions for draft building, product lookup, validation and AWB creation.
- Loan Order customer print format and print-time address, contact and description preparation.
- Sales Order 2026 branded print format and controlled French OMR PDF generation.
- Sales Order and OMR Print Format records managed through standard Frappe fixtures, with retained stylesheet sources, a single default Letter Head on Sales Order confirmations and improved page margins.
- Barcode, DataMatrix, QR code and label infrastructure expanded.
- Alphanumeric component/Product code support across batch setup, drawing selection, Work Order tooling and manufacturing reports.
- Web pages and generated documents for planning, item information, logistics, print formats and document tooling added.
- Hooks, migrations, settings DocTypes and background utilities added to automate operational behavior, including Tool maintenance lifecycle updates, BOM repair workflows, DHL Shipment setup and weekly report settings.

## Current Main Custom Objects

The current AMF custom app includes custom objects for planning, Item Creation with Review/Variant/Result child records, AMF Data Artifacts, Monthly Inventory Settings and Checks, Weekly Operations Reports, Organizational Modification Requests and Actions, Tool Maintenance Plans, Tool Maintenance Logs, global quality inspection, Timer Production Alerts, timer production, DHL tracking, loan orders, issue management, AMF Issue Processes, Document AI imports, HS codes, customer feedback, CRM forms, Brevo campaigns, sales actions and satisfaction surveys. It also includes utility layers for Product and purchased-item descriptions, customer-description cleanup, custom-item governance, Issue classification and history, Loan Order settlement and printing, Sales Order/OMR print formats, DHL Shipment creation, reviewed creation plans, permanent code reservations, creation lifecycle/traceability, BOM family repair, recursive BOM updates, selected BOM repricing, Acoustic Mixer setup, `4D` interface variants, Delivery Note print formats, Purchase Receipt GL precision, batch setup and guarded stock-history correction.

The current report catalog includes operational reports for inventory turnover, stock and revenue, produced and delivered items, purchased versus manufactured items, delivered items, purchase order items, late purchases, purchase order cash forecasting, projected stock, sales dashboards, quotation dashboards, manufacturing yield, machined parts, item margins, no-price items, leave balances, AMF general ledger, BOM Cost Breakdown, Item Creation Results, Sales Order to Delivery Note lead time and weekly operations slide reporting.

The current page catalog includes inventory planning, sales order stock projection, logistics tracking, global inventory dashboard, Tool Maintenance, component drawing register, bank reconciliation automation, an FFTest stock-flow diagnostic page installer, order confirmation parsing, PDF text extraction and file upload tools.

## Release Maintenance Workflow

Use the report's Latest reviewed commit as the exclusive starting point and inspect only later committed changes in `apps/amf`. Preserve earlier release history, exclude uncommitted files and edits from the change descriptions, and advance the reviewed cutoff to the last commit covered. Dates alone are insufficient when more commits land on the same day.

When a new release is prepared:

1. Add a new entry at the top of the Current Version Register.
2. Mark the previous latest release as Superseded.
3. Add a new Latest Release section or update the existing one with the new release version.
4. Add short, business-readable change notes grouped by functional area.
5. Include user impact, validation notes and any required user action.
6. Update the Release History with the same release version and period.
7. Copy the latest-release email format below, replace the placeholders and send it to the company after validation.

Recommended fields for each future release note:

- Release version.
- Release date.
- Release status.
- Functional area.
- Short business description.
- Operational impact.
- Related release, ticket or commit if available.
- Link to the live ERP system.

This document should remain high level. Technical implementation details, individual bug fixes and minor refactors should stay in git history unless they changed a business process, a user workflow, an audit trail or a management report.

## Format d'email pour l'entreprise

### Email de la dernière version - prêt à valider

Objet: AMF ERP - Version v2026.10.3 - Création d'articles, FFTest et analyse des coûts

Bonjour à toutes et à tous,

Les notes de la version AMF ERP v2026.10.3, couvrant les changements commités depuis le dernier rapport jusqu'au 29 octobre 2026, sont prêtes pour validation. La version applicative correspondante est 0.7.12.

AMF ERP live
https://amf.libracore.ch/desk#

Cette version renforce la création d'articles et de BOM avec un plan complet, une revue d'ingénierie enregistrée et une traçabilité des résultats. Elle élargit les configurations disponibles, ajoute un flux FFTest dédié aux produits 4D et complète les outils d'analyse des coûts, de protection des exports et de gestion des contrôles d'inventaire. Le déploiement et les vérifications métier sont à confirmer avant diffusion de cette annonce.

Principaux changements:

Création d'articles et revue d'ingénierie
https://amf.libracore.ch/desk#List/Item%20Creation/List
Les configurations sont sélectionnées individuellement, puis un plan présente les articles, matières, quantités, révisions de BOM et éventuels remplacements. Une revue d'ingénierie est enregistrée avant soumission; toute modification des données ou dépendances impose une nouvelle revue. Le mode Create Products Only permet de conserver une tête existante et de créer uniquement les produits choisis.

Configurations et numérotation
Le choix couvre les configurations LV/HV/HD, les seringues U autorisées sur les corps LV standard, les pins de siège et les variantes RVM, dont Mini base/RS485/CAN. Les nouveaux produits NM/TH utilisent `421xxx` et les nouveaux P201-O RS485 `422xxx`; les produits existants correspondants conservent leurs codes. Des suggestions et dérogations contrôlées de code/référence permettent de traiter les conflits dans le plan revu.

Historique et cycle de vie
https://amf.libracore.ch/desk#query-report/Item%20Creation%20Results
Les résultats relient chaque article et révision de BOM à sa demande de création, avec accès depuis les fiches Item et BOM. L'annulation motivée d'une demande conserve les articles, BOM et réservations de codes; un amendement passe par une nouvelle revue d'ingénierie.

Flux FFTest 4D
Un module séparé prévoit les étapes nécessaires à partir des BOM, réutilise un numéro de série intermédiaire disponible et vérifie les lots et entrepôts. Le composant acheté `5D0000` doit déjà être réceptionné avec son numéro de série: il n'est pas fabriqué par ce flux. Une prévisualisation et un outil local de test manuel sont disponibles; le point d'appel doit être configuré explicitement pour activer ce module.

Analyse des coûts et exports privés
https://amf.libracore.ch/desk#query-report/BOM%20Cost%20Breakdown
Le rapport compare les coûts prévus/réels, les moyennes, les BOM imbriquées et les derniers prix de réception, avec une option de coûts de processus historiques. Les données de rapport privées sont stockées dans la base avec téléchargement autorisé; les exports de prix séparent les devises et les fichiers texte DHL deviennent des pièces jointes privées.

Contrôles d'inventaire et Acoustic Mixer
Les responsables stock peuvent annuler ou supprimer un contrôle mensuel tout en conservant ses corrections de stock. L'initialisation de cette fonction s'exécute une fois à l'installation ou par patch versionné. Une migration dédiée crée ou vérifie `45D040-AM` et `46F055-AM` avec leurs allocations non stockées et un coût BOM unitaire de CHF 2'500, distinct d'un prix de vente.

Ce que cela signifie pour vous:

- Les préparateurs et responsables ingénierie doivent vérifier le plan complet et renouveler les approbations des demandes encore en brouillon sous les nouvelles règles.
- Les équipes commerciales peuvent vérifier la résolution des configurations dans les Quotations, notamment les variantes RVM et les nouveaux préfixes NM/TH et RS485.
- Les utilisateurs FFTest sont invités à valider la prévisualisation et un cas de stock isolé après configuration du nouveau module.
- Les responsables stock peuvent tester le cycle d'annulation/suppression d'un contrôle et la conservation de ses documents de correction.
- Les équipes coûts et finance peuvent comparer les nouvelles vues à leurs sources et vérifier les accès aux exports; les allocations Acoustic Mixer restent à revoir si les coûts composants évoluent.
- Merci de signaler tout comportement inattendu via le canal de support interne habituel.

Bonne journée,

Alex

### Modèle réutilisable pour les futures versions

Objet: AMF ERP - Version {release_version} - {release_title}

Bonjour à toutes et à tous,

Une nouvelle version AMF ERP, {release_version}, est maintenant disponible dans le système live:

AMF ERP live
https://amf.libracore.ch/desk#

Date de publication: {release_date}

Objectif principal: {one_sentence_summary}

Principaux changements:

{feature_or_change_name_1}
https://amf.libracore.ch/desk#{feature_or_change_route_1}
{brief_change_1} - {business_impact_1}

{feature_or_change_name_2}
https://amf.libracore.ch/desk#{feature_or_change_route_2}
{brief_change_2} - {business_impact_2}

{feature_or_change_name_3}
https://amf.libracore.ch/desk#{feature_or_change_route_3}
{brief_change_3} - {business_impact_3}

Ce que cela signifie pour vous:

- {user_action_or_note_1}
- {user_action_or_note_2}
- {support_or_validation_note}

Merci d'utiliser le système AMF ERP live ici:

AMF ERP live
https://amf.libracore.ch/desk#

Bonne journée,

Alex
