# AMF ERP Release Notes

Generated on: 2026-08-25

Change history through: 2026-08-25

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

Latest release: `v2026.08.4`

Release status: Ready for validation

Release audience: AMF ERP users, department leads, management, operations, finance, logistics, quality, sales and support teams.

## Purpose

This document is the business-facing release notes and change history for the AMF ERP custom app.

It summarizes the main ERP changes developed in the AMF custom app from the beginning of the recorded development history to 2026-08-25. The report is based on the `apps/amf` git history, which starts on 2022-09-19, and on the current AMF app structure, including custom DocTypes, reports, pages, hooks and documentation.

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
| `v2026.08.4` | Ready for validation, latest | 2026 Q3 to date | Governed Product and purchased-item descriptions, Loan Order printing, PostFinance import compatibility, custom-item R&D review controls and process-owned Issue classification. |
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

## Latest Release: `v2026.08.4`

Release date: 2026-08-25

Release status: Ready for validation

Committed change window: 2026-08-19 to 2026-08-25

Live version: [https://amf.libracore.ch/desk#](https://amf.libracore.ch/desk#)

### Summary

This release strengthens master-data quality by standardizing the customer-facing, customs and internal descriptions used for finished Products and purchased physical items. Product descriptions are derived from their configured body, valve head, syringe and preferred submitted BOM, while purchased-item descriptions combine ERP purchasing evidence, supplier references and reviewed catalog facts without discarding existing production notes.

Loan Order communication and finance workflows also improve. A dedicated customer-facing Loan Order print format presents the borrower, loan period, equipment, purpose, terms and declared values, and the PostFinance reconciliation importer now accepts both multi-account and single-account CSV exports as well as invoice references written with or without the normal dash.

Finally, the release adds two controlled review mechanisms. Custom Valve Heads propagate a `Custom Item` flag to Products and trigger a one-time R&D review warning in Quotations and Sales Orders. Issues now use a governed process, ownership and classification model with canonical active Issue Types, accountable owners, separate outcomes and user-confirmed subject suggestions.

### Highlights

- Standardized the three Item description layers for Product records: customer-facing sales content, concise customs wording and internal production detail based on the preferred active submitted BOM.
- Added a reviewed migration for active physical items with submitted purchase history, using supplier references and catalog evidence while preserving existing production notes.
- Added stable child groups under `Part` for clearer classification of fasteners, bearings, seals, fluidic components, electronics, custom mechanical parts and other purchased components.
- Added a dedicated Loan Order print format with borrower/contact details, loan dates, item descriptions, declared values, purpose and terms; the printed document now points to a separately shared and signed Loan Agreement.
- Extended PostFinance bank-statement parsing to accept single-account exports whose IBAN and currency are held in metadata and whose debit/credit columns include the currency.
- Normalized invoice references such as `SINV01641` and `SINV-01641` to the ERPNext document-name format during reconciliation and payment matching.
- Added a `Custom Item` control that propagates from custom Valve Heads through active default BOMs to finished Products.
- Added a non-repeating R&D review warning when a draft Quotation or Sales Order contains custom items; the warning is rearmed when the custom-item set changes.
- Added the `AMF Issue Process` setup object, canonical Issue Types, active/retired controls and automatic primary/secondary process-owner routing.
- Added up to three subject-based Issue Type suggestions on Issue and AMF Issue Test, using governed multilingual vocabulary and confirmed historical classifications while leaving the final selection to the user.
- Refined the Issue form so product/batch information and repair fields follow a clearer operational sequence, including visibility of the warranty indicator.

### Change Notes

| Area | Change | Brief Explanation |
| --- | --- | --- |
| Product descriptions | Three governed description layers generated. | Product Items receive structured customer-facing specifications from the configured product family, valve head and syringe, a DHL-safe customs description, and an internal production description from the preferred active submitted BOM. The migration validates its output and does not invent a BOM where none exists. |
| Purchased-item master data | Evidence-based descriptions and grouping added. | Active physical items with submitted purchase history are enriched from Item data, supplier part numbers, purchase documents and reviewed supplier/manufacturer sources. Existing production notes are preserved, non-physical placeholders are excluded and a compact CSV supports review and debugging. |
| Part classification | Stable purchased-part child groups added. | Purchased `Part` records can be assigned to controlled groups such as Fasteners, Bearings and Bushings, Fluidic Components, Electronic Components or Custom Mechanical Parts. Classification rules preserve an existing valid child group and use stable fallbacks for items without a stronger match. |
| Loan Order printing | Customer-facing print format installed. | Loan Orders now default to a structured print with borrower address/contact, start and return dates, equipment descriptions, quantities, purpose, terms and optional declared values. The final layout identifies the document as issued and refers to the separately signed Loan Agreement instead of embedding a signature block. |
| Bank reconciliation | Additional PostFinance CSV layout supported. | The importer now resolves both the existing multi-account export and a single-account format with IBAN/currency metadata and currency-qualified credit/debit columns. It verifies that the IBAN and currency match a configured supported account before importing transactions. |
| Invoice matching | Optional-dash references normalized. | Sales and Purchase Invoice references are recognized whether the bank text contains the normal dash or omits it. References are normalized before matching and the same flexible pattern is used when extracting Payment Entry check references. |
| Custom-item governance | Valve Head flags propagated to Products. | Marking a Valve Head as custom identifies Products whose active submitted default BOM directly contains it. The synchronization also runs when qualifying BOMs are submitted or updated and can backfill existing related Products after migration. |
| Sales review | R&D warning added to draft selling documents. | Saving a Quotation or Sales Order with custom items displays an orange R&D review message listing the affected references. A hidden acknowledgement prevents repetition for an unchanged item set but resets when custom items are removed or changed. |
| Issue classification | Process-owned taxonomy and routing added. | A new AMF Issue Process register defines process codes, scope and primary/secondary owners. Canonical Issue Types link to these processes, inactive legacy types are excluded from new selection, and the selected type routes the Issue to the accountable owner fields. |
| Issue suggestions | Governed user-confirmed recommendations added. | Issue and AMF Issue Test subjects can show up to three ranked active Issue Types using controlled English/French/German terminology and sufficiently confirmed historical examples. Suggestions explain their matching signals and never apply a classification until the user explicitly chooses one. |
| Issue form layout | Product and resolution sections reordered. | Product/item/batch details are brought forward, repair options are kept together and the `Under Guarantee` control is visible. This reduces navigation between scattered fields while preserving the existing Issue information. |

### User Impact

- No separate user installation action is required after the migration is deployed.
- Sales, customs and production users receive clearer Product and purchased-item descriptions drawn from controlled ERP and supplier evidence.
- Item-master reviewers should check generated descriptions and the new `Part` child-group assignments, especially any component that depends on a safe fallback rather than an exact researched catalog match.
- Loan Order users receive a consistent customer document with the relevant loan dates, equipment details and declared values; the Loan Agreement remains a separate signed document.
- Finance users can import the supported single-account PostFinance export and match compact invoice references that omit the dash.
- Sales users are warned when a Quotation or Sales Order needs R&D review because it contains a custom Product or Valve Head.
- Issue creators receive clearer active classifications and suggestions, while process owners gain explicit routing and accountability for triage and closure quality.

### Validation Notes

Recommended post-release checks:

- Review a representative pump, valve, special Product and Product without a BOM across the customer, customs and internal description fields.
- Review purchased items from several suppliers and Part categories, confirming that source facts are appropriate and existing internal production notes remain intact.
- Print draft and submitted Loan Orders with and without declared values, checking address/contact selection, dates, item descriptions, page layout and the separate Loan Agreement wording.
- Import one multi-account and one supported single-account PostFinance CSV, then verify invoice matching for references both with and without a dash.
- Mark a test Valve Head as custom, confirm the related default-BOM Product is flagged, and verify the R&D warning behavior on a draft Quotation and Sales Order.
- Create test Issues for several processes, confirm owner routing, verify retired Issue Types cannot be newly selected and review the subject suggestions before explicitly applying one.

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
- Quality inspection, process-owned Issue classification, customer feedback and satisfaction surveys.
- Finance and compliance support such as VAT, HS codes, customs values, landed cost, custom ledgers and PostFinance reconciliation.
- Operational dashboards, KPI reporting and AI-assisted reporting.
- Weekly operations slide reporting for production, supply, QC and shipping follow-up.
- User interface improvements, document hooks, automation scripts and administrative utilities.

## Release History

### 2026 - Advanced Planning, Finance, Compliance, Dashboards And AI Reporting

#### `v2026.08.4` - 2026 Q3 To Date - Latest

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
- Delivery Note commercial invoice and packaging branding print formats.
- Sales Order to Delivery Note lead-time reporting.
- Loan Order support, document links and commercial settlement invoicing.

### CRM, Sales And Marketing

- Master CRM module introduced.
- Contact enhancements, statuses, duplicate prevention and customer linking.
- Sales actions, sales activities, sales journey and quotation workflow.
- Custom-item warnings on Quotations and Sales Orders requiring R&D review.
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
- Weekly Operations Report slides with production, delivery, QC and shipping snapshots.
- AI-assisted operations reporting added with controlled evidence-backed insights.
- Document AI import structures added for document parsing and extraction workflows.

### User Experience And Technical Enablement

- Custom pages, common JavaScript utilities and UI refinements added.
- DHL Shipment form actions for draft building, product lookup, validation and AWB creation.
- Loan Order customer print format and print-time address, contact and description preparation.
- Barcode, DataMatrix, QR code and label infrastructure expanded.
- Web pages and generated documents for planning, item information, logistics, print formats and document tooling added.
- Hooks, migrations, settings DocTypes and background utilities added to automate operational behavior, including Tool maintenance lifecycle updates, BOM repair workflows, DHL Shipment setup and weekly report settings.

## Current Main Custom Objects

The current AMF custom app includes custom objects for planning, item creation, Weekly Operations Reports, Tool Maintenance Plans, Tool Maintenance Logs, global quality inspection, timer production, DHL tracking, loan orders, issue management, AMF Issue Processes, Document AI imports, HS codes, customer feedback, CRM forms, Brevo campaigns, sales actions and satisfaction surveys. It also includes utility layers for Product and purchased-item descriptions, custom-item governance, Issue classification, Loan Order settlement and printing, DHL Shipment creation, BOM family repair, recursive BOM updates, Delivery Note print formats and batch setup.

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

Objet: AMF ERP - Version v2026.08.4 - Descriptions articles, Loan Orders et classification Issues

Bonjour à toutes et à tous,

La dernière version AMF ERP, v2026.08.4, est prête pour validation dans le système live:

AMF ERP live
https://amf.libracore.ch/desk#

Cette version concerne principalement la qualité des descriptions articles, le nouveau format d'impression Loan Order, la compatibilité des imports PostFinance, le contrôle des articles custom et une classification des Issues basée sur les processus responsables.

Principaux changements:

Descriptions des Products et articles achetés
https://amf.libracore.ch/desk#List/Item/List
Les Products disposent maintenant de descriptions client, douanière et interne structurées à partir de leur configuration et de leur BOM active soumise. Les articles physiques achetés sont enrichis avec les références fournisseurs, l'historique d'achat et des sources catalogue contrôlées, tout en conservant les notes de production existantes.

Classification des pièces achetées
https://amf.libracore.ch/desk#Tree/Item%20Group
Les articles du groupe Part peuvent être répartis dans des sous-groupes stables, par exemple Fasteners, Bearings and Bushings, Fluidic Components, Electronic Components ou Custom Mechanical Parts. Cette structure facilite les recherches et les contrôles sans remplacer une classification existante déjà valide.

Impression Loan Order
https://amf.libracore.ch/desk#List/Loan%20Order/List
Un format client dédié présente l'emprunteur, les contacts, la période de prêt, les équipements, le but, les conditions et les valeurs déclarées si elles existent. Le document imprimé renvoie désormais au Loan Agreement transmis et signé séparément.

Réconciliation bancaire PostFinance
https://amf.libracore.ch/desk#bank-reconciliation-automation
L'import accepte les exports CSV multi-comptes et mono-compte PostFinance. Les références SINV/PINV sont aussi reconnues avec ou sans tiret, avec contrôle de cohérence entre l'IBAN, la devise et les comptes supportés avant l'import.

Articles custom et revue R&D
https://amf.libracore.ch/desk#List/Quotation/List
Un Valve Head marqué Custom Item propage ce statut aux Products concernés via leur BOM par défaut. Lorsqu'un devis ou une commande client contient un article custom, un avertissement orange demande une revue de configuration avec le département R&D sans se répéter tant que la liste des articles concernés reste identique.

Classification et routage des Issues
https://amf.libracore.ch/desk#List/Issue/List
Les Issues utilisent maintenant des types actifs et normalisés liés à un processus responsable et à ses propriétaires principal et secondaire. Jusqu'à trois suggestions sont proposées à partir du sujet et du vocabulaire contrôlé; l'utilisateur doit toujours choisir et appliquer explicitement la classification finale.

Ce que cela signifie pour vous:

- Les responsables articles sont invités à contrôler plusieurs descriptions Product et articles achetés, ainsi que les nouveaux sous-groupes Part.
- Les utilisateurs Loan Order sont invités à imprimer un brouillon et un document soumis, avec et sans valeurs déclarées.
- L'équipe finance est invitée à tester un export PostFinance mono-compte et les références de facture avec et sans tiret.
- Les équipes sales et R&D sont invitées à vérifier la propagation Custom Item et l'avertissement sur un devis ou une commande client.
- Les responsables de processus sont invités à contrôler le routage, les propriétaires et les suggestions sur plusieurs Issues représentatives.
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
