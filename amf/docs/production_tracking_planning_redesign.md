# Production Tracking: visual redesign

2026-11-05 · Independent page `production-tracking-planning`.

The published copy now uses a shared production cockpit with consistent navigation,
clear visual hierarchy, compact status labels and a responsive layout. Its route remains
`/production-tracking-planning`; `#usinage` opens the planning tab directly.

The later density adjustment enlarges the desktop clock to 42 px (28 px on mobile),
places summary values beside their labels to reduce the four-panel row height, and
tightens the production card padding, spacing and lane headers without truncating labels.

## Deploying to the live site

A Git merge alone does not create or refresh this database-stored Web Page. There is
currently no fixture, patch or migration hook that runs its installer. After deploying
the code, run the following from the live bench, replacing `LIVE_SITE` with its site name:

```sh
bench --site LIVE_SITE execute amf.www.production_tracking_planning.install_page --kwargs '{"publish": 1}'
```

This creates the separate page if absent, or refreshes its HTML, CSS and JavaScript if
already present, then publishes it. Manual creation through the Web Page form is not
required. Run it after future updates to these page templates as well. The original
`production-tracking` page is not modified.

## Production overview

- Four live summaries: ongoing orders, upcoming orders, remaining weekly shipments and overdue shipments.
- Separate Assemblage and Usinage boards, each with ongoing/upcoming lanes and counts.
- Every card shows the complete item label, order/item identifiers, quantity, expected date and available machine/operator information. Dates sort chronologically, with missing dates last.
- Active timers, paused timers, overdue dates and missing dates receive explicit text and distinct status treatments. Assembly cards no longer use the machining Progress field as their assembly status.
- Weekly shipments show customer, date and a written delivery-note status. Customer visibility remains configurable.
- Shared workshop notes retain their existing permissions, conflict protection and explicit Save action.

## Machining planning

- Four summaries show report order count, overdue dates, unassigned machines and total recorded estimated manufacturing days.
- Quick filters cover overdue orders, today's orders, missing machines and unsaved rows. Search, part-family and machine filters work together; a reset clears them.
- A machine distribution panel shows order counts, overdue portions and recorded estimated days. Selecting a machine filters the table. These bars describe the recorded work, not machine capacity or guaranteed completion dates.
- All report rows and all 13 report columns remain present, in the existing report column order and global expected-date order. Horizontal scrolling exposes the complete table.
- Desktop pins part family, Work Order identity and action controls. Mobile pins the order identity while keeping the wider table inside its scroll region.
- French column headings, readable date hints, part-family badges and protected document-state labels replace dense technical presentation. Native date inputs remain editable; accompanying month-name hints remove date-format ambiguity.
- Editable cells use subtle borders until interaction. Pending cells and rows are highlighted, and a sticky pending-change bar can jump to modified rows.
- Save and Cancel appear when a row is edited. Delete remains a separate confirmed action with its existing permissions, draft/version/report checks and native link protection. Icon actions have descriptive titles and accessible names.

## Data and compatibility

The independent backend only adds overview display fields (`qty`, machine, priority and
expected dates) and the site date used by visual date comparisons. Save, Delete, report
membership, calculated fields and permissions keep their existing behavior. Summary
estimates use the recorded Work Order values; zero or missing values are not replaced by
invented scheduling assumptions. The table's filter counts reflect the current selection;
summary cards describe the complete saved report cohort.

The page uses local CSS, system fonts and inline SVG icons; no new frontend packages or
external font/image services are required. Frappe V12's website callback adapter is
preserved. Both tabs support keyboard navigation, visible focus and reduced-motion settings.

The master Web Page, original backend, framework controllers, hooks, source reports,
permissions and production records were not changed by this redesign.

## Verification

All 25 existing integration tests passed with rollback. All 5,568 production Work Orders
and their timestamps were unchanged after that run. Firefox checks used a private source
preview and the installed Frappe V12 website assets, with real Save calls rolled back and
Delete restricted to a transaction-only fixture.

Browser checks covered both summaries, complete cards and columns, customer visibility,
all quick filters and empty states, machine bars, combined search/report filters, the
pending-change bar, Cancel, native Save and refresh, deletion confirmation cancellation,
blocked deletion, successful native fixture deletion preserving another draft, keyboard
tabs and contained mobile scrolling. A final read-only visual pass captured the finished
design using only actual rows.

Screenshots and deployment verification are in
[`production_tracking_planning/redesign_2026_11_05/`](production_tracking_planning/redesign_2026_11_05/):

- [Production overview — desktop](production_tracking_planning/redesign_2026_11_05/overview_desktop.png)
- [Machining planning — desktop](production_tracking_planning/redesign_2026_11_05/planning_desktop.png)
- [Machine distribution](production_tracking_planning/redesign_2026_11_05/planning_machines.png)
- [Production overview — mobile](production_tracking_planning/redesign_2026_11_05/overview_mobile.png)
- [Machining planning — mobile](production_tracking_planning/redesign_2026_11_05/planning_mobile.png)
