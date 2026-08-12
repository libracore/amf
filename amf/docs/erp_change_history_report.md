# AMF ERP Release Notes

Generated on: 2026-08-11

Change history through: 2026-08-11

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

Latest release: `v2026.08.1`

Release status: Ready for validation

Release audience: AMF ERP users, department leads, management, operations, finance, logistics, quality, sales and support teams.

## Purpose

This document is the business-facing release notes and change history for the AMF ERP custom app.

It summarizes the main ERP changes developed in the AMF custom app from the beginning of the recorded development history to 2026-08-11. The report is based on the `apps/amf` git history, which starts on 2022-09-19, and on the current AMF app structure, including custom DocTypes, reports, pages, hooks and documentation.

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
| `v2026.08.1` | Ready for validation, latest | 2026 Q3 to date | Tool-only maintenance planning, maintenance history, preventive maintenance dashboard, automatic Item maintenance summaries, P202-O BOM creation and receipt batch tracking for item `70E000`. |
| `v2026.07.1` | Published | 2026 Q3 | Procurement cash forecast, global inventory dashboard, issue management, item dashboards, component drawing register, bank reconciliation automation and serial-number tools. |
| `v2026.06.0` | Superseded | 2026 Q2 | Loan Orders, landed cost behavior, work order automation, KPI dashboards, procurement tools and AI-assisted reporting. |
| `v2026.03.0` | Superseded | 2026 Q1 | Swiss VAT handling, customs mapping, planning quantities, batch quantity retrieval and costing support. |
| `v0.7.0` | Superseded | 2025 Q4 | Production Tracking, Timer Production, automatic Quality Inspections, drawing-based QA and HS Code support. |
| `v0.6.5` | Superseded | 2025 Q2 | Satisfaction scoring, customer reporting, planning and rating reports, leave balances and ERPNext-related Stock Entry fixes. |
| `v0.6.0` / `v0.6.1` | Superseded | 2025 Q1 | Safety Stock, Work Order creation, labels, drawing matching, customer surveys and Global Quality Inspection. |
| `v0.4.0` | Superseded | 2024 Q3 | Master CRM, Sales Actions, campaign lists, Gravity Forms, Brevo integration and CRM analytics. |
| Foundation releases | Superseded | 2022-2024 | Core reporting, planning, labels, QR codes, inventory visibility, logistics, purchasing and CRM foundations. |

## Latest Release: `v2026.08.1`

Release date: 2026-08-11

Release status: Ready for validation

Live version: [https://amf.libracore.ch/desk#](https://amf.libracore.ch/desk#)

### Summary

This release adds a dedicated Tool Maintenance workflow inside AMF ERP and includes BOM creation support for P202-O products. Maintenance information is now attached directly to Item records when the Item Group is `Tool`, and the ERP includes dedicated maintenance plans, intervention logs and a maintenance planner page for daily follow-up.

The release is designed so maintenance status stays current when tools, plans or maintenance logs change. New Tool items are initialized automatically, recurring plans recalculate their next due date after interventions, completed one-time plans close automatically, and Item maintenance summary fields are refreshed through document hooks and a scheduled daily sync.

For product master data, the release also creates submitted default BOMs for the P202-O `4D` item family from validated P201-O/`42` BOM templates, with the body component updated to the P202-O body item.

The release also activates batch tracking for purchased syringe item `70E000` (`Syringe 2500-P uL`). Purchase Receipts for this item can now receive a newly generated Batch automatically on receipt submission, improving traceability for incoming syringe stock.

### Highlights

- Added a Tool-only maintenance section on Item records.
- Added Tool Maintenance Plan and Tool Maintenance Log DocTypes.
- Added the Tool Maintenance planner page at `/app/tool-maintenance`.
- Added Item form actions for Maintenance Planner, New Maintenance Plan and Log Intervention.
- Added BOM creation for P202-O products in the `4D` item family.
- Imported safe tool metadata from the maintenance spreadsheet where item matching was unambiguous.
- Added automatic refresh behavior when a Tool item, maintenance plan or maintenance log is created, changed, completed, moved or deleted.
- Added safeguards so Tool items with existing maintenance records cannot be silently moved out of the Tool item group.
- Added daily maintenance summary refresh so due and overdue statuses age correctly over time.
- Activated batch tracking and automatic per-receipt Batch creation for item `70E000`.

### Change Notes

| Area | Change | Brief Explanation |
| --- | --- | --- |
| Item master data | Tool-only maintenance fields added to Item. | Displays maintenance fields only for items in Item Group `Tool`, including serial number, equipment type, ownership, location, responsible employee, required PPE, calibration procedure, instructions, last maintenance, next maintenance, status and open/overdue plan counts. |
| Maintenance planning | Tool Maintenance Plan DocType added. | Lets users define preventive maintenance requirements for tools, including frequency, due dates, responsibility, status and plan instructions. |
| Maintenance execution | Tool Maintenance Log DocType added. | Records completed interventions, links work back to the related Tool item and maintenance plan, and updates last/next maintenance information. |
| Maintenance dashboard | Tool Maintenance page added. | Provides a dedicated planning page for reviewing Tool maintenance status, due and overdue work, plans and intervention history. |
| Product master data | P202-O BOM creation added. | Creates submitted default BOMs for P202-O `4D` finished goods from matching P201-O/`42` BOM templates and replaces the source body component with the P202-O body item `5D1000`. |
| ERP automation | Maintenance summaries refresh automatically. | Item maintenance summary fields are updated after Tool saves, plan changes and log changes, plus a scheduled daily refresh keeps due and overdue status current. |
| Data migration | Spreadsheet data mapped into Tool Item fields where safe. | Maintenance-related metadata from the spreadsheet was imported only when the Tool item match was unambiguous; conflicting or stale reused item codes were left untouched for manual review. |
| Data protection | Item Group changes are guarded. | A Tool item with existing maintenance plans or logs cannot be moved out of Item Group `Tool` without first resolving the linked maintenance history. |
| Purchase receipt traceability | Item `70E000` now creates Batches on receipt. | Enables batch tracking and automatic new Batch creation for `70E000` so each Purchase Receipt can create a receipt-specific Batch for the incoming syringe item. |

### User Impact

- No separate user installation action is required.
- Users should continue working in the live ERP system at [https://amf.libracore.ch/desk#](https://amf.libracore.ch/desk#).
- Maintenance-relevant fields appear on Item records only when the item belongs to Item Group `Tool`.
- New Tool items receive a maintenance summary automatically when saved.
- Maintenance users can create plans and log interventions from the Tool Item form or from the Tool Maintenance planner page.
- Recurring plans calculate their next due date from the latest completed intervention.
- Overdue and due statuses are visible both on Tool Item records and in the dedicated planner.
- P202-O `4D` products can receive validated default BOMs based on the corresponding P201-O product structure.
- Purchase Receipts for item `70E000` now support automatic Batch creation, so users do not need to create the receipt Batch manually when the document is submitted.

### Validation Notes

Recommended post-release checks:

- Open a Tool item and confirm the maintenance section is visible.
- Open a non-Tool item and confirm the maintenance section is hidden.
- Create a new Tool item and confirm the maintenance status initializes to `No Plan`.
- Create a maintenance plan for a Tool item and confirm the Item summary counts update.
- Log a completed intervention and confirm last maintenance, next maintenance and plan status update.
- Test one recurring plan and confirm the next due date moves according to the configured frequency.
- Confirm the Tool Maintenance page opens at [https://amf.libracore.ch/desk#tool-maintenance](https://amf.libracore.ch/desk#tool-maintenance).
- Review the spreadsheet import exceptions before manually entering maintenance data for conflicted item codes.
- Review a representative P202-O `4D` item and confirm its submitted default BOM uses body item `5D1000` with the expected remaining components from the corresponding P201-O template.
- Create or review a Purchase Receipt line for item `70E000` and confirm a Batch is generated on submission when the row has no manually selected Batch.

## Executive Summary

Since the beginning of development, the AMF ERP has evolved from a custom reporting and page layer into a broader operational system covering manufacturing, planning, inventory, purchasing, logistics, sales, CRM, quality, finance support and management reporting.

The main evolution areas are:

- Production planning, Work Order automation and manufacturing follow-up.
- Tool maintenance planning, preventive maintenance status and intervention history.
- Item, BOM and product master creation and maintenance.
- QR code, barcode, label and production sticker generation.
- Inventory visibility, safety stock, stock forecasting and replenishment support.
- Purchasing and procurement follow-up.
- Delivery Note, shipping, DHL tracking and logistics tools.
- CRM, contact management, sales actions, campaign lists and external form/email integrations.
- Quality inspection, issue management, customer feedback and satisfaction surveys.
- Finance and compliance support such as VAT, HS codes, customs values, landed cost and custom ledgers.
- Operational dashboards, KPI reporting and AI-assisted reporting.
- User interface improvements, document hooks, automation scripts and administrative utilities.

## Release History

### 2026 - Advanced Planning, Finance, Compliance, Dashboards And AI Reporting

#### `v2026.08.1` - 2026 Q3 To Date - Latest

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
- Production tracking with operator timers and Work Order QR access.
- Estimated manufacturing time and production cost/time tracking support.
- Tool maintenance planning, due-date tracking and intervention history.
- Machining reports and production stickers.

### Inventory, Stock And Procurement

- Inventory turnover, stock summary, projected stock and stock/revenue reporting.
- Safety stock, reorder level, stock forecasting and shortage visibility.
- Purchase Order checking, late purchase reporting and procurement dashboards.
- Batch handling, raw material batches, ATR batches and batch disabling.
- Stock Entry hooks, repairs, scrap behavior and valuation/rate updates.

### Item, BOM And Product Master

- Item Master, Product Master and Item Creation workflows.
- BOM creation, P202-O BOM creation, BOM child updates, pump BOM updates and recursive BOM updates.
- Item valuation from BOM costs.
- Drawing match and component drawing register support.
- Tool-only Item maintenance fields and automatic maintenance summaries.
- Item pricing and item category controls.

### Logistics And Delivery

- Delivery Note API and Delivery Note customizations.
- Serial-number transfer to Delivery Notes.
- DHL export and tracking integration.
- Logistics tracking page and tracking settings.
- Sales Order to Delivery Note lead-time reporting.
- Loan Order support and document links.

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
- Landed Cost Voucher-related behavior.
- Sales Invoice custom behavior.
- Bank reconciliation automation.
- Expense claim and administrative scripts.

### Reporting, Dashboards And AI

- Operational, sales, procurement, stock, production, delivery and quality reports added over time.
- SCM, quotation, global inventory, operations KPI and planning dashboards introduced or improved.
- AI-assisted operations reporting added with controlled evidence-backed insights.
- Document AI import structures added for document parsing and extraction workflows.

### User Experience And Technical Enablement

- Custom pages, common JavaScript utilities and UI refinements added.
- Barcode, DataMatrix, QR code and label infrastructure expanded.
- Web pages for planning, item information, logistics and document tooling added.
- Hooks, migrations, settings DocTypes and background utilities added to automate operational behavior, including Tool maintenance lifecycle updates.

## Current Main Custom Objects

The current AMF custom app includes custom objects for planning, item creation, Tool Maintenance Plans, Tool Maintenance Logs, global quality inspection, timer production, DHL tracking, loan orders, issue management, Document AI imports, HS codes, customer feedback, CRM forms, Brevo campaigns, sales actions and satisfaction surveys.

The current report catalog includes operational reports for inventory turnover, stock and revenue, produced and delivered items, purchased versus manufactured items, delivered items, purchase order items, late purchases, purchase order cash forecasting, projected stock, sales dashboards, quotation dashboards, manufacturing yield, machined parts, item margins, no-price items, leave balances, AMF general ledger and Sales Order to Delivery Note lead time.

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

Objet: AMF ERP - Version v2026.08.1 - Maintenance outils et BOM P202-O

Bonjour à toutes et à tous,

La dernière version AMF ERP, v2026.08.1, est prête pour validation dans le système live:

AMF ERP live
https://amf.libracore.ch/desk#

Cette version concerne principalement la planification de maintenance des outils directement dans l'ERP et la création de BOM pour les produits P202-O.

Principaux changements:

Tool Maintenance
https://amf.libracore.ch/desk#tool-maintenance
Une nouvelle page permet de suivre les plans de maintenance, les interventions, les échéances et les retards pour les outils.

Articles de type Tool
https://amf.libracore.ch/desk#List/Item/List
Une section maintenance est maintenant affichée uniquement pour les articles dont le groupe est Tool.

Tool Maintenance Plans
https://amf.libracore.ch/desk#List/Tool%20Maintenance%20Plan/List
Les plans de maintenance permettent de définir les fréquences, les prochaines échéances, les responsables et les instructions.

Tool Maintenance Logs
https://amf.libracore.ch/desk#List/Tool%20Maintenance%20Log/List
Les interventions réalisées peuvent être enregistrées et reliées au plan et à l'outil concerné.

BOM P202-O
https://amf.libracore.ch/desk#List/BOM/List
Les BOM des produits P202-O de la famille 4D peuvent être créés à partir des modèles P201-O correspondants, avec le composant body adapté.

Mise à jour automatique
Les statuts de maintenance sont recalculés automatiquement lors des changements d'outil, de plan ou d'intervention, ainsi qu'une fois par jour.

Ce que cela signifie pour vous:

- Les responsables maintenance et production sont invités à valider quelques outils représentatifs avant communication générale.
- Les responsables produit ou production sont invités à vérifier une BOM P202-O représentative avant utilisation opérationnelle.
- Les utilisateurs peuvent créer un plan de maintenance ou enregistrer une intervention depuis la fiche article Tool ou depuis la nouvelle page Tool Maintenance.
- Les articles qui ne sont pas dans le groupe Tool ne sont pas concernés par cette nouvelle section.
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
