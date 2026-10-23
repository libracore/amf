# Monthly random inventory sanity checks

This feature lives in the AMF app and uses native Frappe v12 DocTypes. It does
not modify ERPNext core or write stock quantities, valuation rates, stock
ledger entries, or accounting entries directly. Corrections use ERPNext's
normal Stock Reconciliation or Stock Entry controllers.

## Initial configuration

Open **AMF → Production Tracking → Monthly Inventory Settings**, or find the
DocType in the Desk search bar.

The installed defaults are:

| Setting | Value |
| --- | --- |
| Company | Advanced Microfluidics SA |
| Assignee | alexandre.trachsel@amf.ch |
| References per check | Exactly 10 distinct references, selected randomly |
| Warehouse scope | Enabled stock warehouses under AMF Warehouse / Production, excluding OLD BATCH |
| Due date | 15th of the inventory month |
| Eligible item groups | All item groups enabled except Product |
| Excluded references | Separate administrator-maintained list, initially empty |
| Automatic generation | Disabled until the settings are reviewed and enabled |

The **Item Groups** table lists every item group and an **Enabled** checkbox.
All groups start enabled except **Product**. Unchecking a parent excludes that
group and its entire subtree, even if child checkboxes remain checked.
For example, disabling **Part** also excludes **Fasteners** and the other Part
subgroups. The enabled **All Item Groups** root does not override Product's
disabled setting. Product can be explicitly enabled later.

Add individual exceptions to the **Excluded References** table. Every listed
reference is excluded regardless of its group's setting; a reason is optional.
References may be listed even when currently inactive so the exclusion still
applies if they are reactivated. Duplicate exclusion rows are rejected.

New groups are included automatically with the same defaults. Opening settings
or using **Refresh Item Groups** adds their rows without resetting existing
checkboxes or exclusions; save the settings to persist those new rows. Server
validation and generation also account for newly created groups. The effective
pool contains active, unexpired stock items that are not variant templates or
cancelled items, minus explicit exclusions. At least ten must remain before
automatic generation can be enabled.

**References per Check** is fixed at ten. The former minimum/maximum fields
are hidden and normalized to ten for compatibility. **Warehouse Scope** shows
the Production group belonging directly to AMF Warehouse for the company.

These rules apply to future selections. Changing a group or excluding a
reference does not alter an already generated checklist or its audit history.

Select **Enable Monthly Inventory** and save when the settings are ready. The daily
scheduler creates the current month's check on its next run. **Generate Current
Month** creates it immediately and queues an email to the assignee, even while
automatic scheduling is disabled. Repeating generation opens the existing
check and sends no duplicate email.

Only a Stock Manager or System Manager can configure or generate checks.
The assignee receives an open ToDo and explicit read/write sharing on the
check. Normal stock correction creation and submission permissions still apply.

## Monthly selection algorithm

1. Lock the settings record for the enclosing database transaction.
2. Identify the company and current month in the site's configured timezone.
3. Look up the deterministic company/month document name. Return the existing
   check if one has already been created. This also prevents concurrent
   scheduler/manual requests from creating separate samples.
4. Build the candidate pool from enabled item groups. A disabled group vetoes
   its descendants, and explicit excluded references always take precedence.
   Filter inactive, expired, non-stock, variant-template and cancelled items.
   Exclude any reference already present in an unfinished check for this company.
5. Require at least ten available candidates; never silently reduce the sample.
6. Use the system random generator to select ten distinct references uniformly
   without replacement. Prior selection dates do not bias the random sample.
7. Store the selected references, algorithm version, pool size, enabled groups,
   excluded references, and prior selection dates in the read-only selection audit.
8. Snapshot every selected reference in the enabled stock warehouses within
   AMF Warehouse / Production, including zero-stock warehouses. The Production
   group itself is not a stock location. OLD BATCH is explicitly excluded even
   while enabled. Disabled warehouses, descendants of
   disabled ancestors, and other branches are excluded from counts, corrections
   and completion requirements.
9. Create the check, its ToDo, sharing, and queued email in one transaction.

Every new check contains exactly ten distinct item references. The active
Production scope currently contains seven eligible stock warehouses, so a
ten-reference check contains 70 warehouse rows. These are Main Stock,
Work In Progress, Scrap, Shipping, Quality Control, Rework and Test Unit.
Inventory, external warehouses and other AMF Warehouse branches are outside scope.

If fewer than ten eligible references are available, generation fails visibly
and the scheduler records an error. It does not silently shrink the sample or
reuse references from open checks. Finish the backlog or review enabled groups
and excluded references to extend the pool.
The daily job catches up after downtime; it creates the current month only,
not retroactive checklists for missed months. A late check retains its original
due date, and overdue open checks are marked in the list view.

## Counting workflow

Open **Monthly Inventory Check** from the assignment or email.

Each warehouse row contains the item, warehouse, stock UOM, ERP quantity,
valuation rate, snapshot time, counted quantity, verified valuation rate,
explicit confirmation, reason for a difference, correction reference, and
the user/time of confirmation.

Creation and **Refresh Stock** automatically fill the warehouse's actual stock
balance and its latest valuation rate from the latest active stock ledger entry
at the snapshot time (`qty_after_transaction` and `valuation_rate`). Values are
specific to the item/warehouse pair; item-master rates and other warehouses'
rates are not substituted. If that warehouse has no ledger history for the
reference, both values start at zero.

The counted quantity and verified rate start with the ERP values as an entry
aid. They are not treated as verified until **Confirmed** is checked. Enter
the physical quantity and the valuation rate you verified, explain each
difference, confirm the row, and save. For quantities of zero, rate-only
changes do not require a stock adjustment because no stock is being valued.

**Confirm Empty Warehouses** asks for explicit confirmation that the remaining
warehouses showing zero stock were physically checked and found empty. It
confirms only rows whose ERP and entered quantities are both zero. Warehouses
containing unexpected stock must instead receive their actual counted quantity.

Counts must be finite, nonnegative numbers in ERPNext's numeric range.
Stock UOMs marked as whole-number-only reject fractional quantities. A
nonzero counted quantity with a difference requires a positive valuation rate,
as required by v12's Stock Reconciliation. Existing zero-valued stock can be
confirmed unchanged. Negative ERP
balances can be corrected to a nonnegative physical count; their initial
count entry is zero until the user enters the physical count.

If a warehouse is disabled or re-enabled during an open check, the scope
validation requires **Refresh Stock** and a recount. Refresh removes disabled
warehouses and includes newly enabled ones within Production. Moving a warehouse
into or out of Production likewise changes the scope. Completed checks retain their
historical audit records.

The quantities and rates displayed are dated snapshots, not continuously
overwritten balances. The form checks for movements when opened. A stock
movement, cancellation, reposting, changed warehouse scope, changed stock UOM,
or changed item tracking configuration requires **Refresh Stock** and a new
count. Refresh clears all counts and takes a new complete snapshot. It never
overwrites saved counts silently.

## Corrections and completion

For ordinary items, **Create Draft Reconciliation** creates one standard
Stock Reconciliation containing only the differences. Every warehouse row
must already be confirmed. The voucher belongs to the same company, uses its
standard adjustment account and cost center defaults, and targets the counted
quantities and verified rates. It remains a draft until a permitted user
reviews and submits it.

The submission hook keeps posting time as a string: Frappe v12's HTTP JSON
encoder cannot serialize Python `datetime.time` objects after `before_submit`.
The Stock Reconciliation form also guards missing/invalid save responses so
an interrupted request cannot crash on `r.exc` or display a false Saved alert.
If save confirmation is unavailable, reload the voucher and check its status
before retrying; the client never retries a stock posting automatically.

The generated voucher is linked in both directions. Repeated button clicks
open the same voucher. Its item/warehouse scope, quantities, rates, purpose,
company, and inventory link are protected against changes inconsistent with
the count. Accounting fields retain normal ERPNext validation. Posting time
is refreshed during validation/submission. Stock must still match the
count's snapshot when the voucher is saved or submitted.

To change counts or refresh stock after generating a draft, delete the draft
first. The deletion hook clears the active links. Cancelled generated
vouchers may be replaced. Ordinary ERPNext amendment of a generated voucher
is intentionally rejected: generate its replacement from the inventory check.

For batch or serial items, create the normal batch/serial-aware Stock Entry
or Stock Reconciliation with the correct identities and link that submitted
document in the warehouse row's **Correction Document Type** and **Correction
Document** fields. These items are counted and valued at warehouse-total
level in the checklist. The feature does not infer missing batch or serial
identities or automatically reconcile aggregate quantities for tracked items.
Ordinary items can also use this manual correction path.

After submitting corrections, choose **Verify and Complete**. A check passes
only when:

- Every warehouse row has been explicitly confirmed.
- Item configuration and the complete warehouse scope still match.
- Rows without corrections have no intervening stock changes.
- Each difference is linked to a submitted stock voucher from the same company.
- The voucher actually posted stock ledger entries for that item and warehouse
  after the count was recorded.
- Excluding that voucher, the ledger fingerprint still matches the count's
  original fingerprint: unrelated or net-zero movements require a recount.
- Current stock equals the counted quantity and verified valuation rate,
  rounded to the database's six-decimal precision. Rate is ignored at zero stock.

Completion records its user and time, closes the assignment, and locks the
check against further editing. An email or a submitted voucher alone does not
mark a check passed. Final verification is an explicit user action.

Cancelling a correction used by a check reopens the check and assignment,
clears the affected confirmations and completion stamp, and adds an audit
comment. Refresh and recount before completing again. Later ordinary stock
movements do not invalidate historical passed checks.

## Integrity and concurrency

The ledger fingerprint includes entry count, latest creation/modification
times, movement/value sums, cumulative balance/rate sums, cancellation count,
and future-entry count. This detects net-zero movement and reposting, not just
changes in final quantity. Actual balances come from ERPNext's stock ledger
functions. Future-dated active entries block counting so a reconciliation
cannot overwrite an unseen future balance.

Inventory transitions lock the check's unique parent record before reading it.
Child rows are read without locking their index range. The parent modification
timestamp must match the transaction's consistent-read snapshot before those
children can be used; otherwise a timestamp conflict requires a reload. This
avoids mixing newer document headers with older counts under REPEATABLE READ.
Native Frappe saves also lock the parent before updating child rows, so writers
of the same check remain serialized.

Creating snapshots, confirming physical counts and saving draft corrections
do not lock stock history. Submission and completion still verify current
balances under stock locks. Those locks follow ERPNext's ledger-then-Bin order
and a deterministic item/warehouse order. Document names and backlinks provide
an additional idempotency boundary.

The earlier child-row `SELECT ... FOR UPDATE` could be executed as a full-table
scan, locking rows from other checks and producing deadlock 1213 during concurrent
saves. Removing that locking scan fixes this conflict without discarding counts
or weakening the stock verification performed when posting corrections. Plain
reads use InnoDB's consistent-read snapshot, as described in the official
[InnoDB consistent-read documentation](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html).

Snapshot fields, selected references, row scope, derived differences, audit
users/timestamps, status, and completion stamps are validated on the server.
They cannot be forged by changing browser fields or posting JSON directly.
Checks are retained as audit records and cannot be deleted through the normal
document API. Standard Frappe version tracking retains count and refresh
history. Non-manager stock users can access checks assigned to them; the
assignee's explicit document share supports users without a Stock User role.

## Deployment and validation

The existing site was installed with a targeted DocType reload and setup.
The scope is AMF Warehouse / Production and the sample size is fixed at ten.
Deployments preserve the configured group switches, manual exclusions and
scheduler enablement. The current site has automatic generation enabled by its
administrator. No operational stock quantities or valuations were changed by
installation. Unconfirmed checks may be refreshed to the new scope while
preserving their selected references; recorded physical counts are not discarded
automatically.

For another existing v12 site with AMF installed, use:

```sh
bench --site SITE execute amf.amf.utils.monthly_inventory.install_monthly_inventory
```

This reloads the inventory DocTypes, creates/updates the reconciliation
link, fills only missing settings defaults, adds missing item groups without
resetting saved choices, and clears relevant caches. The former reference
whitelist is retained in a hidden legacy field for compatibility; it does not
control eligibility and is never inverted into the exclusion list.
It avoids running unrelated pending patches. Standard `bench migrate` also
runs the idempotent setup hook. App installation runs setup after its DocTypes
are synchronized. Use the site's usual worker/web reload procedure when
deploying source changes to persistent processes.

Unit tests:

```sh
env/bin/python -m unittest amf.amf.utils.test_monthly_inventory -v
node apps/amf/amf/tests/test_stock_reconciliation_transport.js
```

The opt-in integration suite is
`amf.amf.utils.test_monthly_inventory_integration`. Initialize/connect Frappe,
set `AMF_INVENTORY_DB_TESTS=1` and `frappe.flags.in_test=True`, then invoke its
unittest suite. Prefer a dedicated test site. The suite uses temporary
warehouses and unique checklist names, blocks commits, suppresses email and
background cleanup jobs, and rolls each test back to a savepoint.

Suppressing v12's synchronous deletion cleanup job is necessary: its
`execute_job` wrapper commits even during tests. The integration tests exercise
real stock and accounting posting inside rollback boundaries, including
generation idempotency, writable assignment, serialized form saves, manual
and generated corrections, draft deletion, completion, and cancellation.
The submission regression test uses the Desk save endpoint under the assignee's
permissions and serializes the actual HTTP JSON response. The Node tests use
the installed Frappe request/form-save code to reproduce the null `r.exc`
failure and check normal saves, validation errors, missing responses, and
recovery without automatic retries.

The additional opt-in suite `amf.amf.utils.test_monthly_inventory_concurrency`
uses `AMF_INVENTORY_CONCURRENCY_TESTS=1` in a separately initialized Frappe process.
It creates disposable copies of the MIC tables, commits only data in those copies,
and drops them afterward. It reproduces the previous full-table locking deadlock,
verifies that two checks can save concurrently with the corrected code, and
checks that a newer parent cannot be combined with stale snapshot counts. It
does not modify operational MICs, stock, or accounting entries.

The implementation was checked against the installed v12 Stock Reconciliation,
Stock Ledger, assignment, permissions, and document lifecycle code. General
ERPNext workflow background is available in the official
[Stock Reconciliation documentation](https://docs.frappe.io/erpnext/stock-reconciliation);
newer-version batch/serial interfaces described there are not assumed here.
