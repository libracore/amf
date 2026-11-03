# Production Tracking audit and independent machining planning copy

Audit date: 2026-11-03, site `site1.local`, installed Frappe / ERPNext V12 source and site metadata.

## Result and isolation

The database Web Page `production-tracking` was duplicated **before implementation** to
`production-tracking-planning`, titled **Production Tracking - Planning**. The duplicate
was published on 2026-11-03 after the user explicitly requested publication and a commit.
Its route is `/production-tracking-planning`; `#usinage` opens the machining tab directly.

The existing HTML, JavaScript, CSS and Python methods were copied first. Changes are
contained in these new files and the new Web Page record:

- `amf/www/production_tracking_planning.py`: independent overview, planning, write and installer methods.
- `amf/templates/includes/production_tracking_planning/page.html`: copied overview plus the new tab.
- `amf/templates/includes/production_tracking_planning/page.js`: copied overview logic plus editable planning.
- `amf/templates/includes/production_tracking_planning/page.css`: scoped copied styling plus planning styles.
- `amf/www/test_production_tracking_planning.py`: integration tests with rollback after every test.
- This audit and its accompanying `production_tracking_planning/` evidence directory.

The master Web Page, `amf/www/production_tracking.py`, hooks, ERPNext/Frappe controllers,
DocTypes, Custom Fields, Property Setters and the two saved reports were not edited.
The copy calls `amf.www.production_tracking_planning.*`, with no imports or calls into
the original page's Python module. Standard framework APIs and existing Work Order save
hooks still execute normally; they are not copied or modified.

Page/code isolation does **not** create a second set of production records. User saves
on the copy update the actual Work Orders, so the reports and
other ERP views reflect them. The overview's note refers to the existing shared
Production Notes record. No second note was created, which could otherwise alter the
original method's unfiltered `limit=1` selection. All development test writes rolled back.

## Original page: behavior and findings

The page content is stored in the database `Web Page`, rather than an HTML file under
`www`. Its backend is `amf/www/production_tracking.py`. It shows the week's Sales Orders,
ongoing/upcoming assembly and machining cards, timers/operators, a clock and a shared note.

| Finding | Evidence / consequence | Handling in the copy |
| --- | --- | --- |
| Read APIs bypass document permissions | Original `get_work_orders`, `get_shipments`, `get_note` use `frappe.get_all`. Default whitelisting rejects Guests but still permits these calls from authenticated users without the corresponding DocType rights. | Login/DocType checks and permission-aware `frappe.get_list`; report role checks and document/field permission checks for editing. |
| Note writes bypass permissions and validation | Original `save_note` uses `db.set_value`, `insert(ignore_permissions=True)` and an explicit commit, with no version check. | Normal Document save, native permissions, required last-modified version, no explicit commit in request methods. |
| Machining cards do not represent report membership | Original draft selection uses status, priority, numeric item code and Item Group. It includes QC in ongoing cards; the machining reports exclude QC. | Preserve an overview, and load the new planning tab from the actual report definitions independently. |
| Alphanumeric Item codes are omitted by classification | Original `find_operation_type` requires `code.isdigit()`. Live report rows include alphanumeric `10xxxx`/`20xxxx` codes. | Recognize six-character `10`/`20` families with the relevant Item Group. |
| Machining operators are fabricated | Original draft cards hardcode `MBA` rather than reading an assignment. | No invented operator is displayed for machining cards. |
| Timer lookup can return the wrong record | Original first checks existence of an active/paused timer, then loads a timer using only Work Order as filter. | Use the same active/paused predicate for retrieval, selecting the latest modified timer. |
| Shipment color accepts draft/cancelled Delivery Notes | Original checks only the presence of any linked Delivery Note Item. | Only submitted Delivery Notes visible to the user count; parent permissions are applied before reading child rows. |
| Displayed week and queried week differ | Original JavaScript labels Monday–Friday; Python queries Monday–Sunday. Python uses server `date.today()`. | Label Monday–Sunday and use Frappe's site date. |
| Compact card HTML is malformed | Original compact anchor is missing its closing `>` before the child span. | Rebuilt valid markup; browser-checked compact number spans. |
| Database values are interpolated as HTML | Original names, item labels, customer names and tooltip strings are inserted without escaping. | Escape copied overview values, encode document URLs, and build table cells with DOM text/value APIs. Attachment links reject executable URL schemes. |
| Note feedback calls an undefined function | Original calls `showToast`, with no definition in the page. | Explicit Save button, success/error status and retained edits. |
| Note listeners can accumulate | Calling original `loadGlobalNote` repeatedly registers additional input listeners. | Bind note controls once. |
| Layout rules affect framework containers | Original CSS globally overrides `.container`, `.row` and others, with fixed 1800px widths. | Scope the copy's styles, use responsive widths, scroll the wide table, keep headers/actions visible. |
| Load handler replaces other handlers and assumes elements exist | Original assigns `window.onload` and dereferences nav/footer unconditionally. | Register a load event listener and safely select the website chrome. |
| V12 website callbacks differ from Desk callbacks | `frappe/website/js/website.js` runs `opts.always` before `opts.callback`, and does not pass `opts.error` through to jQuery AJAX. A save handler based on Desk callback ordering would refresh incorrectly or stay stale. | A local jqXHR adapter guarantees callback/error/completion order without changing framework JavaScript. Verified with real website assets and real endpoint saves. |
| Debug information goes to console/server logs | Original logs Work Order/timer and note details. | Remove those debug statements in the copy. |

Remaining overview semantics: a green shipment means a submitted linked Delivery Note
exists, not that every Sales Order quantity has shipped. Work Order overview cards retain
the original general status grouping rather than becoming the date-sorted planning table.
The overview still makes individual timer/Item-group lookups; the new report read is
batched per report. These points do not limit planning row completeness.

## Exact machining data source

Both requested reports exist and are enabled **Report Builder** reports on **Work Order**:

| Report | Item filter | Rows at verification |
| --- | --- | ---: |
| `Plug à usiner...` | `production_item LIKE '10_%'` | 9 |
| `Valve Seat à usiner...` | `production_item LIKE '20_%'` | 15 |

Both also require:

- Status is neither `Cancelled`, `Completed`, nor `Stopped`.
- Progress differs from `QC`.
- Priority is at most 5.

The patterns are SQL LIKE patterns: `_` is a one-character wildcard. The new planning
query preserves the saved filters exactly, including their SQL/null semantics. It does
not replace them with a guessed Item Group, numeric-only predicate or status list.
The disabled, similarly named `Plugs à usiner...` report is not used.

Both saved reports sort by priority and store `page_length=500`. The copy leaves those
settings intact and applies **Expected Date ascending across the combined results**,
then Work Order ID for equal dates. Empty dates follow all dated rows (one such row was
present at verification). The relevant field is **`expected_delivery_date_`**, with a
trailing underscore, not the separate standard `expected_delivery_date` field.

The backend explicitly requests unlimited results, deduplicates by Work Order ID,
retains source report membership, and returns all columns in saved report order.
The current result is **24 distinct rows, 13 report columns**; the UI adds source and
action columns. Search and source filtering run over the already fetched complete data.
Labels, field types, Select options and editable status come from current site metadata.
Unsupported future joined/grouped report layouts fail explicitly instead of silently
showing or editing the wrong fields.

## Columns and edit behavior

All 13 columns are displayed. Existing system/derived fields remain protected, so
**eight business fields are editable on drafts**. This is the deliberate limit on
“all columns modifiable”; making the five protected columns arbitrary writable values
would require changing lifecycle or source-of-truth rules, which this implementation
does not do.

| Column | Work Order field | Draft editing | Submitted editing |
| --- | --- | --- | --- |
| ID | `name` | Link to Work Order; identity protected | Protected |
| Item To Manufacture | `production_item` | Editable Item code; requires an accessible active submitted default BOM; refreshes BOM items/operations, Item Name, R&D Code, description, UOM and image | Protected by native metadata |
| Item Name | `item_name` | Fetched/read-only; updates when the production Item changes | Protected |
| R&D Code | `rd_code` | Fetched/read-only; updates from Item reference code | Protected |
| Qty To Manufacture | `qty` | Editable; normal quantity validation and recalculation | Protected by native metadata |
| Progress | `progress` | Select: `En Attente`, `Fabrication`, `QC` | Editable with native write/submit rights |
| Expected Date | `expected_delivery_date_` | Date input; updates chronological position after save | Protected by native metadata |
| Priority | `priority` | Integer input | Editable with native write/submit rights |
| Machine | `machine` | Editable text | Protected by native metadata |
| Raw Material | `raw_material` | Editable text | Protected by native metadata |
| Drawing | `drawing` | Editable attachment path/URL; existing allowed links can be opened | Protected by native metadata |
| Document Status | `docstatus` | Displayed; submit/cancel belongs to the native Work Order workflow | Protected |
| Temps de Fabrication Estimé [jours] | `temps_de_fabrication_estime_jours` | Calculated/read-only; recalculates on ordinary save | Protected |

Estimated days follow the existing `work_order_estimated_time` hook: average Planning
preparation hours plus average cycle minutes × quantity / 60, converted to workdays
of 8 h 25 min. The copy does not introduce a competing estimate or manual override.

Drawing editing changes the existing Work Order attachment value; it does not upload a
new file. New files can be uploaded using the native Work Order form opened from its ID.

Each row stages its edits and offers **Enregistrer / Annuler**. Saves affect only changed,
authorized report fields, lock the row, compare its original `modified` timestamp, verify
that it still belongs to the reports, then call `doc.save()` with native validation and
hooks. Both user and server errors retain unsaved input. A refresh warns before discarding
staged changes; leaving the page triggers the browser's unsaved-changes protection.
Saving one row preserves other staged rows and their original conflict tokens.

Changing progress to QC, priority above 5, or Item outside the report filters can remove
the saved row from the planning; that is correct report behavior and the UI explains it.
Cancelled records cannot be edited. Submitted records honor `allow_on_submit` and native
submit permissions. Read-only users see no editable cells.

The note uses the native Production Notes permissions. A real non-administrator Stock
User could read/edit the 24 planning rows but could not edit the note, consistent with
that user's existing permissions; no new roles or permissions were granted.

## Verification and review

17 integration tests passed against the initialized site, with rollback after each test:
exact row/column parity with both native reports; global date order and empty dates;
fetching beyond 500 rows without truncation; saving planning values and dates; quantity
recalculation; QC removal; version conflicts; protected/unreported fields; invalid numbers,
dates, options and quantities; out-of-report writes; Guest and read permission denial;
read-only cell metadata; submitted edit rules; report authorization/disabled state;
duplicated overview responses; and shared-note save/conflict behavior.

Firefox used the actual copied Web Page template, installed website bundles and actual
backend endpoints through a private, temporary loopback preview before publication.
Successful backend saves in this browser server were rolled back automatically. Checks
covered complete rendering, the 192 editable cells, Save/Cancel, source/search filtering,
save refresh, retained edits after failure, independent pending rows, original overview
cards/shipments and mobile horizontal scrolling. See the evidence directory for screenshots.

Python compilation, JavaScript syntax and HTML identifier/panel structure were checked.
The source Web Page still matches the pre-change document snapshot, including its
`modified` timestamp `2025-12-08 10:29:27.199378`. Source report snapshots and master Python
hashes are recorded with the audit evidence. Unrelated pre-existing workspace changes
were left intact.

After explicit publication authorization, the copy's published state and route resolution
were verified with the same 24 rows and 13 columns. The original Web Page and both reports
still matched their audit hashes.

The installer refreshes only the duplicate from the new source files. It is intentionally
not an HTTP-whitelisted method. To recreate or refresh the published copy:

```sh
bench --site site1.local execute amf.www.production_tracking_planning.install_page --kwargs '{"publish": true}'
```

Omitting `publish`, or passing `false`, saves the copy as an unpublished draft.

The copy is also available as a Web Page document in Desk under
`#Form/Web%20Page/production-tracking-planning`. There is no navigation change to the
original page.
