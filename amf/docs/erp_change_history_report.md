# AMF ERP Release Notes

Generated on: 2026-08-19

Change history through: 2026-08-18

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

Latest release: `v2026.08.3`

Release status: Ready for validation

Release audience: AMF ERP users, department leads, management, operations, finance, logistics, quality, sales and support teams.

## Purpose

This document is the business-facing release notes and change history for the AMF ERP custom app.

It summarizes the main ERP changes developed in the AMF custom app from the beginning of the recorded development history to 2026-08-18. The report is based on the `apps/amf` git history, which starts on 2022-09-19, and on the current AMF app structure, including custom DocTypes, reports, pages, hooks and documentation.

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
| `v2026.08.3` | Ready for validation, latest | 2026 Q3 to date | Loan Order commercial settlement, DHL Express shipment creation, Delivery Note commercial invoice and packaging formats, Weekly Operations Report slides and legacy weekly email cleanup. |
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

## Latest Release: `v2026.08.3`

Release date: 2026-08-19

Release status: Ready for validation

Committed change window: 2026-08-14 to 2026-08-18

Live version: [https://amf.libracore.ch/desk#](https://amf.libracore.ch/desk#)

### Summary

This release extends Loan Orders into a complete commercial settlement workflow. After loaned equipment is with the customer, users can record the customer decision, create a draft settlement Sales Invoice, and generate the supporting stock or delivery documents needed to close the loan cleanly.

It also introduces a cautious DHL Express shipment workflow for submitted DHL Delivery Notes. ERPNext can now prepare a DHL Shipment draft, fetch available DHL transport products, validate the exact payload with MyDHL, and create the AWB only after the validated payload is still unchanged and the operator confirms the action.

Operational reporting and document output also move forward. A new Weekly Operations Report creates a 16:9 production and supply slide as PDF/PNG, while Delivery Note printing gains updated commercial invoice and packaging formats for customs and shipping review.

### Highlights

- Added Loan Order settlement invoicing for customer decisions such as `Spare Parts Only` and `Full Product Purchase`.
- Added settlement stock/logistics documents for Loan Orders, including full-sale Delivery Notes, spare-part sale Delivery Notes, remaining-item return Delivery Notes and value-neutral repack Stock Entries.
- Added Sales Invoice, Delivery Note and Stock Entry backlinks so Loan Order settlement documents remain traceable from the originating Loan Order and item rows.
- Added DHL Express Shipment creation from submitted DHL Delivery Notes, including local draft building, product lookup, remote validation and confirmation-gated AWB creation.
- Added DHL audit controls: payload fingerprints, Test/Production environment tracking, message references, creation status, piece tracking numbers and private attachment of returned labels/documents.
- Added 2026 Delivery Note print formats for commercial invoices and packaging branding, with installer patches and updated Delivery Note print-button routing.
- Added Weekly Operations Report DocType and generation utilities for a one-slide production and supply snapshot covering delivery performance, overdue orders, machining, Work Orders, QC backlog and shipping.
- Added weekly report settings, manual generation from Operations KPI Report Settings, optional weekly email distribution and scheduled defaults.
- Disabled legacy weekly open-issue and standard-item availability email reports so the new reporting workflow becomes the controlled reporting path.
- Refined the 2026 packaging print layout so item sections, images and serial tables fit more compactly on the generated document.

### Change Notes

| Area | Change | Brief Explanation |
| --- | --- | --- |
| Loan Order settlement | Commercial decision workflow added. | Submitted customer Loan Orders can now move from temporary stock movement to settlement. Users choose `Spare Parts Only` or `Full Product Purchase`, and ERPNext prepares a draft invoice from the Loan Order quantities, roles and price list. |
| Loan Order stock flow | Settlement support documents added. | A full purchase creates a settlement Delivery Note for the sold items. A spare-parts-only settlement dismantles loaned products through a value-neutral Repack, invoices the spare parts and prepares a return Delivery Note for the remaining components. |
| Loan Order traceability | Backlinks and status sync added. | Sales Invoices, Sales Invoice Items, Delivery Notes and Stock Entries now carry Loan Order references where relevant. The Loan Order keeps links to the created settlement documents and updates its status when commercial settlement is complete. |
| DHL shipment creation | MyDHL Express workflow added. | Submitted non-return Delivery Notes whose carrier contains `DHL` can create an ERPNext Shipment draft. The workflow builds the DHL payload, fetches available transport products, validates data remotely and only then allows AWB creation. |
| DHL audit and safeguards | Validation boundary added. | The exact validated payload and MyDHL environment are fingerprinted before creation. Unknown creation outcomes block automatic retries, and request identifiers, tracking numbers, DHL responses and returned labels are retained for audit follow-up. |
| Delivery Note printing | 2026 print formats added. | Delivery Notes now have enhanced commercial invoice and packaging branding formats. The commercial invoice format emphasizes customs fields such as origin, HS code, net weight and totals, while packaging output was tuned for denser item/serial presentation. |
| Weekly operations reporting | Weekly slide report added. | The new Weekly Operations Report stores generated PDF/PNG outputs and a JSON data snapshot. It collects live ERP data for production, delivery, QC and shipping so management can review a repeatable weekly operational picture. |
| Report distribution | Weekly settings and email controls added. | Operations KPI Report Settings now includes weekly slide configuration, row limits, lookback/lookahead windows, QC backlog thresholds, manual generation and optional scheduled email recipients. |
| Legacy email cleanup | Old weekly reports disabled. | The older weekly open-issue and standard-item availability email functions now return disabled status instead of sending mail. This prevents parallel report emails from continuing beside the new Weekly Operations Report workflow. |

### User Impact

- No separate user installation action is required after the migration is deployed.
- Loan Order users get a guided settlement path instead of manually assembling invoices, repacks and return documents.
- Sales and finance teams can trace settlement invoices and related stock/logistics documents back to the originating Loan Order.
- Logistics/export users can build and validate DHL Shipments from ERPNext before creating an AWB, with clearer audit data when DHL accepts, rejects or leaves an outcome uncertain.
- Delivery Note users get refreshed commercial invoice and packaging outputs for customs, parcel preparation and customer-facing shipment documentation.
- Operations managers can generate a weekly production and supply slide from live ERP data and control whether it is emailed automatically.
- Legacy weekly email reports stop sending, reducing duplicate operational report traffic.

### Validation Notes

Recommended post-release checks:

- Create or open a submitted customer Loan Order and validate both `Spare Parts Only` and `Full Product Purchase` settlement paths on representative examples.
- Confirm the Loan Order keeps links to its settlement Sales Invoice, Delivery Notes and Repack Stock Entry where applicable.
- Create a DHL Shipment draft from a submitted DHL Delivery Note, build the local draft, fetch transport products and validate with MyDHL in the Test environment before any Production AWB creation.
- Print one representative Delivery Note with the 2026 commercial invoice and packaging formats, checking customs fields, totals, item images and serial-number layout.
- Generate a Weekly Operations Report manually from Operations KPI Report Settings and confirm both the PDF and PNG slide outputs are attached.
- Confirm the legacy weekly open-issue and standard-item availability email functions return disabled status and do not send mail.

## Executive Summary

Since the beginning of development, the AMF ERP has evolved from a custom reporting and page layer into a broader operational system covering manufacturing, planning, inventory, purchasing, logistics, sales, CRM, quality, finance support and management reporting.

The main evolution areas are:

- Production planning, Work Order automation and manufacturing follow-up.
- Tool maintenance planning, preventive maintenance status and intervention history.
- Item, BOM and product master creation and maintenance.
- QR code, barcode, label and production sticker generation.
- Inventory visibility, safety stock, stock forecasting and replenishment support.
- Purchasing and procurement follow-up.
- Delivery Note, shipping, DHL tracking, DHL shipment creation and logistics tools.
- CRM, contact management, sales actions, campaign lists and external form/email integrations.
- Quality inspection, issue management, customer feedback and satisfaction surveys.
- Finance and compliance support such as VAT, HS codes, customs values, landed cost and custom ledgers.
- Operational dashboards, KPI reporting and AI-assisted reporting.
- Weekly operations slide reporting for production, supply, QC and shipping follow-up.
- User interface improvements, document hooks, automation scripts and administrative utilities.

## Release History

### 2026 - Advanced Planning, Finance, Compliance, Dashboards And AI Reporting

#### `v2026.08.3` - 2026 Q3 To Date - Latest

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
- Gravity Forms integration for external form entry handling.
- Brevo integration, campaign lists, campaign synchronization and contact statistics.
- Customer, referral and satisfaction survey features.

### Quality And Issue Management

- Global Quality Inspection and related inspection tables.
- Automatic Quality Inspection generation for batches and Work Orders.
- Drawing-based inspection support.
- Preventive Tool maintenance plans and maintenance intervention history.
- Customer Feedback and satisfaction scoring.
- Issue management workflows and ISO-oriented documentation.
- Root cause and quality investigation support.

### Finance, Compliance And Administration

- AMF-specific General Ledger reporting.
- Swiss VAT handling.
- HS Code and customs tariff support.
- Customs-oriented Delivery Note commercial invoice output.
- Landed Cost Voucher-related behavior.
- Sales Invoice custom behavior.
- Bank reconciliation automation.
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
- Barcode, DataMatrix, QR code and label infrastructure expanded.
- Web pages and generated documents for planning, item information, logistics, print formats and document tooling added.
- Hooks, migrations, settings DocTypes and background utilities added to automate operational behavior, including Tool maintenance lifecycle updates, BOM repair workflows, DHL Shipment setup and weekly report settings.

## Current Main Custom Objects

The current AMF custom app includes custom objects for planning, item creation, Weekly Operations Reports, Tool Maintenance Plans, Tool Maintenance Logs, global quality inspection, timer production, DHL tracking, loan orders, issue management, Document AI imports, HS codes, customer feedback, CRM forms, Brevo campaigns, sales actions and satisfaction surveys. It also includes utility layers for Loan Order settlement, DHL Shipment creation, BOM family repair, recursive BOM updates, Delivery Note print formats and batch setup.

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

Objet: AMF ERP - Version v2026.08.3 - Loan Orders, DHL et reporting OPS

Bonjour à toutes et à tous,

La dernière version AMF ERP, v2026.08.3, est prête pour validation dans le système live:

AMF ERP live
https://amf.libracore.ch/desk#

Cette version concerne principalement le règlement commercial des Loan Orders, la création d'expéditions DHL Express, les nouveaux formats d'impression Delivery Note et le nouveau reporting hebdomadaire OPS.

Principaux changements:

Loan Orders
https://amf.libracore.ch/desk#List/Loan%20Order/List
Les Loan Orders client soumis peuvent maintenant créer une facture de règlement selon la décision client: Spare Parts Only ou Full Product Purchase. Le flux prépare aussi les documents de stock ou de livraison nécessaires pour solder correctement le prêt.

DHL Express
https://amf.libracore.ch/desk#List/Shipment/List
Une Delivery Note DHL soumise peut maintenant préparer une Shipment ERPNext, récupérer les produits de transport DHL, valider les données avec MyDHL et créer l'AWB après confirmation explicite. Les validations, empreintes de payload, références DHL, numéros de suivi et documents retournés sont conservés pour audit.

Formats Delivery Note
https://amf.libracore.ch/desk#List/Delivery%20Note/List
De nouveaux formats 2026 améliorent la facture commerciale douanière et le branding packaging. Ils mettent mieux en avant l'origine, le code HS, les poids, les totaux et les informations articles/séries pour la préparation d'expédition.

Weekly Operations Report
https://amf.libracore.ch/desk#List/Weekly%20Operations%20Report/List
Un nouveau rapport hebdomadaire génère une slide 16:9 en PDF et PNG pour suivre production, supply, QC et expéditions. La génération peut être lancée manuellement depuis Operations KPI Report Settings et dispose d'une distribution email optionnelle.

Anciens emails hebdomadaires
Les anciens rapports email Weekly Open Issues et Weekly Availability of Standard Items sont désactivés afin d'éviter des emails parallèles non contrôlés à côté du nouveau reporting OPS.

Ce que cela signifie pour vous:

- Les équipes sales et finance sont invitées à valider un règlement Loan Order Spare Parts Only et un Full Product Purchase sur des cas représentatifs.
- Les équipes logistique/export sont invitées à tester la création DHL en environnement Test avant toute création AWB en Production.
- Les utilisateurs Delivery Note sont invités à contrôler une facture commerciale et un document packaging générés avec les nouveaux formats.
- Les responsables opérations peuvent générer une Weekly Operations Report et vérifier la slide PDF/PNG avant activation d'une distribution email.
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
