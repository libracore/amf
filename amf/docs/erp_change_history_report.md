# AMF ERP Release Notes

Generated on: 2026-09-03

Change history through: 2026-09-03

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

Latest release: `v2026.09.1`

Release status: Ready for validation

Release audience: AMF ERP users, department leads, management, operations, finance, logistics, quality, sales and support teams.

## Purpose

This document is the business-facing release notes and change history for the AMF ERP custom app.

It summarizes the main ERP changes developed in the AMF custom app from the beginning of the recorded development history to 2026-09-03. The report is based on the `apps/amf` git history, which starts on 2022-09-19, and on the current AMF app structure, including custom DocTypes, reports, pages, hooks and documentation.

This is intentionally not a technical commit-by-commit changelog. It is a release communication document for the main modifications, novelties and functional areas added over time. Standard Frappe and ERPNext framework changes are not listed unless they were reflected in AMF custom development.

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
| `v2026.09.1` | Ready for validation, latest | 2026 Q3 to date | Organizational Modification Request governance, Sales Order and commercial-invoice printing, focused Weekly Operations KPIs and a guarded RVM.3300 stock-history correction. |
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

## Latest Release: `v2026.09.1`

Release date: 2026-09-03

Release status: Ready for validation

Committed change window: 2026-08-26 to 2026-09-03

Live version: [https://amf.libracore.ch/desk#](https://amf.libracore.ch/desk#)

### Summary

This release introduces a controlled Organizational Modification Request workflow for significant and major company changes. Teams can document the proposed change, affected domains, risks, preventive controls, implementation actions and effectiveness criteria, then route it through change-responsible, Quality and—when required—General Management approval before implementation and closure.

Customer documents also become more consistent. `Standard Branding AMF 2026` is now the default Sales Order print format and presents customer/order references, billing and shipping details, item delivery dates, remaining quantities, prices, totals and commercial text in a structured layout. The Delivery Note commercial invoice letterhead handling was simplified to prevent it from behaving like a repeating PDF header.

Weekly Operations reporting is now deliberately narrower and manually distributed: production output considers only Sales Orders classified as `Production`, `GX` items are excluded from selected delivery/QC indicators, and scheduled report generation no longer sends the slide automatically. A guarded migration also corrects the duplicate RVM.3300 receipt `PREC-02960` and its downstream batch allocations while preserving the valid physical stock history.

### Highlights

- Added the submittable Organizational Modification Request (OMR) workflow for `C2 - Significant` and `C3 - Major` changes.
- Added structured change-type and impact assessment, risk/failure analysis, pre-implementation controls, training/documentation requirements and effectiveness-review planning.
- Added an implementation action table with named owners, due dates, completion tracking and controls preventing implementation while actions remain incomplete.
- Added approval decisions and electronic visas for the change owner and Quality, with an additional General Management approval required for C3 changes.
- Added post-submit implementation and effectiveness closure stages, including automatic statuses and an optional follow-up Issue when a change is not effective.
- Added a controlled French OMR PDF (`AMF.0053`) and an AMF module link for direct access to modification requests.
- Added `Standard Branding AMF 2026` for Sales Orders and made it the default print format after migration.
- Synchronized the AMF Sales Order, Sales Order Item and Payment Schedule customizations needed by the new print and existing order workflows.
- Adjusted Delivery Note commercial-invoice letterhead rendering to keep the letterhead with the document body instead of configuring it as a repeatable PDF header.
- Restricted Weekly Operations output-versus-plan data to `Production` Sales Orders and excluded `GX` items from On Time Delivery and incoming-QC inventory calculations.
- Changed Weekly Operations slide distribution to manual email only; scheduled generation continues to create the report files without automatically emailing recipients.
- Added an assertion-guarded, idempotent migration to remove duplicate Purchase Receipt `PREC-02960`, reassign valid RVM.3300 consumption and split later batch usage correctly between the valid receipts.
- Added or updated automated coverage for OMR validation/lifecycle rules and the revised Weekly Operations data and email behavior.

### Change Notes

| Area | Change | Brief Explanation |
| --- | --- | --- |
| Organizational change control | OMR lifecycle introduced. | The new Organizational Modification Request records C2/C3 changes from proposal through impact and risk assessment, implementation planning, approval, execution, effectiveness review and Quality closure. Its status progresses automatically through Draft, approval outcome, Effectiveness Review and Closed states. |
| OMR scope and risk | Required governance fields added. | Requesters must identify at least one change type and impacted domain, explain the change and its purpose, document what could fail, define preventive controls and state how effectiveness will be verified. Conditional fields capture training, documentation and non-standard review periods when applicable. |
| OMR actions and approvals | Controlled execution gates added. | Each implementation action has a responsible user, due date and completion record, and actions must be complete before an actual implementation date can be recorded. Submission requires the decision and applicable signed approvals; C3 changes additionally require a General Management visa. |
| OMR effectiveness and closure | Post-implementation review added. | Submitted requests remain updateable for the actual implementation and effectiveness review. An ineffective result requires additional actions and can link to a formal Issue; completed closure requires the Quality reviewer, result, decision, date and signature. |
| OMR output and navigation | Controlled document and module link added. | A French `AMF.0053 - Organizational Modification Request` PDF mirrors the governed form and is available from a dedicated Print action. The AMF module exposes the OMR list so users can access the workflow directly. |
| Sales Order printing | 2026 customer format made default. | The new branded format combines order status and dates, customer PO, AMF contact, billing/shipping addresses, introduction, delivery dates, ordered/remaining quantities, discounts, totals, terms and closing text. A migration installs or refreshes it and sets it as the Sales Order default. |
| Sales Order fixtures | Existing AMF customizations synchronized. | Sales Order, Sales Order Item and Payment Schedule fields/property settings used by printing and operations are now committed as migration fixtures. This includes customer PO/contact data, shipping controls, order type, remaining quantities, display options and payment-schedule labeling. |
| Commercial invoice printing | Letterhead behavior corrected. | The Delivery Note commercial invoice now renders the letterhead once as part of the document layout with controlled spacing. This avoids unintended repeated-header behavior and keeps the first-page composition stable. |
| Weekly Operations scope | Production and `GX` filters tightened. | Output-versus-plan now counts only Sales Orders explicitly classified as `Production`. `GX` item codes are excluded from the On Time Delivery dataset and incoming-QC stock backlog so the slide reflects the intended operational scope. |
| Weekly Operations distribution | Automatic scheduled email removed. | Scheduled generation still creates the Weekly Operations Report PDF/PNG, but no longer sends it automatically. Recipients and subject settings remain available for intentional manual sending of a generated slide. |
| Stock history correction | Duplicate RVM.3300 receipt repaired. | The migration validates exact receipts, batches, quantities and downstream Stock Entries before changing anything. It reassigns consumption to the correct `PREC-02868` batch, allocates 67 later-used units to `PREC-02979`, removes duplicate `PREC-02960` and verifies the expected remaining stock. |

### User Impact

- No separate user installation action is required after the migration is deployed.
- Requesters and Quality managers gain one auditable place to prepare, approve, implement and close significant organizational, process, supplier, production, documentation or ERP/IT changes.
- C3 requests require General Management approval; implementation cannot be recorded until all planned actions are marked complete.
- Sales users receive a clearer default Sales Order document with delivery, remaining-quantity and commercial information grouped for customer review.
- Operations managers should expect Weekly Operations output and delivery indicators to change because only Production orders and the intended non-`GX` scope are now counted.
- Weekly slides are not emailed by scheduled generation; an authorized user must deliberately send a generated report.
- The RVM.3300 repair is limited to the named receipts and exact validated stock records; it aborts if the live state differs from the expected history.

### Validation Notes

Recommended post-release checks:

- Create one C2 and one C3 OMR, verifying mandatory scope/impact fields, action due-date rules, approval signatures and the additional General Management requirements for C3.
- Submit an approved OMR, complete its actions, record implementation and exercise both effective and ineffective closure paths, including a follow-up Issue where justified.
- Generate the `AMF.0053` PDF and confirm the French content, signatures, selected change/impact boxes, action plan and closure data remain legible across pages.
- Print representative draft and submitted Sales Orders with taxes, discounts, long descriptions and remaining quantities, confirming `Standard Branding AMF 2026` is the default.
- Print a Delivery Note commercial invoice with a letterhead and confirm the letterhead appears once with correct first-page spacing.
- Generate a Weekly Operations Report and reconcile output/plan, On Time Delivery and QC backlog values against Production-only and non-`GX` expectations; verify scheduled generation sends no email.
- After migration, confirm `PREC-02960` and its obsolete batch are removed, the valid receipt/invoice remain submitted, RVM.3300 WIP is zero and 33 units remain in the overflow batch in Main Stock.

## Executive Summary

Since the beginning of development, the AMF ERP has evolved from a custom reporting and page layer into a broader operational system covering manufacturing, planning, inventory, purchasing, logistics, sales, CRM, quality, finance support and management reporting.

The main evolution areas are:

- Production planning, Work Order automation and manufacturing follow-up.
- Tool maintenance planning, preventive maintenance status and intervention history.
- Item, BOM and product master creation, governed descriptions, purchased-part classification and custom-item review controls.
- QR code, barcode, label and production sticker generation.
- Inventory visibility, safety stock, stock forecasting and replenishment support.
- Purchasing and procurement follow-up.
- Delivery Note, shipping, DHL tracking, DHL shipment creation and logistics tools.
- CRM, contact management, sales actions, campaign lists and external form/email integrations.
- Quality inspection, process-owned Issue classification, organizational change control, customer feedback and satisfaction surveys.
- Finance and compliance support such as VAT, HS codes, customs values, landed cost, custom ledgers and PostFinance reconciliation.
- Operational dashboards, KPI reporting and AI-assisted reporting.
- Weekly operations slide reporting with controlled production, delivery, QC and shipping scope.
- Customer-facing Sales Order, Loan Order, Delivery Note and commercial-invoice document formats.
- User interface improvements, document hooks, automation scripts and administrative utilities.

## Release History

### 2026 - Advanced Planning, Finance, Compliance, Dashboards And AI Reporting

#### `v2026.09.1` - 2026 Q3 To Date - Latest

- Organizational Modification Request and Organizational Modification Action DocTypes added for controlled C2 significant and C3 major changes.
- OMR preparation covers the proposed change, motivation, change types, impacted domains, failure risks, preventive controls, training/documentation needs and effectiveness criteria.
- Named implementation actions now carry responsible users, deadlines, completion flags and completion dates; all actions must be complete before implementation can be recorded.
- Submission requires an approval decision plus change-responsible and Quality signatures, while C3 changes also require General Management approval.
- Submitted OMRs support actual implementation, effectiveness review and Quality closure, with automatic statuses and mandatory additional actions when a change is not effective.
- French controlled print format `AMF.0053 - Organizational Modification Request` added with a dedicated PDF button and direct access from the AMF module.
- Sales Order custom fields and property fixtures synchronized so customer PO, AMF contact, shipping, order-type, remaining-quantity, display and payment-schedule configuration migrate consistently.
- `Standard Branding AMF 2026` Sales Order format added and set as the default, presenting customer/order details, delivery dates, remaining quantities, pricing, totals, terms and commercial messages.
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
- Guarded correction tooling for the duplicate RVM.3300 receipt and its downstream batch/ledger history.

### Item, BOM And Product Master

- Item Master, Product Master and Item Creation workflows.
- BOM creation, P202-O BOM creation, BOM child updates, pump BOM updates, 4B/4C repairs and recursive BOM updates.
- Governed customer, customs and internal production descriptions for Product Items.
- Evidence-based descriptions and stable child-group classification for purchased physical items.
- Custom Valve Head propagation and R&D review controls for custom Products in selling documents.
- Item valuation from BOM costs.
- Drawing match and component drawing register support.
- Tool-only Item maintenance fields and automatic maintenance summaries.
- Item pricing and item category controls.

### Logistics And Delivery

- Delivery Note API and Delivery Note customizations.
- Serial-number transfer to Delivery Notes.
- DHL export, tracking and MyDHL Express shipment creation.
- Logistics tracking page and tracking settings.
- Delivery Note commercial invoice and packaging branding print formats, including single-letterhead commercial-invoice rendering.
- Sales Order to Delivery Note lead-time reporting.
- Loan Order support, document links and commercial settlement invoicing.

### CRM, Sales And Marketing

- Master CRM module introduced.
- Contact enhancements, statuses, duplicate prevention and customer linking.
- Sales actions, sales activities, sales journey and quotation workflow.
- Custom-item warnings on Quotations and Sales Orders requiring R&D review.
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
- Issue outcomes separated from classifications, with inactive legacy types retained for historical records.
- Root cause and quality investigation support.
- Organizational Modification Requests with C2/C3 risk assessment, approvals, implementation actions, effectiveness review and Quality closure.

### Finance, Compliance And Administration

- AMF-specific General Ledger reporting.
- Swiss VAT handling.
- HS Code and customs tariff support.
- Customs-oriented Delivery Note commercial invoice output.
- Landed Cost Voucher-related behavior.
- Sales Invoice custom behavior.
- Bank reconciliation automation with multi-account and single-account PostFinance CSV support.
- Expense claim and administrative scripts.

### Reporting, Dashboards And AI

- Operational, sales, procurement, stock, production, delivery and quality reports added over time.
- SCM, quotation, global inventory, operations KPI and planning dashboards introduced or improved.
- Weekly Operations Report slides with Production-order scope, non-`GX` delivery/QC filters and manual email distribution.
- AI-assisted operations reporting added with controlled evidence-backed insights.
- Document AI import structures added for document parsing and extraction workflows.

### User Experience And Technical Enablement

- Custom pages, common JavaScript utilities and UI refinements added.
- DHL Shipment form actions for draft building, product lookup, validation and AWB creation.
- Loan Order customer print format and print-time address, contact and description preparation.
- Sales Order 2026 branded print format and controlled French OMR PDF generation.
- Barcode, DataMatrix, QR code and label infrastructure expanded.
- Web pages and generated documents for planning, item information, logistics, print formats and document tooling added.
- Hooks, migrations, settings DocTypes and background utilities added to automate operational behavior, including Tool maintenance lifecycle updates, BOM repair workflows, DHL Shipment setup and weekly report settings.

## Current Main Custom Objects

The current AMF custom app includes custom objects for planning, item creation, Weekly Operations Reports, Organizational Modification Requests and Actions, Tool Maintenance Plans, Tool Maintenance Logs, global quality inspection, timer production, DHL tracking, loan orders, issue management, AMF Issue Processes, Document AI imports, HS codes, customer feedback, CRM forms, Brevo campaigns, sales actions and satisfaction surveys. It also includes utility layers for Product and purchased-item descriptions, custom-item governance, Issue classification, OMR setup/printing, Loan Order settlement and printing, Sales Order branding, DHL Shipment creation, BOM family repair, recursive BOM updates, Delivery Note print formats, batch setup and guarded stock-history correction.

The current report catalog includes operational reports for inventory turnover, stock and revenue, produced and delivered items, purchased versus manufactured items, delivered items, purchase order items, late purchases, purchase order cash forecasting, projected stock, sales dashboards, quotation dashboards, manufacturing yield, machined parts, item margins, no-price items, leave balances, AMF general ledger, Sales Order to Delivery Note lead time and weekly operations slide reporting.

The current page catalog includes inventory planning, sales order stock projection, logistics tracking, global inventory dashboard, Tool Maintenance, component drawing register, bank reconciliation automation, order confirmation parsing, PDF text extraction and file upload tools.

## Release Maintenance Workflow

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

Objet: AMF ERP - Version v2026.09.1 - Modifications organisationnelles, impressions et KPI OPS

Bonjour à toutes et à tous,

La dernière version AMF ERP, v2026.09.1, est prête pour validation dans le système live:

AMF ERP live
https://amf.libracore.ch/desk#

Cette version introduit un processus contrôlé pour les demandes de modification organisationnelle, modernise l'impression des Sales Orders et précise le périmètre du reporting hebdomadaire OPS. Elle comprend également une correction sécurisée de l'historique de stock RVM.3300.

Principaux changements:

Organizational Modification Request
https://amf.libracore.ch/desk#List/Organizational%20Modification%20Request/List
Le nouveau formulaire OMR encadre les changements significatifs C2 et majeurs C3 depuis la demande jusqu'à la clôture Qualité. Il documente les impacts, risques, mesures préventives, actions avec responsables et échéances, critères d'efficacité et visas requis; les changements C3 demandent aussi l'approbation de la Direction Générale.

Mise en œuvre et clôture OMR
https://amf.libracore.ch/desk#List/Organizational%20Modification%20Request/List
Toutes les actions planifiées doivent être terminées avant d'enregistrer la mise en œuvre effective. La revue d'efficacité et la clôture sont ensuite documentées dans le même dossier, avec actions complémentaires obligatoires et lien possible vers une Issue si le changement n'est pas maîtrisé.

Impression Sales Order
https://amf.libracore.ch/desk#List/Sales%20Order/List
Le format `Standard Branding AMF 2026` devient le format d'impression par défaut. Il regroupe le statut, les références client, les adresses, les dates de livraison, les quantités commandées et restantes, les prix, taxes, totaux, conditions et messages commerciaux dans un document client plus lisible.

Facture commerciale Delivery Note
https://amf.libracore.ch/desk#List/Delivery%20Note/List
Le letterhead de la facture commerciale est maintenant placé une seule fois dans le corps du document avec un espacement contrôlé. Cette adaptation évite sa répétition comme en-tête PDF et stabilise la présentation de la première page.

Weekly Operations Report
https://amf.libracore.ch/desk#List/Weekly%20Operations%20Report/List
Le calcul Output vs Plan utilise désormais uniquement les Sales Orders de type Production, et les articles GX sont exclus des indicateurs On Time Delivery et du backlog QC entrant. La génération planifiée crée toujours les fichiers PDF/PNG, mais leur envoi email devient exclusivement manuel.

Correction stock RVM.3300
Une migration contrôlée corrige le doublon `PREC-02960` et réattribue les consommations aux réceptions valides `PREC-02868` et `PREC-02979`. Elle vérifie les documents, lots, quantités et mouvements attendus avant toute modification, puis contrôle le stock final et s'arrête si l'historique ne correspond pas exactement aux hypothèses validées.

Ce que cela signifie pour vous:

- Les demandeurs et l'équipe Qualité sont invités à tester un OMR C2 et un OMR C3, y compris les signatures, actions, mise en œuvre et clôture.
- L'équipe Sales est invitée à imprimer plusieurs Sales Orders représentatifs avec le nouveau format par défaut.
- Les responsables opérations sont invités à rapprocher les nouveaux KPI hebdomadaires avec les Sales Orders Production et à confirmer qu'aucun email n'est envoyé automatiquement.
- La facture commerciale Delivery Note doit être vérifiée avec letterhead sur un document de plusieurs pages.
- Après migration, l'équipe stock/finance doit confirmer la suppression de `PREC-02960`, l'intégrité des documents valides et le solde attendu de 33 unités RVM.3300.
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
