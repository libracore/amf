# Item Creation audit and existing-head/Product-only update — 29 October 2026

AMF `0.7.8` accepts existing Valve Heads whose existing components have different suffixes and adds **Create Products Only**. New head/component families retain matching suffixes. This updates the reuse finding in the [28 October audit](item_creation_audit_2026-10-28.md); its separate authorization, legacy-hook and engineering-specification findings remain on the [improvement tracker](item_creation_improvements.md).

The baseline was AMF `0.7.7`, commit `0708267`, on the local Frappe/ERPNext v12 installation `site1.local`. Unrelated workspace changes are excluded. Catalogue inspection used database-enforced read-only transactions. Submission tests prohibited nested commits and rolled back their business records, reservations and generated files.

## Exact reported case

The error came from applying the new-family suffix policy recursively to an existing submitted head definition. It did not demonstrate that the selected parts were incompatible.

| Record | Observed submitted/default definition |
| --- | --- |
| Head `300080` | `VALVE HEAD-S-1-3-050-C-P`; default `BOM-300080-001` |
| Its plug `110137` | Qty `1`, pinned `BOM-110137-001`; consumes `100137` through `BOM-100137-002` and three magnets |
| Its seat `210056` | Qty `1`, pinned `BOM-210056-004`; consumes `200056` through `BOM-200056-003` and two pins |
| Head R&D reference | Empty; reuse must preserve the existing Item without inventing a master reference |
| P201-O Product | Enabled `420100` owns unique reference `P201O300080`, has its existing catalogue name, and has no default BOM |
| Preferred-code history | Disabled `/420080` remains a retired alias occupying canonical code `420080` |

The existing head and parts are now accepted. The complete plan reports their independent numbering and shows their pinned recipes. New Product names can fall back to the explicit head code when a reused head lacks an R&D reference. When the exact Product reference already exists, its existing Item name/reference are retained.

For P201-O, the resulting plan reuses Item `420100` and proposes one new automatically submitted Product BOM. It does not allocate another Item for the same unique reference, rename/reactivate an Item or repair the historical head chain.

Two nested raw-stock rows retain `stock_uom=Nos`, while their `uom` and the material Items use `Meter`. Their conversion factors are `1` and `stock_qty=qty` (`0.02` plug, `0.03` seat). Reuse now shows explicit warnings for this consistent legacy label case. Other mismatches remain errors; submitted manufacturing records are preserved for separate engineering review.

## Implemented policies and algorithm

| Situation | Behavior |
| --- | --- |
| New head/components | Allocate/check a shared suffix throughout the newly created family; reservations and insertion guards remain enforced. |
| Existing head, actual existing components | Accept independent suffixes. Validate enabled Items, submitted active BOMs, company, positive quantities and the recursive graph; show the actual pinned revisions. |
| Existing head, changed selected components | Require **Propose Replacement BOMs** and a fresh review. A trusted execution context permits the reviewed existing-head replacement; standalone new mixed-family BOMs remain subject to existing guards. |
| **Create Products Only** | Require an existing head and at least one valid Product configuration. Execute only Product actions. Hidden seat/plug input values cannot create/replace head components. Product replacement mode leaves the head chain preserved. |
| Matching Product already exists | Reuse an enabled Product with the exact configuration prefix and globally unique body/head/syringe reference, including an independent suffix. Preserve its Item identity and compare its BOM normally. |
| New Product code needed | Prefer configuration prefix + head suffix. Otherwise search free decimal suffixes `001`–`999`, then remaining uppercase alphanumeric suffixes within that prefix. Keep six characters. |
| Occupied/retired code | Include disabled Items, canonical retired aliases, exact member reservations and other planned codes. Never silently replace an explicit override. |
| Reference owned by another unsuitable Item | Reject during preview with the owning Item identified, before a SQL uniqueness error. Do not invent a different reference. |
| Concurrent catalogue change | Rebuild the plan under dependency/current inventory locks on submission. A changed code/recipe/dependency requires fresh review; exact member reservations remain the final insertion guard. |

The shared planner implements preview, suggestions, approval and submission. Product inventory/reservations are read once per plan. Repeated existing-chain visits are cached by Item/BOM revision, while cycle detection remains path based. The derived **Suggested Product Code** column is separate from editable overrides and excluded from browser input stamps. Stale suggestion responses are discarded.

The additive mode/column schema patch reloads only `Item Creation Variant` and `Item Creation`, then clears their caches. Plan version increases from `3` to `4`; earlier draft approvals require refresh/review. Historical submitted/cancelled snapshots and result links remain intact.

## Catalogue recheck

A read-only planner pass over all **101 enabled heads** accepted **94** in approximately **1.45 seconds**, with no Product configurations selected. This measures structural reuse preflight, not physical approval of every design or all possible Product configurations. The current catalogue contains one more enabled head than the prior audit; the earlier 100-head counts describe that earlier snapshot.

| Remaining head | Blocking condition |
| --- | --- |
| `300057`, `300100`, `300110`, `300111`, `300138` | No selected default production BOM |
| `300092` | Invalid quantity for `RVM.1204` in `BOM-300092-004` |
| `V-Template` | Template does not have a managed six-character head code |

These records were not repaired. Missing/inactive BOMs, disabled components, cycles, inconsistent stock conversions and company mismatches continue to block reuse. Existing cross-suffix composition alone no longer blocks it.

## Verification and deployment

- **162 focused/regression Python tests** and **15 read-only initialized-site Work Order/report tests** passed. Coverage includes strict new families, legacy reuse, disabled/cyclic dependencies, replacement boundaries, Product-only isolation, code exhaustion/rollover, aliases/reservations, unique reference owners and stale approvals.
- Actual form-script Node tests passed: mode switching, preserved head selection, read-only mode fields, code suggestions without override mutation, stale responses and existing engineering-review/preview behavior.
- The exact real `300080` case completed review and automatic submission of a new Product BOM on `420100` in approximately **2.4 seconds**. A repeated request reused that Product and BOM. SQL snapshots of all five original head/component Items and their BOM headers/material rows remained identical.
- A second real rollback-only case created a strict new head family, submitted a reviewed head replacement using existing `110137`/`210056`, and allocated a new independently numbered Product after retiring its preferred code. It pinned the reviewed replacement and preserved all borrowed component records.
- An injected failure during result-link recording rolled back the complete Item/BOM/request/result/reservation transaction. Nested commits were prohibited in write-path tests; temporary QR files were removed with rollback.
- Targeted metadata installation exposes the new mode and suggestion column without changing Item/BOM/request counts. The repeatable registered patch is `amf.patches.v12_0.update_item_creation_existing_head_products`; it is available to the next standard migration. No broad migration, pending 4D changes or paused cost writers were run.

Deploy Python/form code together and use the normal web/worker reload plus browser refresh. Save and refresh existing draft requests, then record fresh engineering review before submission. No live Product/BOM was retained from the tests. Full browser, multi-process concurrency and complete repository-suite testing are outside this verification.

User instructions: [engineering workflow](item_creation_engineering_workflow_2026-10-27.md). Remaining proposals: formal authorization policy (including older lookup helpers), revision/transaction ownership outside this workflow, structured specifications, versioned engineering templates, historical corrections, company costing policy and platform migration.
