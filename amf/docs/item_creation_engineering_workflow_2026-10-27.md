# Item Creation: engineering workflow implementation

Updated 27 October 2026. This extends the [numbering implementation](item_creation_algorithm_implementation_2026-10-27.md) and implements the five improvements selected after the [audit](item_creation_audit_2026-10-27.md). The maintained backlog is [item_creation_improvements.md](item_creation_improvements.md).

## User workflow

1. Define a new head or select an existing enabled head. Component names, references, material tags and drawings remain explicit engineering inputs. Ordinary names receive suggestions; custom names are not reconstructed by guessing missing fields.
2. For each newly machined plug/seat, choose the exact raw-stock Item and enter its consumption per finished component. The current stock UOM is displayed automatically. Quantities are positive, limited to the v12 BOM field capacity, and expressed in that stock UOM. Different grades and diameters are separate stock choices. No universal rod or consumption is selected automatically.
3. Enable the desired product families, open **Choose Product Configurations**, and select individual supported body/syringe combinations. The selection is retained as child rows; family checkboxes alone no longer generate a Cartesian product.
4. Save the request, then open **Refresh Complete Plan**. Resolve every error. The plan displays every planned Item/BOM action, materials, quantities per output unit, stock UOMs, manufacturing flags, scrap outputs and exact child BOM revisions. Existing dependency recipes can be expanded.
5. When a default BOM differs, explicitly enable **Propose Replacement BOMs**. Review the existing/proposed definitions side by side, including removed operations and affected parent revisions.
6. A System Manager with request write/submit permission records engineering review notes. The server stores the exact plan, dependency snapshot, input/plan hashes, reviewer and timestamp in protected review history. Review does not create Items or BOMs.
7. Submit. The server rebuilds the approved plan under dependency locks, rejects changes, creates missing Items and automatically submits all new/replacement BOMs in dependency order. A structured execution result links every created/reused Item and BOM to the request.

Editing reviewed inputs marks the request **Stale** and clears its current approval while retaining review history. Changed dependencies also invalidate approval at submission, even if the request itself was unchanged. Reviewed history and execution results cannot be edited through the ordinary document API.

The existing System Manager authorization is retained. Separate engineering roles and mandatory separation of preparer/reviewer remain a distinct permissions-policy improvement.

## Explicit compatibility policy

[item_creation_compatibility.py](../amf/utils/item_creation_compatibility.py) owns the versioned rules. They are based on the enabled catalogue relationships evaluated in the audit.

| Family | Bodies | Syringe tokens | Head requirements |
| --- | --- | --- | --- |
| RVM | `511000`, `521000` | No syringe | Standard head; observed D, DS, O, OS, S, B, DA, SA, SL, T, SPLIT and SPLITS types. |
| LV | `551000`, `571000`, `591000`, `5B1000` | `2`, `3`, `5`, `8`, `D` | Standard D/DS head. |
| HV | `561000`, `581000`, `5A1000`, `5C1000` | `E`, `F` | D/DS head with an explicit HV designation. Customer suffixes such as `-HV MGA` are recognized. |

Every selected Body/Syringe must also exist, be enabled and belong to its correct Item Group. Duplicate combinations, unsupported pairs and selections whose family checkbox is cleared are errors. Selected configurations use the same reserved head suffix at every layer.

`704000`/`709000` are excluded from new LV recipes because the inspected catalogue contains their Product recipes only in disabled Products. Other interfaces/families, including the pending 4D interface BOMs, are not inferred from the existence of a Body Item. Extending support requires a reviewed compatibility-rule/recipe update.

These rules enforce the supported standard configuration matrix, head type and volume class. The review records the engineering decision for the exact geometry, materials, stock dimensions and accessory quantities; catalogue frequency is not proof of physical compatibility for a new design.

## Complete recipes and replacements

Each newly defined component now receives its own raw-material BOM before its subassembly BOM. A complete new head therefore creates five Items and five submitted BOMs: raw-stock-to-plug, plug subassembly, raw-stock-to-seat, seat subassembly and head.

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
- The largest supported standard selection created **27 Items and 27 submitted BOMs** in approximately **35 seconds**. An HV selection created six Items/six BOMs in approximately 5.6 seconds.
- Injected second-BOM failure propagated. Both changed request inputs and a changed temporary raw-stock Item invalidated approval. Request, Item, reservation and QR cleanup checks passed after rollback.
- Every write-path integration test configured nested commits to raise an error. No nested commit occurred. Test business records and generated files were rolled back.
- Real Guest access to preview and engineering review was denied in a database-enforced read-only transaction.
- Unit tests cover numbering, compatibility, raw-stock identity/UOM/quantity checks, complete plans, reuse/differences, review invalidation/protection and Product defaults. Node tests execute the actual form script, covering stale responses, safe rendering, UOM changes and saved-plan review.

Additional checks and final test counts are recorded in the improvement tracker. These timings describe this inspected site and test load, not a guaranteed production response time.

## Deployment and remaining scope

The [AMF 0.7.3 traceability extension](item_creation_traceability_2026-10-27.md) adds searchable execution result rows, reverse Item/BOM links and the request-only cancellation/amendment policy. Its registered patch follows the original workflow patch below. Syringe selection now explicitly enforces `70X___`, with a digit or letter at `X`; existing engineering compatibility rules still apply.

AMF `0.7.2` registers `amf.patches.v12_0.install_item_creation_engineering_workflow` in `amf/patches.txt`, so the next standard migration installs the child tables before the parent form and updates the Work Order estimated-time fields for alphanumeric codes. The patch is safe to repeat and performs no historical Item/BOM repair or reservation backfill. The Product Configurations table has its own full-width section; its Body and Syringe selectors use six-character code patterns `5_1___` and `70____` without an Item Group restriction. Server-side engineering compatibility validation still applies.

The three affected DocType schemas were reloaded on `site1.local` with the targeted `sync_item_creation_schema()` helper. No broad migration or unrelated pending patches ran. Historical manufacturing data and pending 4D BOMs were not repaired or activated.

Deploy the Python/form code together and reload the installation's web/worker processes. Refresh the browser/form cache. The targeted schema command for another deployment is:

```sh
bench --site <site> execute amf.amf.utils.item_creation_workflow.sync_item_creation_schema
```

Existing draft requests need explicit raw-stock quantities, supported variant selections and recorded engineering review before submission. Historical submitted requests retain their existing records.

Broader permission roles, formal versioned engineering-template maintenance, dedicated structured geometry fields, company-wide costing/settings policy, historical catalogue repair and a platform upgrade remain on the separate backlog. A full browser session and the entire repository test suite are outside the recorded verification above.
