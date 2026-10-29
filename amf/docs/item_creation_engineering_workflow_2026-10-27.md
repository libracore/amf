# Item Creation: engineering workflow implementation

Updated 29 October 2026. This extends the [numbering implementation](item_creation_algorithm_implementation_2026-10-27.md) and implements the five improvements selected after the [original audit](item_creation_audit_2026-10-27.md), plus the [existing-head/Product-only update](item_creation_audit_2026-10-29.md). The maintained backlog is [item_creation_improvements.md](item_creation_improvements.md).

## User workflow

1. Define a new head or select an existing enabled head. Component names, references, material tags and drawings remain explicit engineering inputs. Ordinary names receive suggestions; custom names are not reconstructed by guessing missing fields.
2. For each newly machined plug/seat, choose the exact raw-stock Item and review consumption per finished component. At the user's request, new documents prefill `0.02` for the plug and `0.03` for the seat; both are editable and expressed in the selected stock UOM, which is displayed automatically. Quantities remain positive and limited to the v12 BOM field capacity. Different grades and diameters are separate stock choices; no stock Item is selected automatically.
3. Enable the desired product families, open **Choose Product Configurations**, and select individual supported body/syringe combinations. The chooser displays every available combination in enabled families, including HV and HD, with highlighted head-requirement notes where geometry is incomplete or incompatible. Resolve those requirements before review. The selection is retained as child rows; family checkboxes alone do not generate a Cartesian product.
4. Save the request, then open **Refresh Complete Plan**. Resolve every error. The plan displays every planned Item/BOM action, materials, quantities per output unit, stock UOMs, manufacturing flags, scrap outputs and exact child BOM revisions. Existing dependency recipes can be expanded.
5. When a default BOM differs, explicitly enable **Propose Replacement BOMs**. Review the existing/proposed definitions side by side, including removed operations and affected parent revisions.
6. A System Manager with request write/submit permission records engineering review notes. The server stores the exact plan, dependency snapshot, input/plan hashes, reviewer and timestamp in protected review history. Review does not create Items or BOMs.
7. Submit. The server rebuilds the approved plan under dependency locks, rejects changes, creates missing Items and automatically submits all new/replacement BOMs in dependency order. A structured execution result links every created/reused Item and BOM to the request.

Editing reviewed inputs marks the request **Stale** and clears its current approval while retaining review history. Changed dependencies also invalidate approval at submission, even if the request itself was unchanged. Reviewed history and execution results cannot be edited through the ordinary document API.

The existing System Manager authorization is retained. Separate engineering roles and mandatory separation of preparer/reviewer remain a distinct permissions-policy improvement.

## Existing heads and Create Products Only

Existing heads may use existing plug/seat Items with independent suffixes. The actual submitted BOM revisions determine their composition. For example, head `300080` already consumes plug `110137` and seat `210056`; this is accepted and shown in the review. New heads, new machined components and their new sub-assemblies still use matching suffixes. Selecting different parts for an existing head requires **Propose Replacement BOMs**, review of the exact differences and a new default head revision. Existing submitted revisions and their parents keep their links.

To assemble Products using a head as it stands:

1. Enable **Create Products Only** and select the existing **Valve Head**. The head definition is read from its Item master; seat/plug creation fields are hidden.
2. Select the company/warehouse and the Product accessories/quantities required by the existing recipes. Enable the Product families, then use **Choose Product Configurations** to select individual combinations.
3. Use **Suggest Product Codes**, or refresh the complete plan. The configuration table displays a read-only **Suggested Product Code** beside the optional editable **Product Code** override. A suggestion never overwrites an explicit override.
4. Save, refresh the plan, record engineering review and submit. Only Product actions execute. The existing head/component BOMs are pinned dependencies and are preserved, including when **Propose Replacement BOMs** is used to review an existing Product recipe.

For existing-head requests, blank overrides first reuse an enabled Product with the same body/head/syringe engineering reference. Otherwise, the suggestion uses the configuration prefix plus the head suffix when free. If occupied or retired, it takes the first free suffix in that same three-character prefix: `001`–`999`, then the remaining uppercase alphanumeric tokens. All codes retain six characters. Disabled Items, retired aliases and member reservations block reallocation. Availability and dependencies are rechecked at review/submission; a changed suggestion invalidates the approval.

In the inspected catalogue, P201-O with head `300080` suggests existing Product `420100`, which already owns reference `P201O300080`. Its missing Product BOM can be created after review. The retired `/420080` alias remains reserved. A duplicate Product is not created just to retain suffix `080`; the existing Item name/reference are preserved.

AMF `0.7.9` adds **Change Product Reference** directly beside a reference-conflict error. The dialog shows the generated reference and existing owner. Enter a unique reference, apply it, save the request and refresh/review the complete plan. For example, the disabled `/410080` owns `P200O300080`; an entered `P200O300080-R1` can distinguish the planned Product if that reference is available. The optional **Product Reference** field is also available in the expanded configuration row. Clearing it restores the generated reference. Reopening the chooser retains the entered value.

The override applies to the planned Product; existing Item masters retain their identities. It must contain the selected head code exactly once, be a single line of at most 140 characters, and be unique against existing Items and other selected configurations. An explicit code pointing to an existing Item with another reference remains an identity conflict: clear the Product Code override to obtain an available code, or review that master separately. Reference changes invalidate approval. Assembly screw/cap selections and quantities remain required by their Product recipes. See the [reference-override release record](item_creation_product_references_2026-10-29.md).

Some legacy raw-material rows retain a stale `stock_uom` label. Reuse is permitted with an explicit plan warning only when the row's `uom` already equals the current Item stock UOM, conversion is exactly `1`, and `stock_qty` equals `qty`. No submitted row is rewritten. Invalid quantities, inconsistent conversions, disabled components, missing/inactive/unsubmitted BOMs, cycles and company mismatches remain errors.

## Explicit compatibility policy

[item_creation_compatibility.py](../amf/utils/item_creation_compatibility.py) owns the versioned rules. They combine the catalogue relationships evaluated in the audit with the user's explicit authorization of both U syringes for standard LV bodies on 27 October 2026.

| Family | Bodies | Syringe tokens | Head requirements |
| --- | --- | --- | --- |
| RVM | Enabled `511___`/`521___` Body variants; Mini `5D1000`, `5D1001`, `5D1002` | No syringe | Standard head; observed D, DS, O, OS, S, B, DA, SA, SL, T, SPLIT and SPLITS types. |
| LV | `551000`, `571000`, `591000`, `5B1000` | `2`, `3`, `4`, `5`, `8`, `9`, `D` | Standard D/DS head. |
| HV | `561000`, `581000`, `5A1000`, `5C1000` | `E`, `F` | D/DS head with an explicit HV designation. Customer suffixes such as `-HV MGA` are recognized. |

Every selected Body/Syringe must also exist, be enabled and belong to its correct Item Group. Duplicate combinations, unsupported pairs and selections whose family checkbox is cleared are errors. New head/component families use the same reserved suffix; Products may use independently numbered codes while their reference and BOM identify the selected head.

AMF `0.7.5`, rule version `2026-10-27.2`, permits `704000` (`S-100-U`) and `709000` (`S-500-U`) with all four standard LV bodies, as explicitly authorized by the user. The chooser and manually selected rows use the same rules. Their enabled state, exact U reference, head geometry and request engineering review remain required. Historical disabled Products are not reactivated. HV bodies continue to permit only `70E000` and `70F000`. Other interfaces/families, including the pending 4D interface BOMs, still require a reviewed rule update.

The rule-version change invalidates earlier draft approvals at submission; refresh the complete plan and record a fresh engineering review. Submitted/cancelled requests retain their original recorded snapshots. With the `0.7.11` RVM variant extension and the current catalogue, the maximum standard selection is five head-chain Items plus 40 Products: 45 Items/BOMs. Additional enabled `511___`/`521___` variants can extend that catalogue; requests are bounded to 256 configurations.

These rules enforce the supported standard configuration matrix, head type and volume class. The review records the engineering decision for the exact geometry, materials, stock dimensions and accessory quantities; catalogue frequency is not proof of physical compatibility for a new design.

AMF `0.7.6` makes HV and HD choices explicit instead of hiding choices whose head requirements have not yet been met. Both pump-family checkboxes say **including HD**. Chooser labels identify LV/HV and the HD drive; head errors use the same helper as the server's selection validation. Showing a configuration does not approve incompatible head geometry.

| Configuration | Body Item | Chooser family/drive | Syringes |
| --- | --- | --- | --- |
| P202-O base / RS485 / CAN | `5D1000` / `5D1001` / `5D1002` | RVM mini | None |
| P200-O and variants | `511___` | RVM | None |
| P201-O base / RSB / RS485 / LPH / AIR / ELV / SYS | `521000`–`521006` | RVM | None |
| P211-O NM/TH | `521101` | RVM | None |
| P100-O / P100-L | `551000` / `571000` | LV | Standard LV set, including approved U variants |
| P110-O / P110-L | `591000` / `5B1000` | LV / HD | Same LV set |
| P101-O / P101-L | `561000` / `581000` | HV | `70E000` (`S-2500-P`), `70F000` (`S-5000-P`) |
| P111-O / P111-L | `5A1000` / `5C1000` | HV / HD | Same HV set |

AMF `0.7.10`, compatibility version `2026-10-29.1`, adds **P202-O (RVM mini)** under **Rotary Valves (including RVM mini)**. Enable that family, open **Choose Product Configurations** and select body `5D1000` without a syringe. Its suggested Product code is `4D0` plus the head suffix, subject to existing matching-Product reuse and collision handling. Its generated reference is `P202O` plus the full head code. Code/reference overrides, Product-only mode, engineering review and automatic BOM submission use the same workflow as other RVM configurations.

Mini assembly recipes consume one body, one selected head, the selected assembly-screw quantity and one selected head cap. These accessories remain explicit inputs. New Mini Products use the observed `0.10 Kg` catalogue weight; reused Item weights are preserved. Existing recipe exceptions remain visible and require reviewed replacements; for example, `4D0040` includes shipping foam. RS485/CAN bodies `5D1001`/`5D1002` and pending interface BOMs are not enabled by adding the requested base configuration. The registered `update_item_creation_rvm_mini` patch reloads only parent-form guidance metadata and clears its cache. See the [RVM mini release record](item_creation_rvm_mini_2026-10-29.md).

AMF `0.7.11`, compatibility version `2026-10-29.2`, extends that base release to Mini RS485/CAN and every enabled `511___`/`521___` Body Item. New matching body records with supported P200-O/P201-O/P211-O/P221-O reference definitions appear automatically; incomplete/unknown definitions are shown as requirements for Item-master review. See the [complete RVM variant mapping](item_creation_rvm_variants_2026-10-29.md). No Body master is created by choosing a configuration.

Variant references retain the head between the family and interface suffix: e.g. `P201O300080RS485`, `P202O300080/RS485`, `P202O300080/CAN`. `521101` retains Product prefix `430` and reference `P211O` + head. Variants sharing prefix `420` receive distinct free codes; the base configuration retains the head-suffix preference when available. This also works for a newly created head, with matching head/component suffixes. Suggested Product dependencies are loaded in a batch and row reordering does not change the allocation.

LPH I2C addresses/customer settings are not inferred from body `521003`; enter the exact **Product Reference** for such a configuration, e.g. the existing `P201O300041I2C2LPH`. Assembly screw quantity and cap remain explicit shared request inputs; use separate reviewed requests when variants require different accessories. Existing recipe disagreements remain replacement-review requirements. Historical pending interface BOMs remain untouched unless separately requested/reviewed through the normal workflow. Canonical variant lookup in Quotation uses the same prefix/reference rules; arbitrary reference overrides still require direct Item selection until broader discovery is implemented.

The registered `update_item_creation_rvm_variants` patch updates only parent guidance metadata. During verified execution, BOM names are allocated without overwriting historical names left behind by Item renaming; actual new revisions remain pinned through the dependency results. No historical naming/record repair is performed.

## Complete recipes and replacements

Each newly defined component now receives its own raw-material BOM before its subassembly BOM. A complete new head therefore creates five Items and five submitted BOMs: raw-stock-to-plug, plug subassembly, raw-stock-to-seat, seat subassembly and head.

AMF `0.7.6` adds the user-requested new-document consumption defaults: seat `0.03`, plug `0.02`. They are editable suggestions in the selected stock UOM and remain part of the engineering review. Changing stock or refreshing the form does not overwrite an entered consumption. Existing saved request quantities are not backfilled or altered.

Pins/magnets are explicit quantities. Zero means a reviewed design without that accessory; negative quantities are rejected. LV laboratory recipes include `T100` and retain adapter scrap treatment. HV recipes consume the adapter and include the selected screw quantity. Syringe descriptions use µL and show the corresponding mL value where useful. The planner includes the Item-derived manufacturing flag, matching v12's BOM field fetch behavior.

Compatible existing Items/BOMs are reused. Item identity conflicts are errors, requiring Item-master review separately. BOM comparison normalizes quantities per output unit and includes UOMs, conversions, manufacturing flags, scrap, company, operations and child revisions. A different recipe requires explicit replacement mode and a recorded approval.

Replacement creates a new submitted default revision. Existing submitted recipes and their parent material/child-version links are preserved. Parent impact is displayed for review; this workflow does not propagate replacement revisions through existing parents. Item valuation rates are not seeded with guessed constants or overwritten during reuse.

## Implementation and performance

- [item_creation_plan.py](../amf/utils/item_creation_plan.py): read-only planner, bulk dependency catalogue, normalized recipe differences and stable review fingerprints.
- [item_creation_recipes.py](../amf/utils/item_creation_recipes.py): pure shared component and product recipe definitions.
- [item_creation_workflow.py](../amf/utils/item_creation_workflow.py): authorized preview/review APIs, approval protection, locked submission validation and execution/results.
- [item_creation.py](../amf/doctype/item_creation/item_creation.py): controller lifecycle, numbering and read-only compatibility adapters.
- [item_creation.js](../amf/doctype/item_creation/item_creation.js): guided form, explicit variant chooser and complete plan rendering.
- `Item Creation Variant` and `Item Creation Review`: selected configurations and immutable per-request engineering reviews.

Preview and execution consume the same recipe data. Syringe and other dependencies are bulk-loaded once per plan rather than fetched repeatedly inside product loops. The occupied-code catalogue and family ownership are cached only inside the trusted creation context; permanent suffix/member reservations still provide the concurrency boundary.

The source transaction owns commits and rollback. Database methods are no longer monkey-patched. Execution uses direct BOM document creation; its scoped hooks propagate errors, preserve reviewed child revisions and avoid legacy per-BOM commits/logging and implicit parent propagation. Core ERPNext calculation and validation still run. Submitted recipes are checked against the approved quantities/UOMs/manufacturing flags/links after hooks execute.

The form invalidates cached plans immediately and debounces requests by 350 ms. Sequence/input checks reject old plan, head and stock-UOM responses. Preview rendering escapes user/catalogue text and uses encoded document links. Technical approval hashes and stored snapshots are hidden from the normal form.

## Verification

- The read-only live-catalogue preview for seven planned Items/BOMs passed in approximately **0.3 seconds**.
- Real approval/submission created **seven Items and seven submitted BOMs**, then approved **three replacement BOMs**. Existing Product parent BOM links remained unchanged. The complete case took approximately **10.5 seconds**.
- Before the `0.7.5` LV/U extension, the largest supported standard selection created **27 Items and 27 submitted BOMs** in approximately **35 seconds**. An HV selection created six Items/six BOMs in approximately 5.6 seconds.
- The user-authorized `0.7.5` LV/U extension passed a real review/submission for all eight added pairs: **13 Items, 13 submitted BOMs and 13 result links** in approximately **18 seconds**. Exact U references, codes and materials were verified; all temporary records/files were rolled back. The expanded maximum 35-Item plan passed the bulk-read unit check.
- Injected second-BOM failure propagated. Both changed request inputs and a changed temporary raw-stock Item invalidated approval. Request, Item, reservation and QR cleanup checks passed after rollback.
- Every write-path integration test configured nested commits to raise an error. No nested commit occurred. Test business records and generated files were rolled back.
- Real Guest access to preview and engineering review was denied in a database-enforced read-only transaction.
- Unit tests cover numbering, compatibility, raw-stock identity/UOM/quantity checks, complete plans, reuse/differences, review invalidation/protection and Product defaults. Node tests execute the actual form script, covering stale responses, safe rendering, UOM changes and saved-plan review.

Additional checks and final test counts are recorded in the improvement tracker. These timings describe this inspected site and test load, not a guaranteed production response time.

## Deployment and remaining scope

The [AMF 0.7.3 traceability extension](item_creation_traceability_2026-10-27.md) adds searchable execution result rows, reverse Item/BOM links and the request-only cancellation/amendment policy. Its registered patch follows the original workflow patch below. Syringe selection explicitly enforces `70X___`, with a digit 1–9 or a letter at `X`; existing engineering compatibility rules still apply.

AMF `0.7.2` registers `amf.patches.v12_0.install_item_creation_engineering_workflow` in `amf/patches.txt`, so the next standard migration installs the child tables before the parent form and updates the Work Order estimated-time fields for alphanumeric codes. The patch is safe to repeat and performs no historical Item/BOM repair or reservation backfill. The Product Configurations table has its own full-width section; its Body and Syringe selectors use six-character code patterns `5_1___` and `70____` without an Item Group restriction. Server-side engineering compatibility validation still applies.

The three affected DocType schemas were reloaded on `site1.local` with the targeted `sync_item_creation_schema()` helper. No broad migration or unrelated pending patches ran. Historical manufacturing data and pending 4D BOMs were not repaired or activated.

Deploy the Python/form code together and reload the installation's web/worker processes. Refresh the browser/form cache. The targeted schema command for another deployment is:

```sh
bench --site <site> execute amf.amf.utils.item_creation_workflow.sync_item_creation_schema
```

Existing draft requests need explicit raw-stock quantities, supported variant selections and recorded engineering review before submission. Historical submitted requests retain their existing records.

AMF `0.7.8` registers `amf.patches.v12_0.update_item_creation_existing_head_products` to reload the parent/variant schemas and clear their caches. Plan version `4` invalidates earlier draft approvals at validation; refresh/review them before submission. Submitted/cancelled review snapshots remain intact. Product-only requests do not require raw-stock inputs for the preserved head components.

AMF `0.7.9` registers `amf.patches.v12_0.update_item_creation_product_references` to add the optional variant field and clear variant/parent caches. Plan version `5` supersedes version `4` for new reviews; earlier draft approvals require refresh/review. The patch changes no historical Item reference or BOM.

Broader permission roles, formal versioned engineering-template maintenance, dedicated structured geometry fields, company-wide costing/settings policy, historical catalogue repair and a platform upgrade remain on the separate backlog. A full browser session and the entire repository test suite are outside the recorded verification above.
