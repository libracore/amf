# Work Order creation audit and magnet-stock coverage

Audit date: 2026-11-03. Scope: all of `amf/amf/utils/work_order_creation.py`
(1,331 lines before this change), its stock-summary dependency, callers/hooks,
and the installed Frappe / ERPNext V12 quantity calculations. AMF baseline commit:
`50c2be658c047c14b9eaf9dcae4d55e6946ef9fd`. Both framework repositories are on `v12`.

## Implemented behavior

When deciding whether to produce a six-character `10xxxx` or `20xxxx` component,
count its matching stocked magnet sub-assembly as coverage of that component:

| Machined component | Additional stock checked | Match rule |
| --- | --- | --- |
| `100040` | `110040` | Replace `10` with `11`; retain the four-character suffix |
| `200040` | `210040` | Replace `20` with `21`; retain the four-character suffix |
| `100ABC` | `110ABC` | Uppercase alphanumeric suffixes follow the existing machining-code rules |

The business assumption is one stocked magnet sub-assembly per machined part,
with compatible stock units. This is an exact identifier match, as requested;
the code does not infer other substitutions from descriptions, reference codes,
cross-suffix BOM compositions, or other item families.

```text
planning_stock = base_item_actual_stock + max(matching_magnet_actual_stock, 0)
shortage       = required_quantity - planning_stock - existing_eligible_WO_supply
```

Only the Sales Order planner already includes existing Work Order supply.
Reorder and legacy checks retain their respective existing supply rules.
If coverage is sufficient, no new Work Order is created. Partial magnet stock
reduces the shortage; the existing production buffer is applied afterward.
For demand 10, component stock 2 and magnet stock 3, the shortage is 5. The
Sales Order planner therefore requests `ceil(5 × 1.2) = 6` units. Ten magnet
assemblies alone cover demand of ten and require no component production.

Absent counterpart Items/Bins contribute zero. Negative **net** magnet stock
across the eligible warehouses contributes zero rather than causing additional
component production. Negative base-item stock retains its previous effect.
Other item families, longer historical codes, lowercase suffixes and invalid
codes receive no additional coverage. The mapping is one-way: an `11xxxx`
request does not gain coverage from `10xxxx` stock.

This changes planning availability only. It does not post Stock Entries, move
or disassemble magnet assemblies, replace BOM material rows, allocate physical
stock, or include unfinished `11`/`21` Work Orders. Native manufacturing still
requires the stock Items specified by the actual BOM. If a downstream BOM
requires the bare component itself, fulfilling it from an assembled component
needs the appropriate reviewed manufacturing/material flow separately.

## Paths audited and changed

| Entry point | Existing behavior | Change |
| --- | --- | --- |
| `create_work_orders_based_on_reorder_levels` → `get_stock_balance` | Daily job. Selects manufacturing Items with default BOMs, excluding `4%`/`5%`; compares stock against `Item.reorder_level`; creates drafts or calls `delete_draft_wo`. | `get_stock_balance` delegates to the shared bulk planning-stock function, which includes the matching magnet Item. |
| `plan_machining_work_orders_from_sales_orders` → `_get_stock_balance_for_items` | Daily job and whitelisted API. Explodes open submitted SO demand, groups by machining Item/company, deducts stock and eligible machining WOs, and reconciles managed drafts. | Query both base and exact counterpart in one parameterized Bin query; add positive net counterpart stock to base coverage. Existing demand, dates, buffer and draft reconciliation remain in effect. |
| `check_and_create_work_orders` | Legacy whitelisted API. Reads direct BOM Items and Work Order required quantities, checks stock-summary balances, then creates and submits missing-component WOs. | Add the matching counterpart's stock summary. Check Item existence first because `get_stock` throws for an unknown Item. |

Both daily jobs are registered in `amf/hooks.py`, with reorder planning listed
before Sales Order machining planning. Neither legacy `check_and_create_work_orders`
nor `on_submit_work_order` is registered in the current Work Order document
hooks. Current hooks generate QR codes and update estimated manufacturing time.
Database scripts or external API callers can still invoke the whitelisted legacy APIs;
absence of a repository caller does not prove they are unused in production.

Warehouse scope is deliberately retained:

- Reorder and Sales Order planning: `Main Stock - AMF21` and `Assemblies - AMF21`.
  QC, WIP and all other warehouses do not count here.
- Legacy missing-component check: `stock_summary.get_stock` includes all Bin
  warehouses whose names do not match `%OLD%`. It has a broader scope, including
  eligible QC/WIP stock, just as before. The magnet check uses that same scope.
- Explicit `get_stock_balance(..., warehouse=(...))` callers use that scope for
  both Items. This module's function is a planning balance, not a physical balance
  of the base Item; do not use it for stock ledger posting or valuation.

The shared mapping helper reads `machining_include_magnet_stock` from site
configuration, defaulting to enabled. Setting it to numeric `0` or string `"0"`
disables the added coverage in all three paths. No schema migration or new
Custom Field is needed. Source changes, tests and this document are the only
repository edits made for this task; pre-existing unrelated changes were retained.

## Existing findings requiring separate follow-up

These are source-audit findings, except for the explicitly identified live
dry-run observations below. They were not silently changed as part of the
stock-coverage request. High priority means possible wrong quantities, deleted
planning data or overly broad write access; medium means a material limitation
that depends on how these APIs and planning jobs are used.

| Priority | Location | Finding, effect and recommended correction |
| --- | --- | --- |
| High | `delete_draft_wo` | Deletes every Administrator-owned draft for the Item with `force=1`, without a planner ownership marker, company or BOM restriction. It can delete manually entered or Sales Order planner drafts. Restrict cleanup to explicitly owned drafts and preserve or audit their previous values. Magnet coverage can cause this existing branch to run for additional Items. |
| High | `plan_machining_work_orders_from_sales_orders`, `_delete_managed_draft_work_orders` | Fully covered demand, duplicate managed drafts and stale full-run demand cause actual draft deletion. Ownership is inferred from a description substring; manually editing/removing that text changes ownership classification. Use a dedicated immutable marker and recoverable cancellation/archive or persisted snapshots if draft restoration is required. The new stock coverage changes which rows enter this existing cleanup branch. |
| High | Both daily planning jobs | Reorder and SO demand are planned independently. There is no shared stock reservation or combined demand model. Reorder drafts can be treated as SO supply; reorder cleanup can delete SO planner drafts. Separate runs may reuse the same actual stock for independent demand. Coordinate both jobs under one supply/demand allocation model. |
| High | `_get_stock_balance_for_items`, legacy stock checks | `actual_qty` is on-hand quantity, not unreserved/available stock. Reservations and other commitments are not deducted. Matching magnet stock follows this existing policy. A component committed elsewhere can therefore suppress new production. Define the business availability policy before changing the quantity source. |
| High | `_get_demand_key`, stock initialization, warehouse constants | SO demand/open WOs are company-scoped, but stock is aggregated from the two fixed AMF21 warehouses without a company join and reused for each company key. The API accepts another company. Other companies can receive AMF stock coverage or AMF warehouse defaults. Scope warehouses and inventory to the demand company. |
| High | Whitelisted SO planner | The API accepts stock/date/company filters and uses `frappe.get_all`, `insert/save(ignore_permissions=True)` and forced deletion without an explicit planning role check. Authentication alone does not establish authorization to run this administrative reconciliation. Add a role gate and company access checks before exposing it to general authenticated users. Native insert/submit permission checks still apply to the other creation APIs unless explicitly bypassed. |
| High | `check_and_create_work_orders` | Multiplies `Work Order Item.required_qty` by `BOM Item.qty`. ERPNext V12 already computes required quantity as material stock quantity / BOM output quantity × WO quantity in `set_required_items`/`get_bom_items_as_dict`. Example: WO quantity 5, BOM material quantity 2 and BOM output 1 yields required quantity 10, then this legacy method incorrectly checks 20. Reconcile against the existing stock-UOM required quantity once. |
| High | Same legacy check | Iterates direct BOM rows but derives a dictionary from WO required rows, which may be exploded. Repeated required Item codes are overwritten by the dictionary comprehension. Duplicate BOM lines can independently append shortages; repeated calls have no creation idempotency guard. Aggregate the appropriate material layer once and reconcile with already planned supply. |
| High | `_create_or_update_draft_machining_work_order`, planner exception handling | A per-Item exception is logged without rollback to a savepoint. An earlier insert/save or duplicate deletion for that Item may already have happened. A later success can commit partial changes. Use per-Item savepoints or fail the atomic run and roll back all changes. Covered/stale deletion branches are outside the per-Item try block. |
| High | Legacy creators, reorder creator, `make_stock_entry`, `delete_draft_wo` | Explicit commits inside loops and utility calls make the surrounding operation partially irreversible when a later Item fails. `commit_database` also wraps commit in `custom_try`, which can hide failures. Move transaction control to the request/job boundary and propagate errors. Changing the new flag does not reverse data already committed by these old paths. |
| High | Reorder creator and managed-draft reconciliation | Read-then-create checks have no lock or uniqueness constraint for one managed WO per Item/company. Simultaneous scheduler/API runs can both see no draft and create duplicates. Serialize planning and lock the planning key or implement a database-backed unique key. |
| Medium | `_get_open_work_orders_by_item`, `_consume_due_work_order_supply` | Counts draft non-planner WOs as supply, treats missing dates as immediately usable, and uses quantity minus produced quantity without reservation/stock-allocation reconciliation. Drafts may never be submitted; undated supply can suppress urgent production. Define which WO states/dates are firm enough for coverage. Only base machining WOs are queried; unfinished magnet assembly WOs are deliberately not added by this change. |
| Medium | Date-filtered SO planner calls | Demand is aggregated across the supplied SO date window but an existing managed draft is selected by Item/company, not by window. Running for a subset can overwrite a draft that previously represented full demand. Either restrict production reconciliation to full runs or give windows separate ownership. |
| Medium | `_collect_machining_components_from_bom`, `_get_valid_child_bom` | SO planning explodes intermediate assemblies without deducting their stock, apart from the new exact 11/21 coverage at the machining layer. A pinned child BOM is checked for active/submitted status but not Item/company agreement, and traversal does not apply every native BOM explosion/manufacturing flag. Cycles return an empty subtree rather than an explicit skipped reason. Validate these relationships and decide where stocked assemblies should stop explosion. |
| Medium | `create_work_orders_based_on_reorder_levels`, `process_bom_and_create_work_orders` | Initial Item query does not filter disabled Items; it uses the legacy header reorder level rather than warehouse-specific reorder rows. Creation selects active/default BOMs without `docstatus=1`, treats any existing open matching WO as sufficient regardless of remaining quantity/date, truncates `required_qty * 1.2` with `int`, and assigns `CMZ` for both 10 and 20 families. Recursion is commented out. The function name overstates its current sub-assembly planning behavior. Review these rules separately. |
| Medium | `make_work_orders`, `make_work_order`, `create_work_orders` | Manual/SO creation paths do not check magnet stock; these explicit creation APIs remain explicit. `make_work_orders` compares pending quantity to the entire SO line quantity, not a locked remaining balance after other WOs. The excess WO has an SO Item link but no SO header link. There is no retry/idempotency key. Helpers also use hardcoded company/warehouse defaults or `int(qty)` truncation. Add explicit finite positive-quantity and linked-document validation before creation, retaining native validations. |
| Medium | `get_default_bom`, `check_sub_assembly_items`, `on_submit_work_order`, `get_exploded_items` | `get_default_bom` does not require active/submitted status. `check_sub_assembly_items` has no cycle guard/deduplication and makes recursive per-Item queries. `on_submit_work_order` is whitelisted but only returns sub-assembly codes; its name/comment does not make it an active submit hook. `get_exploded_items` reads direct BOM Items and only Main Stock despite its name; its old recursive caller is commented out. Clarify contracts and remove inactive scaffolding after caller review. |
| Medium | `make_stock_entry` | Inserts, submits and commits a Stock Entry internally. `qty or remaining_qty` interprets explicit zero as the entire remaining quantity. Native validations handle manufacturing and stock constraints, but callers cannot atomically include this in a larger rollback scope. Give this helper clear quantity and transaction semantics in a separate change. |
| Low | Module imports/logging/stubs | Wildcard `utilities` import, numerous `print` statements, an unused Desk URL and the unused always-true `should_generate_work_order_for_item` stub obscure dependencies and put document details in process logs. Prefer explicit imports and structured logging after functionality is covered. |

The automatic SO planner's active/submitted default-BOM check, branch-local
cycle prevention, stock query batching, demand aggregation, ceiling-based
buffering, and explicit dry-run support are useful existing protections. The
new change retains them. No V12 framework or ERPNext core source was edited.

## Verification and observed effect

The new unit test module has 27 tests. It runs against the installed Frappe and
ERPNext code with persistence mocked, without initializing a site. It covers
both prefix families, alphanumeric suffixes, exact matching, invalid codes,
empty/missing stock, negative balances, warehouse parameters, one-way coverage,
full/partial coverage in all creation paths, SO aggregation without reusing
counterpart stock, due versus late base-WO supply, managed-draft dry-run cleanup,
and feature-disable behavior in all three paths.

```sh
# From /home/libracore/frappe-bench; no database connection required:
env/bin/python -m unittest amf.amf.utils.test_work_order_creation -v
```

A second verification initialized `site1.local` and used one MariaDB
`START TRANSACTION READ ONLY` transaction. An additional SQL guard rejected
non-read statements and a commit guard rejected commits. It loaded the exact
original file backup, compared the original full SO dry run to the new planner
with coverage disabled, then compared the enabled planner against that same
snapshot. It also checked all 138 reorder-eligible machining Items against
actual grouped Bin balances and exercised the old/new single-Item SQL on five
stocked examples. No work orders were created, changed, submitted or deleted
by this verification, and the transaction ended with rollback.

Observed results on 2026-11-03:

| Measurement | Original | Magnet stock enabled |
| --- | ---: | ---: |
| Open SO source rows | 43 | 43 |
| Aggregated machining demand rows | 23 | 23 |
| Proposed new drafts | 0 | 0 |
| Proposed draft updates | 18 | 8 |
| Proposed draft deletions under existing cleanup | 0 | 10 |
| Skipped source/result rows | 18 | 18 |

Fifteen demand rows have reduced shortages. Examples: `100040` shortage 5 → 0;
`100045` shortage 70 → 5; `200030` shortage 600 → 325; `200040` shortage 51 → 3.
Of the 138 checked reorder machining Items, 66 have positive corresponding
magnet stock. No existing skip reason changed. These counts are a snapshot,
not a guarantee for the next run after Sales Orders or stock change.

**Operational consequence:** the existing planner would delete ten managed
drafts on this snapshot because the added stock makes their demand fully
covered. The reorder planner also retains its broad Administrator-draft
deletion behavior. This task did not run either job in write mode or restart
production processes. Existing processes can retain imported old code until
reloaded; new imports use the edited source.

The read-only harness also ran the 27 new tests plus the four existing estimated
manufacturing-time tests: **31 passed**. The latter tests need initialized
Frappe system-setting context for rounding, so their initial site-free invocation
was inconclusive; they passed in the guarded initialized run. Python compilation,
diff whitespace, source-backup hashes, reversible-patch applicability and the
rollback script's no-write check were also verified. No production write-flow
integration or concurrency test was performed.

## Artifacts and rollback

The evidence directory is outside the AMF Git repository, inside the bench:

```text
/home/libracore/frappe-bench/reports/work_order_magnet_stock_2026-11-03/
```

It contains:

- `manifest.json`: baseline commit and original/modified source SHA-256 hashes.
- `work_order_creation.py.before`: byte-for-byte original source, saved before editing.
  Original SHA-256: `def04a63758929a5b5bec9ff65b48b2464586a20952cc64e2dd14d1e21b84520`.
- `work_order_creation.patch`: runtime-source-only Git patch.
- `rollback.py`: hash-guarded source restore; defaults to checking without writing.
- `verify_read_only.py`, `verification_summary.json`, `unittest.txt`: reproducible
  guarded comparison and test results.
- `planner_before.json`, `planner_after.json`, `planner_changes.json`: full
  proposed planner actions and changed shortages. These are read-only previews,
  **not** complete Work Order document backups.
- `reorder_stock_coverage.json`: checked component/counterpart balances.

### Disable the added coverage

```sh
cd /home/libracore/frappe-bench
bench --site site1.local set-config machining_include_magnet_stock 0
```

Reload the site's web, worker and scheduler processes using the normal deployment
procedure, for example `bench restart`. Setting the key to `1` enables coverage
again. Do not run these configuration/restart commands merely to review the
change; they are documented operator actions and were not executed in this task.
The feature defaults to enabled if the key is absent. The disabled full planner
result was verified equal to the original full dry run on the same stock snapshot.

### Restore the original source

```sh
cd /home/libracore/frappe-bench
# Safe check; makes no changes:
env/bin/python reports/work_order_magnet_stock_2026-11-03/rollback.py
# Actual restoration, when needed:
env/bin/python reports/work_order_magnet_stock_2026-11-03/rollback.py --apply
```

The script checks both the original backup and current source against the
manifest before writing. It refuses to overwrite subsequent source edits. On
restoration it saves the replaced version as `work_order_creation.py.pre-rollback`.
Then reload web, worker and scheduler processes. The audit/test/evidence files
can remain for review. No database migration is involved.

**Code rollback and data recovery are separate.** Disabling coverage or restoring
the source does not restore drafts deleted by a later live planning run, undo
quantity changes, or cancel work already submitted. Before an operator runs the
planner in write mode, retain full snapshots/backups of affected Work Orders,
including child rows and attachments, if document-level recovery is needed.
The saved dry-run action lists identify proposed changes but cannot recreate
every original draft field. Review affected records individually; do not bulk
cancel manufacturing records to reverse this stock-coverage change.
