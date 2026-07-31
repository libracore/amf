# AMF ERP Release Notes

Generated on: 2026-07-31

Change history through: 2026-07-30

Live system: [AMF ERP Desk](https://amf.libracore.ch/desk#)

Latest release: `v2026.07.1`

Release status: Published

Release audience: AMF ERP users, department leads, management, operations, finance, logistics, quality, sales and support teams.

## Purpose

This document is the business-facing release notes and change history for the AMF ERP custom app.

It summarizes the main ERP changes developed in the AMF custom app from the beginning of the recorded development history to 2026-07-30. The report is based on the `apps/amf` git history, which starts on 2022-09-19, and on the current AMF app structure, including custom DocTypes, reports, pages, hooks and documentation.

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
| `v2026.07.1` | Published, latest | 2026 Q3 to date | Procurement cash forecast, global inventory dashboard, issue management, item dashboards, component drawing register, bank reconciliation automation and serial-number tools. |
| `v2026.06.0` | Superseded | 2026 Q2 | Loan Orders, landed cost behavior, work order automation, KPI dashboards, procurement tools and AI-assisted reporting. |
| `v2026.03.0` | Superseded | 2026 Q1 | Swiss VAT handling, customs mapping, planning quantities, batch quantity retrieval and costing support. |
| `v0.7.0` | Superseded | 2025 Q4 | Production Tracking, Timer Production, automatic Quality Inspections, drawing-based QA and HS Code support. |
| `v0.6.5` | Superseded | 2025 Q2 | Satisfaction scoring, customer reporting, planning and rating reports, leave balances and ERPNext-related Stock Entry fixes. |
| `v0.6.0` / `v0.6.1` | Superseded | 2025 Q1 | Safety Stock, Work Order creation, labels, drawing matching, customer surveys and Global Quality Inspection. |
| `v0.4.0` | Superseded | 2024 Q3 | Master CRM, Sales Actions, campaign lists, Gravity Forms, Brevo integration and CRM analytics. |
| Foundation releases | Superseded | 2022-2024 | Core reporting, planning, labels, QR codes, inventory visibility, logistics, purchasing and CRM foundations. |

## Latest Release: `v2026.07.1`

Release date: 2026-07-30

Live version: [https://amf.libracore.ch/desk#](https://amf.libracore.ch/desk#)

### Summary

This release extends the AMF ERP with stronger procurement cash planning, inventory visibility, manufacturing preparation, issue handling, drawing traceability and administrative automation. It continues the 2026 direction of improving operational dashboards, finance support, compliance-oriented data, production planning and management reporting.

### Highlights

- Added Purchase Order Cash Forecast reporting for procurement and finance planning.
- Expanded Global Inventory Dashboard, procurement tools and stock analysis logic.
- Added or improved issue management functionality for operational follow-up.
- Added estimated manufacturing time support on Work Orders.
- Updated item dashboards and Item Creation tooling.
- Added Component Drawing Register support.
- Updated Delivery Note, purchase receipt return and leave entry behavior.
- Added or improved bank reconciliation automation and serial-number mixer work.
- Added Sales Invoice trend reporting updates.

### Change Notes

| Area | Change | Brief Explanation |
| --- | --- | --- |
| Procurement and finance | Purchase Order Cash Forecast report added. | Supports cash planning by combining unbilled Purchase Order commitments and unpaid supplier invoices linked to Purchase Orders, with cumulative views for one month, one quarter and one year in CHF, EUR and USD plus drill-down detail. |
| Inventory and procurement | Global Inventory Dashboard, procurement tools and stock analysis algorithms added. | Gives procurement and operations better visibility into stock, availability, shortages and replenishment decisions. |
| Manufacturing | Estimated manufacturing time added to Work Orders. | Improves production planning, capacity discussion and manufacturing expectation management. |
| Quality and support | Issue management functionality added or expanded. | Helps teams register, follow up and manage operational or quality-related issues more consistently. |
| Item and engineering data | Item dashboards, item creation tools and Component Drawing Register added or updated. | Improves item maintenance, drawing traceability and engineering-to-production visibility. |
| Logistics and warehouse | Delivery Note behavior and purchase receipt return support updated. | Improves handling of delivery and receipt workflows where corrections or return flows are needed. |
| Administration | Leave entry behavior updated. | Keeps administrative workflows aligned with current operating needs. |
| Finance operations | Bank reconciliation automation added or improved. | Reduces manual reconciliation work and supports cleaner finance follow-up. |
| Serial-number operations | Serial-number mixer work added. | Supports operational handling where serial-number combinations or corrections are needed. |
| Sales reporting | Sales Invoice trend reporting updated. | Improves management visibility into invoicing trends and sales performance. |

### User Impact

- No separate user installation action is required.
- Users should continue working in the live ERP system at [https://amf.libracore.ch/desk#](https://amf.libracore.ch/desk#).
- Department leads should review new or changed reports that affect their workflows.
- Procurement and finance users should validate forecast figures against known Purchase Orders and supplier invoices during initial use.
- Production users should review estimated manufacturing time on Work Orders where available.
- Support, quality and operations users should use the updated issue management flow for new cases.

### Validation Notes

Recommended post-release checks:

- Open the live ERP desk and confirm access for the affected user groups.
- Validate Purchase Order Cash Forecast totals in CHF, EUR and USD against known open commitments.
- Review Global Inventory Dashboard figures for high-volume and critical items.
- Confirm estimated manufacturing time is visible where expected on Work Orders.
- Test issue creation and follow-up for one representative operational case.
- Confirm Delivery Note and purchase receipt return behavior on a non-critical example.
- Review bank reconciliation automation output before relying on it for month-end work.

## Executive Summary

Since the beginning of development, the AMF ERP has evolved from a custom reporting and page layer into a broader operational system covering manufacturing, planning, inventory, purchasing, logistics, sales, CRM, quality, finance support and management reporting.

The main evolution areas are:

- Production planning, Work Order automation and manufacturing follow-up.
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

#### `v2026.07.1` - 2026 Q3 To Date - Latest

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
- Production tracking with operator timers and Work Order QR access.
- Estimated manufacturing time and production cost/time tracking support.
- Machining reports and production stickers.

### Inventory, Stock And Procurement

- Inventory turnover, stock summary, projected stock and stock/revenue reporting.
- Safety stock, reorder level, stock forecasting and shortage visibility.
- Purchase Order checking, late purchase reporting and procurement dashboards.
- Batch handling, raw material batches, ATR batches and batch disabling.
- Stock Entry hooks, repairs, scrap behavior and valuation/rate updates.

### Item, BOM And Product Master

- Item Master, Product Master and Item Creation workflows.
- BOM creation, BOM child updates, pump BOM updates and recursive BOM updates.
- Item valuation from BOM costs.
- Drawing match and component drawing register support.
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
- Hooks, migrations, settings DocTypes and background utilities added to automate operational behavior.

## Current Main Custom Objects

The current AMF custom app includes custom objects for planning, item creation, global quality inspection, timer production, DHL tracking, loan orders, issue management, Document AI imports, HS codes, customer feedback, CRM forms, Brevo campaigns, sales actions and satisfaction surveys.

The current report catalog includes operational reports for inventory turnover, stock and revenue, produced and delivered items, purchased versus manufactured items, delivered items, purchase order items, late purchases, purchase order cash forecasting, projected stock, sales dashboards, quotation dashboards, manufacturing yield, machined parts, item margins, no-price items, leave balances, AMF general ledger and Sales Order to Delivery Note lead time.

The current page catalog includes inventory planning, sales order stock projection, logistics tracking, global inventory dashboard, component drawing register, bank reconciliation automation, order confirmation parsing, PDF text extraction and file upload tools.

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

### Email de la dernière version - prêt à envoyer

Objet: AMF ERP - Version v2026.07.1 - Mises à jour opérations et reporting de juillet 2026

Bonjour à toutes et à tous,

La dernière version AMF ERP, v2026.07.1, est maintenant disponible dans le système live:

AMF ERP live
https://amf.libracore.ch/desk#

Cette version concerne principalement la planification de trésorerie achats, la visibilité stock, le suivi des incidents, la préparation de fabrication, la traçabilité des dessins et l'automatisation administrative.

Principaux changements:

Purchase Order Cash Forecast
https://amf.libracore.ch/desk#query-report/Purchase%20Order%20Cash%20Forecast
Disponible pour la planification achats et finance.

Global Inventory Dashboard
https://amf.libracore.ch/desk#global-inventory-dashboard
Les outils d'approvisionnement et la visibilité stock ont été étendus.

Issue Management
https://amf.libracore.ch/desk#List/Issue/List
La gestion des incidents a été ajoutée ou améliorée.

Estimated Manufacturing Time On Work Orders
https://amf.libracore.ch/desk#List/Work%20Order/List
Le temps de fabrication estimé est maintenant disponible lorsque la configuration le permet.

Item Creation Tools
https://amf.libracore.ch/desk#List/Item%20Creation/List
Les outils de création d'articles ont été mis à jour.

Item Dashboards
https://amf.libracore.ch/desk#List/Item/List
Les tableaux de bord articles ont été mis à jour.

Component Drawing Register
https://amf.libracore.ch/desk#component-drawing-register
Le registre des dessins composants a été mis à jour.

Delivery Notes
https://amf.libracore.ch/desk#List/Delivery%20Note/List
Le comportement des bons de livraison a été mis à jour.

Purchase Receipt Returns
https://amf.libracore.ch/desk#List/Purchase%20Receipt/List
Les retours de réception d'achat ont été mis à jour.

Leave Entries
https://amf.libracore.ch/desk#List/Leave%20Application/List
Les saisies d'absence ont été mises à jour.

Bank Reconciliation Automation
https://amf.libracore.ch/desk#bank-reconciliation-automation
L'automatisation du rapprochement bancaire a été améliorée.

Serial Number Tools
https://amf.libracore.ch/desk#List/Serial%20No/List
Les outils de numéros de série ont été améliorés.

Sales Invoice Trends
https://amf.libracore.ch/desk#query-report/Sales%20Invoice%20Trends
Le rapport de tendance des factures de vente a été amélioré.

Ce que cela signifie pour vous:

- Merci de continuer à utiliser le système AMF ERP live via le lien ci-dessus.
- Les responsables de département sont invités à vérifier les rapports et les flux de travail qui concernent leur équipe.
- Les utilisateurs achats et finance sont invités à valider le nouveau rapport de prévision de trésorerie lors des premières utilisations.
- Les utilisateurs production sont invités à vérifier les temps de fabrication estimés sur les ordres de fabrication lorsque ces informations sont disponibles.
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
