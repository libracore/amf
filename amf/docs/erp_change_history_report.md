# AMF ERP Release Notes

Generated on: 2026-11-26

Change history through: 2026-11-26

Latest reviewed commit: `145a35c`

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

Latest release: `v2026.11.2`

Release status: Ready for validation

Release audience: AMF ERP users, department leads, management, operations, finance, logistics, quality, sales and support teams.

## Purpose

This document is the business-facing release notes and change history for the AMF ERP custom app.

It summarizes the main ERP changes developed in the AMF custom app from the beginning of the recorded development history to 2026-11-26. The report is based on the `apps/amf` git history, which starts on 2022-09-19, and on the current AMF app structure, including custom DocTypes, reports, pages, hooks and documentation.

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
| `v2026.11.2` | Ready for validation, latest | 2026 Q4, Nov 5-26 | Sales Analytics, customer feedback and manual closure emails, production cockpit, FFTest corrections, migration layouts, MAT.1021 batch repair and NKN tube caps. |
| `v2026.11.1` | Superseded | 2026 Q4, Nov 3 | Machining-planning page and draft deletion, matching magnet stock coverage, one-unit FFTest consumption and manual machining assignments to Martin. |
| `v2026.10.3` | Superseded | 2026 Q4, Oct 26-29 | Reviewed Item Creation and lifecycle, RVM/LV/HV variants, staged FFTest, BOM cost analysis, private exports, inventory lifecycle and Acoustic Mixer setup. |
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

## Latest Release: `v2026.11.2`

Release date: 2026-11-26

Release status: Ready for validation

Committed change window: 2026-11-05 to 2026-11-26

Reviewed commit range: `b51ff48..145a35c` (18 commits since the previous report update; its application cutoff was `e856f57`).

AMF app version at reviewed commit: `0.7.12`

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

### Summary

This release adds AMF Sales Analytics for CHF reporting of revenue, order intake, shipments and outstanding commercial commitments. Users can inspect source documents, customer/product breakdowns and reconciliation details, with optional approved billing dates and targets. The dashboard distinguishes posted actuals from commitments and outlook, and applies the user's source-document and export permissions.

Customer feedback is integrated into manually sent Sales Order confirmations and Issue closure emails. A token-protected public form collects satisfaction, recommendation and optional future-needs comments; responses feed the existing submitted-survey workflow. Issue closure now offers an editable customer or supplier email that requires an explicit Send action, and separate editable AMF templates are installed for both communication types.

Production Tracking receives a clearer cockpit and machining filters, while FFTest preserves body serials on serialized finished products and keeps customer Sales Orders on the final manufacturing order. Additional committed migrations preserve form layouts, restore the MAT.1021 batch chain and create four NKN tube-cap Items/BOMs. Delivery Note tariff lookup also tolerates destinations without a configured tariff column.

### Highlights

- Added AMF Sales Analytics with period comparisons, customer/product views, shipping commitments, billing balances, source details and permission-controlled Excel/CSV exports.
- Added approved billing-date and revenue/order-intake target records, with reconciliation for noncommercial shipments, returns and quantities credited then re-invoiced.
- Added customer feedback links and a public three-question response form, with one response per request and activation only after email queueing.
- Changed Issue closure to a manual composer workflow and installed editable `AMF Sales Order Confirmation` and `AMF Issue Closure` templates.
- Refined satisfaction-score updates, repeatable global snapshots and new Contact Country defaults while retaining AMF's existing scoring formulas.
- Redesigned the separate production cockpit and machining table with summaries, quick filters, machine distribution, pending-edit navigation and larger desktop text.
- Corrected FFTest serialized-final carryover and component Work Order Sales Order inheritance; improved form-layout migration and guarded MAT.1021 batch repair.
- Added missing-destination tariff handling and an NKN tube-cap migration with validated PEEK recipes and private drawing import.

### Change Notes

| Area | Change | Brief Explanation |
| --- | --- | --- |
| Sales Analytics | Source-linked commercial reporting in CHF. | The new Desk page reports submitted revenue, order intake, deliveries and open commitments for Advanced Microfluidics SA, with history from 2022. It provides period comparisons, customer/Item/group breakdowns, invoice reconciliation and Excel/CSV detail downloads. Document, company, field and export permissions apply; some cross-document balances require complete eligible source access. |
| Billing and shipment analysis | Approved outlook and more precise reconciliation. | Optional submitted billing records assign an expected invoice date to a specific Sales Order row and quantity; targets cover a complete month, quarter or year without automatic annual phasing. Noncommercial movements are separated from commercial deliveries, returns follow their source classification, and exact linked credit/re-invoice sequences avoid double-counting billed quantities. Overdue shipping rolls into the current schedule month while retaining its original ERP date and overdue flag. |
| Public customer feedback | Token links collect one submitted survey response. | Supported Sales Order confirmations and customer Issue emails can include five rating links that open the same public form with the selected star prefilled. Satisfaction 1–5 and recommendation 0–10 are required; a future-needs comment is optional. Viewing a link creates no survey, and repeated submission returns the thank-you message without creating another response; prepared links activate only when the email is queued. |
| Closure emails and templates | Users review and send external messages explicitly. | Closing an Issue offers a customer/supplier draft in the standard composer; the user must click Send, and the legacy automatic Issue Closed notification is disabled by setup. New editable AMF confirmation/closure templates are installed without replacing existing edited templates, and customer drafts can carry feedback links while supplier drafts omit them. Bulk closure offers an Issue to review rather than sending a batch of emails. |
| Satisfaction scores and Contacts | Submitted responses drive scores; defaults are more predictable. | Contact scores refresh from the latest submitted survey on submission/cancellation, and referral records no longer fabricate numeric ratings. Global snapshots can be recalculated on the same day and empty report ranges return zero; existing AMF CSAT/recommendation formulas are retained. New Contacts start with Country blank in full form and Quick Entry while explicit supplied values are preserved. |
| Production cockpit | Clearer overview and interactive machining filters. | The separate planning page adds summary cards, assembly/machining lanes, complete order labels, date states, quick filters and a machine-distribution panel. Pending edits are highlighted with navigation to changed rows; responsive pinned columns and larger desktop text improve readability. Recorded estimated days describe existing work rather than machine capacity, and the database Web Page must be refreshed through its installer after template deployment. |
| FFTest manufacturing | Body serial and customer demand links preserved correctly. | Serialized final assembly carries the consumed body's serial into the finished Item using native Manufacture behavior instead of allocating another serial. Generated component Work Orders link to their manufacturing parent and inherit its project, leaving their own Sales Order empty; the final order retains the customer Sales Order. This fixes native rejection of component Items absent from the Sales Order and applies to future calls rather than repairing historical entries. |
| Form migrations | Sales Order layouts and a targeted Work Order override retained. | AMF customization exports own Sales Order and child-table field positions; setup hooks add missing fields without overwriting existing definitions. The duplicate Sales Team export is removed, and the Work Order Sales Order Item field's update-after-submit property is supplied as a narrow fixture. Other Work Order field layout properties remain governed by their configured metadata. |
| MAT.1021 batches | Receipt-to-subcontract chain restored with data checks. | A new migration selects the named source documents independently of the site's filesystem name, restores receipt batch `8UREHM DAL` and original-stock batch `KRDLAT AMF`, and links the latter through transfer and subcontract consumption. It checks document identities, quantities, conflicting batches and warehouse totals. Only batch tracking/references change; quantities, valuation and GL are not adjusted, and the Batch barcode hook now leaves commits to its caller. |
| Delivery Note customs | Missing tariff destinations no longer cause a column-query error. | HS-code lookup reads the configured tariff row and returns its EU/destination value when present. An unknown country or absent tariff column returns no code, allowing the caller to handle missing customs data rather than failing on an SQL column name. |
| NKN tube caps | Four manufactured components and default BOMs added by migration. | The patch creates or validates `700070`–`700073` for NKN.2024/2031/2039/2040, with 0.04 m of the specified PEEK bar per piece. Drawing PDFs can be staged privately and are checksum-checked before attachment; missing drawings are reported for later import. NKN.2024's filename/title-block revision mismatch keeps its PDF out of the active drawing register pending confirmation; no Work Orders or stock postings are created by this patch. |

### User Impact

- Sales and finance users can inspect actuals, commitments and source reconciliations in Sales Analytics. Approved billing dates and targets need their own submitted records; the dashboard does not invent an invoice schedule from shipping dates.
- Staff select the AMF templates and review recipients, text and attachments before sending. Closing an Issue alone sends no closure email; customer feedback links require the public host to run the matching route and schema.
- A supported confirmation/feedback send reuses its existing Communication on repetition. Failed delivery should be handled with the normal Email Queue retry/resend controls.
- Planners gain filters and clearer production visibility while retaining the same Work Orders and row-save/delete rules. Deployment must refresh the separate database-stored Web Page as well as the source code.
- FFTest users keep the customer Sales Order on the final Work Order and use the body serial for serialized final output. Existing submitted Work Orders and Stock Entries are not backfilled by these fixes.
- Stock and engineering teams should verify MAT.1021 batch references after migration and review NKN material consumption and drawing revisions before manufacturing release.

### Validation Notes

This report was checked against the 18 committed changes above. The following are recommended release checks; no live transactions, emails or migrations were run while updating the report:

- Register Sales Analytics and its optional billing/target DocTypes in staging. Reconcile invoice net/charges/VAT/gross, linked credits and re-invoicing, commercial/noncommercial returns, dated billing and permission-restricted details/exports.
- Prepare and send test confirmation/closure messages with mail delivery intercepted. Confirm that closing an Issue alone queues nothing, supplier drafts omit feedback, attachments are retained and repeated supported sends create no duplicate request/message.
- Open a queued feedback link, change the preselected rating, submit both ratings including recommendation zero, and resubmit it. Verify one survey, Contact score refresh/cancellation behavior, repeatable global snapshots and explicit Contact Country preservation.
- Refresh the planning Web Page using its installer and validate both tabs, combined filters, machine summaries, pending edits, pinned columns and desktop/mobile readability. Follow the [production-page deployment notes](production_tracking_planning_redesign.md).
- Test FFTest serialized final assembly and newly generated component orders with parent/project links, while retaining native Sales Order validation for standalone Work Orders.
- After the guarded MAT.1021 migration, reconcile both source batches through `PREC-03061-1` and warehouse totals without stock/GL changes. Check Sales Order layouts after migration and Delivery Note HS lookup for both configured and absent destinations.
- For NKN Items, verify the four identities, active default BOMs and 0.04 m PEEK recipes. Stage the approved PDFs privately for import, resolve NKN.2024's revision discrepancy and check the resulting drawing register.

## Executive Summary

Since the beginning of development, the AMF ERP has evolved from a custom reporting and page layer into a broader operational system covering manufacturing, planning, inventory, purchasing, logistics, sales, CRM, quality, finance support and management reporting.

The main evolution areas are:

- Production planning, editable machining schedules, Work Order automation, manual-order assignments and manufacturing follow-up.
- Tool maintenance planning, preventive status and intervention history across Tool subgroups.
- Reviewed Item/BOM creation with configuration selection, identifier reservations, execution history and amendments, plus governed descriptions, purchased-part classification and custom-item review controls.
- QR code, barcode, label and production sticker generation.
- Inventory visibility, safety stock, stock forecasting, monthly physical checks and replenishment support.
- Purchasing and procurement follow-up.
- Delivery Note, shipping, DHL tracking, DHL shipment creation and logistics tools.
- CRM, contact management, sales actions, campaign lists and external form/email integrations.
- Quality inspection, process-owned Issue classification and party history, organizational change control, token-linked customer feedback and submitted-survey satisfaction scores.
- Finance and compliance support such as VAT, HS codes, customs values, landed cost, Purchase Receipt GL precision, custom ledgers and PostFinance reconciliation.
- Operational dashboards, source-linked Sales Analytics for revenue/order intake/commitments, KPI reporting and AI-assisted reporting.
- Weekly operations slide reporting with controlled production, delivery, QC and shipping scope.
- Customer-facing Sales Order, Loan Order, Delivery Note and commercial-invoice document formats.
- Source-linked BOM cost analysis, reviewed material repricing, receipt batch tracing and FFTest serial/stock-flow controls.
- Operator-session timer alerts with linked ToDos and optional email.
- User interface improvements, document hooks, automation scripts and administrative utilities.

## Release History

### 2026 - Advanced Planning, Finance, Compliance, Dashboards And AI Reporting

#### `v2026.11.2` - 2026 Q4, Nov 5-26 - Latest

- Added AMF Sales Analytics for CHF actuals, order intake, commercial deliveries and open commitments from submitted ERP records, with history from 2022. Period/customer/product views, source details, invoice reconciliation and Excel/CSV exports apply document/field/export permissions.
- Added optional Sales Analytics Billing and Target records for approved order-row billing dates and full-period revenue/order-intake targets. Shipping schedules retain original ERP dates, identify overdue/held work and move past-due shipping into the current schedule month.
- Refined analytics shipment classification for samples, loans, gifts, warranty/manufacturing movements and returns, and corrected exact linked credit/re-invoice quantity counting. Full-width layout and aligned table headers improve interpretation of the displayed values.
- Added token-protected customer feedback from supported order confirmations and customer Issue emails. The public form collects satisfaction, recommendation and optional future needs, creating one submitted survey only on explicit response and accepting repeated submissions without duplicates.
- Final Issue closure behavior requires manual sending: form/list closure offers an editable customer/supplier composer, and setup disables the former automatic Issue Closed notification. Dedicated editable AMF confirmation/closure templates are installed, with feedback only for eligible customers and existing edited templates preserved.
- Contact scores now follow the latest submitted survey on submission/cancellation; referral creation no longer supplies invented scores. Existing formulas remain, global daily snapshots are repeatable, empty report ranges return zero and new Contact Country defaults are suppressed without clearing explicit values.
- Redesigned the separate production cockpit and machining tab with summaries, lanes, quick filters, machine distribution, pending-edit navigation and responsive pinned columns. Later refinements compact panels, position the heading with navigation, enlarge the clock and improve desktop text readability; deployment must refresh the database Web Page.
- FFTest now carries a consumed body's serial to a serialized finished Item and reports the same serial in preview. Component Work Orders use parent/project links instead of inheriting a Sales Order that does not sell the component; the final Work Order retains the customer order.
- Sales Order/child-table customization exports and create-only setup hooks preserve migrated layouts, replacing the duplicate Sales Team export. A targeted Work Order fixture preserves the Sales Order Item field's update-after-submit property.
- New guarded MAT.1021 migrations restore the two source batches through subcontract consumption, select the source data independently of site name and verify warehouse totals without quantity/value/GL adjustments. Batch barcode creation no longer commits its caller's transaction.
- Delivery Note HS-code lookup now tolerates a missing destination tariff column and returns no code when the corresponding data is unavailable.
- Added a migration for four NKN tube caps `700070`–`700073` with specified PEEK raw materials and 0.04 m consumption per piece. Private PDF import validates checksums, reports missing drawings and leaves NKN.2024's revision-conflicting PDF out of the active drawing register.
- Committed tests, audits, VM/browser tools and screenshots document the new analytics, feedback, production-layout and FFTest behavior. They are evidence from those changes, not live tests or deployment performed by this report update.

#### `v2026.11.1` - 2026 Q4, Nov 3

- Added a separate Production Tracking - Planning page at `/production-tracking-planning#usinage`, combining the existing Plug and Valve Seat machining reports with complete row retrieval and Expected Date ordering. All 13 current columns are shown, with eight business fields editable on authorized drafts and system/calculated fields protected.
- Row saves use native Work Order validation, permission checks and the original modification timestamp. The copied overview also improves timer selection, submitted-Delivery-Note shipment indicators, shared-note concurrency, alphanumeric machining classification and responsive layout while using the same production records.
- Added a confirmed Delete action for draft Work Orders in the machining reports. Native permissions, link checks and Frappe's Deleted Document archive apply; submitted/cancelled orders are excluded and other rows retain their staged edits.
- Machining planning now counts positive net stock of the exact `11xxxx`/`21xxxx` magnet counterpart as coverage of `10xxxx`/`20xxxx` demand. Reorder, Sales Order and legacy shortage paths retain their own warehouse/supply rules; reduced shortages flow through existing buffers and managed-draft cleanup without moving physical stock.
- The copied FFTest endpoint limits each manufacture/transfer to one finished unit's material requirement, including repeated calls for `42` products, body Work Orders and the staged `4D` chain. The cap handles duplicate input rows, stock-UOM conversions and prior consumption, with unit-level rollback on failure.
- New manual machining Work Orders receive one Open ToDo assignment to Martin on their first successful save through supported manual actions. Standard notification rules apply, existing assignees remain, and automatic planners/imports/integrations do not generate these alerts; the recipient account must remain enabled.
- Committed regression coverage and audits document machining page editing/deletion, matching-stock calculations, repeated FFTest unit production and manual assignment behavior. The recorded rollback/read-only checks are distinct from live acceptance checks for this release.

#### `v2026.10.3` - 2026 Q4, Oct 26-29

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
- First-save ToDo assignment to Martin for eligible manually created machining Work Orders, with native notification and duplicate prevention.
- P202-O BOM creation for the `4D` finished goods family.
- 4B/4C BOM family coherence repairs and recursive default BOM versioning.
- Production tracking with operator timers and Work Order QR access.
- Four-hour operator-session alerts with ToDo follow-up and optional email.
- FFTest P202 serial mapping, Work Order checks and a read-only stock-flow preview with a separately installed diagnostic page.
- Opt-in staged FFTest production for serialized `4D` products, including received purchased-body serials, intermediate reuse and a local manual test helper.
- One-unit material consumption/transfer limits across repeated calls in the copied FFTest module, including `42`/body routes and stock-UOM conversions.
- FFTest body-to-finished serial carryover and parent/project links for component Work Orders, with the customer Sales Order retained on final production.
- Estimated manufacturing time and production cost/time tracking support.
- Tool maintenance planning, due-date tracking and intervention history.
- Machining reports and production stickers.
- Separate Production Tracking - Planning page combining Plug/Valve Seat reports by Expected Date, with authorized row editing, concurrent-change checks and native draft deletion.
- Production cockpit summaries, assembly/machining lanes, quick filters, machine distribution and clearer desktop/mobile presentation.

### Inventory, Stock And Procurement

- Inventory turnover, stock summary, projected stock and stock/revenue reporting.
- Safety stock, reorder level, stock forecasting and shortage visibility.
- Exact `11xxxx`/`21xxxx` magnet sub-assembly stock coverage for `10xxxx`/`20xxxx` machining shortages, preserving existing planner warehouse and buffer rules.
- Purchase Order checking, late purchase reporting and procurement dashboards.
- Batch handling, raw material batches, ATR batches and batch disabling.
- Receipt-specific batch creation for selected purchased stock items.
- Stock Entry hooks, repairs, scrap behavior and valuation/rate updates.
- Monthly random inventory checks with ten references, warehouse-level counts, explicit confirmation, linked stock corrections and final ledger verification.
- Manager cancellation/deletion of inventory checks with preserved correction vouchers, assignment closure and one-time installation setup.
- Guarded correction tooling for the duplicate RVM.3300 receipt and its downstream batch/ledger history.
- Separate MAT.1021 batch references for the purchase receipt and original stock/subcontractor flow, with guarded repair through subcontract consumption independent of site name.
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
- NKN tube-cap component/BOM migration with specified PEEK consumption, private drawing checksums and revision-aware drawing registration.
- Reviewed material repricing for 61 selected default BOM roots and qualifying made-child BOMs.
- Drawing match and component drawing register support.
- Item maintenance fields and automatic maintenance summaries for Tool and all its subgroups.
- Item pricing and item category controls.

### Logistics And Delivery

- Delivery Note API and Delivery Note customizations, including tariff lookup that tolerates unconfigured destination columns.
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
- Token-linked order/Issue feedback with required satisfaction/recommendation answers and duplicate-safe public submission.
- Editable AMF Sales Order Confirmation and Issue Closure email templates using the standard manual composer.
- Blank Country defaults on new Contacts without clearing explicitly supplied values.

### Quality And Issue Management

- Global Quality Inspection and related inspection tables.
- Automatic Quality Inspection generation for batches and Work Orders.
- Drawing-based inspection support.
- Preventive Tool maintenance plans and maintenance intervention history.
- Customer Feedback and satisfaction scoring from submitted responses, repeatable daily global snapshots and no invented referral scores.
- Manual customer/supplier Issue closure email drafts, with automatic closure notifications disabled and optional customer feedback links.
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
- AMF Sales Analytics with CHF revenue/order intake, commercial shipments, commitments, reconciliation, source details and permission-controlled exports.
- Approved billing-date and full-period target records, with separate actual/commitment/outlook measures and credit/re-invoice reconciliation.
- Weekly Operations Report slides with Production-order scope, non-`GX` delivery/QC filters and manual email distribution.
- AI-assisted operations reporting added with controlled evidence-backed insights.
- Document AI import structures added for document parsing and extraction workflows.

### User Experience And Technical Enablement

- Custom pages, common JavaScript utilities and UI refinements added.
- Permission-aware Production Tracking - Planning copy with responsive machining tables, protected row saves/deletion, current timer selection and shared-note version checks.
- DHL Shipment form actions for draft building, product lookup, validation and AWB creation.
- Loan Order customer print format and print-time address, contact and description preparation.
- Sales Order 2026 branded print format and controlled French OMR PDF generation.
- Sales Order and OMR Print Format records managed through standard Frappe fixtures, with retained stylesheet sources, a single default Letter Head on Sales Order confirmations and improved page margins.
- Barcode, DataMatrix, QR code and label infrastructure expanded.
- Alphanumeric component/Product code support across batch setup, drawing selection, Work Order tooling and manufacturing reports.
- Migration-safe Sales Order layouts and child-table exports, plus a targeted Work Order Sales Order Item field override.
- Token-protected public satisfaction form and opt-in localhost feedback preview/testing tools.
- Web pages and generated documents for planning, item information, logistics, print formats and document tooling added.
- Hooks, migrations, settings DocTypes and background utilities added to automate operational behavior, including Tool maintenance lifecycle updates, BOM repair workflows, DHL Shipment setup and weekly report settings.

## Current Main Custom Objects

The current AMF custom app includes custom objects for planning, Item Creation with Review/Variant/Result child records, AMF Data Artifacts, Sales Analytics Billing and Target records, Satisfaction Feedback Requests, Monthly Inventory Settings and Checks, Weekly Operations Reports, Organizational Modification Requests and Actions, Tool Maintenance Plans, Tool Maintenance Logs, global quality inspection, Timer Production Alerts, timer production, DHL tracking, loan orders, issue management, AMF Issue Processes, Document AI imports, HS codes, customer feedback, CRM forms, Brevo campaigns, sales actions and satisfaction surveys. It also includes utility layers for Product and purchased-item descriptions, customer-description cleanup, custom-item governance, Issue classification and history, Loan Order settlement and printing, Sales Order/OMR print formats, DHL Shipment creation, reviewed creation plans, permanent code reservations, creation lifecycle/traceability, BOM family repair, recursive BOM updates, selected BOM repricing, Acoustic Mixer setup, `4D` interface variants, Delivery Note print formats, Purchase Receipt GL precision, batch setup, one-unit FFTest consumption, matching magnet-stock planning coverage, manual machining assignments, manual closure-email preparation, NKN tube-cap setup and guarded stock-history correction.

The current report catalog includes operational reports for inventory turnover, stock and revenue, produced and delivered items, purchased versus manufactured items, delivered items, purchase order items, late purchases, purchase order cash forecasting, projected stock, sales dashboards, quotation dashboards, manufacturing yield, machined parts, item margins, no-price items, leave balances, AMF general ledger, BOM Cost Breakdown, Item Creation Results, Sales Order to Delivery Note lead time and weekly operations slide reporting.

The current page catalog includes AMF Sales Analytics, the public satisfaction feedback form, opt-in localhost feedback previews, inventory planning, the separate Production Tracking - Planning machining page, sales order stock projection, logistics tracking, global inventory dashboard, Tool Maintenance, component drawing register, bank reconciliation automation, an FFTest stock-flow diagnostic page installer, order confirmation parsing, PDF text extraction and file upload tools.

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

Objet: AMF ERP - Version v2026.11.2 - Analyse des ventes, retours clients et production

Bonjour à toutes et à tous,

Les notes de la version AMF ERP v2026.11.2 sont prêtes pour validation. Elles couvrent les 18 commits enregistrés depuis le rapport du 3 novembre, jusqu'au 26 novembre 2026. La version applicative reste 0.7.12.

AMF ERP live
https://amf.libracore.ch/desk#

Cette version ajoute une analyse des ventes reliée aux documents ERP, un retour de satisfaction client par lien sécurisé et des emails de clôture d'Issue préparés puis envoyés manuellement. Elle améliore également le cockpit de production, le flux FFTest et plusieurs migrations de données et de formulaires. Le déploiement et les vérifications métier sont à confirmer avant diffusion de cette annonce.

Principaux changements:

AMF Sales Analytics
https://amf.libracore.ch/desk#sales-analytics
La nouvelle page présente les ventes facturées, prises de commandes, livraisons et engagements ouverts en CHF, avec analyses par période, client et article. Les détails et exports permettent de retrouver les documents sources et de rapprocher les montants. Des enregistrements approuvés peuvent ajouter des dates de facturation et des objectifs; les réalisations, engagements et perspectives restent distincts et soumis aux droits d'accès.

Satisfaction client
Les confirmations de commande et emails clients éligibles peuvent contenir cinq liens de notation ouvrant le même formulaire public. Le client confirme une satisfaction de 1 à 5, une recommandation de 0 à 10 et, s'il le souhaite, ses besoins futurs. Le lien devient actif après mise en file de l'email; une réponse explicite crée une seule enquête. Les scores utilisent les réponses soumises et les formules AMF existantes.

Emails de confirmation et de clôture
Les modèles modifiables AMF Sales Order Confirmation et AMF Issue Closure sont disponibles dans le compositeur habituel. Fermer une Issue propose de préparer un email au client ou fournisseur, puis l'utilisateur doit cliquer sur Envoyer; la notification automatique de clôture est désactivée par la configuration de la fonction. Les messages fournisseurs ne contiennent pas de demande de satisfaction. Les destinataires, le texte et les pièces jointes restent à vérifier avant envoi.

Cockpit de production
https://amf.libracore.ch/production-tracking-planning
L'aperçu affiche des résumés et des files assemblage/usinage plus lisibles. Le planning ajoute des filtres rapides, une répartition par machine et un accès aux lignes modifiées, avec colonnes épinglées et textes agrandis sur ordinateur. Les jours estimés reflètent le travail enregistré, sans constituer une mesure de capacité machine; la page stockée en base doit être rafraîchie après déploiement des nouveaux modèles.

FFTest et formulaires
Le numéro de série du corps consommé est conservé sur le produit fini sérialisé. Les OF de composants utilisent leur lien vers l'OF parent et son projet, tandis que la commande client reste sur l'OF final, ce qui évite un rejet lorsqu'un composant n'est pas vendu directement. Les exports de personnalisation préservent aussi la disposition des formulaires après migration; le pays des nouveaux Contacts reste vide sauf valeur explicitement fournie.

Traçabilité matière et douanes
Une migration contrôlée rétablit les lots MAT.1021 depuis les réceptions et le stock initial jusqu'à la consommation chez le sous-traitant, sans ajuster les quantités, valorisations ni écritures comptables. La recherche du code douanier sur Delivery Note tolère désormais une destination sans colonne tarifaire configurée et retourne alors une valeur vide à traiter.

Bouchons NKN
Une migration crée ou vérifie les quatre articles `700070` à `700073` et leurs BOM, avec une consommation de 0,04 m de barre PEEK par pièce. Les PDF peuvent être importés comme pièces jointes privées après contrôle d'intégrité. La révision du dessin NKN.2024 reste à confirmer avant activation dans le registre; cette migration ne crée ni OF ni mouvement de stock.

Ce que cela signifie pour vous:

- Les équipes commerciales et finance peuvent rapprocher les vues Sales Analytics de leurs factures, commandes et livraisons, puis vérifier les droits sur les détails et exports.
- Les utilisateurs doivent préparer et envoyer volontairement les confirmations et clôtures; fermer une Issue seul ne déclenche pas son email. Les liens de satisfaction nécessitent le déploiement du formulaire sur le serveur public.
- Les responsables production peuvent vérifier le cockpit et les nouveaux cas FFTest après mise à jour de la page et des processus applicatifs.
- Les équipes stock et ingénierie sont invitées à contrôler la chaîne de lots MAT.1021, les recettes NKN et les révisions de dessins après migration.
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
