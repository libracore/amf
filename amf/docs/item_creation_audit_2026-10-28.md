# Item Creation audit and requested changes — 28 October 2026

The current Item Creation workflow has server-owned execution, protected engineering review, exact recipe previews and searchable results. Its main remaining operational limitation is legacy-head reuse: 99 of 100 enabled Valve Head Items fail the existing-head preflight under the current component-family and BOM checks. A separate authenticated read-permission gap remains in older lookup helpers. These findings are distinct from the two requested changes implemented below.

This audit supersedes the current-state conclusions of the [27 October audit](item_creation_audit_2026-10-27.md). That document preserves evidence about an earlier implementation; its original controller, browser orchestration and numbering findings must not be applied wholesale to the current code.

**Environment and evidence**

The inspected installation is `site1.local`, with AMF baseline commit `2abf264`, Frappe `2023.6.2` and ERPNext `2023.8.3` on the local v12 codebases. AMF was `0.7.6` before this work and is now `0.7.7`. The AMF working tree was clean at the start. No unrelated application changes were included.

The [verification record](item_creation_verification_2026-10-28.json) contains the baseline metadata and counts, all 100 head-preflight outcomes, authorization evidence, schema-installation checks and rollback verification. Catalogue inspection used MariaDB-enforced read-only transactions. The later creation test prohibited nested commits and rolled back all test business records and generated files.

| Site measure | Observed value |
| --- | --- |
| Items | 3,372 |
| Product Items | 2,144 |
| Valve Head Items | 109 total; 100 enabled |
| BOM headers / BOM Item rows | 8,185 / 39,816 |
| Item Creation requests | Five: four submitted, one draft |
| Recorded engineering reviews / execution-result rows | Zero before and after testing |
| Latest existing submitted request | `Item Creation-00003`, submitted 26 October 2026, head `300085` |
| Existing draft | `Item Creation-00002`, selecting head `300126` |
| Family reservations at baseline | Zero; current next suggestion `117` |
| Item Creation customizations | No Custom Fields, Custom Scripts, Server Scripts or Workflow; one naming-series Property Setter |
| Request permissions | Standard and custom DocPerm both grant the lifecycle to System Manager |

The four Item Creation patches, including the new patch from this work, are installed after the targeted schema update. The parent and three child schemas matched their source definitions at baseline; the two added fields were verified after installation.

**Current architecture and lifecycle**

| Responsibility | Source |
| --- | --- |
| Document lifecycle, head/component validation, name suggestions and legacy adapters | [item_creation.py](../amf/doctype/item_creation/item_creation.py) |
| Form events, configuration chooser, plan rendering and review/cancellation dialogs | [item_creation.js](../amf/doctype/item_creation/item_creation.js) |
| Read-only dependency catalogue, normalized recipe comparison and approval fingerprints | [item_creation_plan.py](../amf/utils/item_creation_plan.py) |
| Component and Product recipes | [item_creation_recipes.py](../amf/utils/item_creation_recipes.py) |
| Body/syringe/head compatibility matrix | [item_creation_compatibility.py](../amf/utils/item_creation_compatibility.py) |
| Review authorization, locked submission and Item/BOM creation | [item_creation_workflow.py](../amf/utils/item_creation_workflow.py) |
| Suffix/member reservations and Item/BOM insertion guards | [item_code_family.py](../amf/utils/item_code_family.py) |
| Immutable result links, history search, cancellation and amendments | [item_creation_traceability.py](../amf/utils/item_creation_traceability.py) |

The parent is submittable and tracks changes. Its child tables hold selected configurations, engineering-review snapshots and execution results. It is an application-managed review process; no separate Frappe Workflow is installed.

1. The user defines a new head or selects an existing enabled head. Selecting an existing head reads its actual default BOM and components without creating a replacement.
2. Newly defined plug/seat components require names, R&D references, material tags, exact raw-stock Items, positive consumption and the stock Item's current UOM. The editable consumption defaults remain plug `0.02` and seat `0.03`.
3. The user selects individual supported Product configurations. Family checkboxes alone do not create every combination.
4. Preview builds a read-only plan showing create/reuse/replace actions, component quantities, UOMs, scraps, child BOM revisions, operation differences and parent impact.
5. A System Manager with request write/submit permission records notes and approves the exact plan/dependency fingerprint. A saved input edit clears the active approval; changed dependencies are rejected at submission.
6. Submission rebuilds the plan under row locks, creates missing Items, submits required BOMs in dependency order and records every result in the owning transaction. Existing Item identity conflicts are rejected. Different BOM recipes require explicit replacement mode and approval.
7. Cancellation requires a reason and retains generated masters, BOM revisions and reservations. An amendment reuses the original head family and requires fresh review. Requests with review/result history cannot be deleted through ordinary document operations.

A complete new head creates five Items and five BOMs: plug component, plug sub-assembly, seat component, seat sub-assembly and head. Standard heads support two RVM and 28 LV selections, for at most 35 planned Items/BOMs including the head chain. HV heads support eight Product selections, for at most 13. Standard and HV head requirements remain mutually exclusive.

The versioned matrix supports RVM bodies `511000`/`521000`; LV bodies `551000`, `571000`, `591000`, `5B1000` with seven syringe choices; and HV bodies `561000`, `581000`, `5A1000`, `5C1000` with `70E000`/`70F000`. Exact enabled Item groups and configured references are checked. LV laboratory recipes retain `T100` and adapter scrap treatment; HV recipes consume the adapter. Screw quantity is included in the reviewed recipe.

**Requested change 1 — Product suffix independence: implemented**

The user specified that Product suffixes may differ from head suffixes, while retaining existing suggestions. The existing default remains the configuration prefix plus the last three characters of the selected head. Each selected configuration now has an optional editable **Product Code** override. Blank means use the existing suggestion; no new automatic numbering sequence was introduced.

For example, head `300ABC` still suggests `420ABC` for body `521000`. Entering `420XYZ` creates or verifies that Product against the same selected head `300ABC`. Its reference and BOM continue to identify `300ABC`; its own last three characters do not determine the head.

The restriction was removed from both the trusted creation context and normal Item/BOM insertion guards. Standalone Products reserve their referenced head family and their own exact Item code. Product BOMs still require exactly one head. Quotation matching now checks the actual body/head/syringe BOM configuration without requiring Product/head suffix equality.

Overrides retain the selected configuration's three-character prefix, the existing six-character alphanumeric format and the nonzero suffix requirement. Existing identity collisions, disabled Items, retired exact-code reservations and incompatible configurations remain errors. Overrides survive reopening the configuration chooser and participate in preview and approval hashes. Head/plug/seat family rules and existing head-code suggestions remain unchanged.

**Requested change 2 — selectable seat pins: implemented**

A new **Pins** Link field selects an enabled Item and defaults to the previously fixed `SPL.3039`. **No. of Pins** remains the quantity field. The seat sub-assembly BOM consumes the selected Item and reviewed quantity. A positive quantity requires an enabled pin Item; zero permits a design without pins. Pin selection is part of the approved inputs and dependency snapshot.

The additive migration reloads only the parent and variant metadata, preserves the old pin choice in applicable saved drafts, and marks any active draft approvals stale while retaining review history. It does not rewrite submitted request snapshots or historical Item/BOM recipes. No applicable draft backfill or approval reset was needed on this site.

**Remaining finding — High: legacy heads largely cannot pass existing-head reuse**

The audit ran the current read-only planner against all 100 enabled Valve Head Items with an enabled warehouse in the configured company, no replacement mode and no Product selections. Only `300134` passed. The remaining 99 include deliberate templates and missing BOMs as well as incompatible legacy structures; this is not a claim that 99 engineered designs are physically wrong.

| Blocking category | Distinct heads affected |
| --- | --- |
| A managed component in the recursively inspected chain has another suffix | 56 |
| A component BOM has invalid quantities or stale stock-UOM metadata | 49 |
| Missing/invalid submitted active production BOM | 6 |
| Template/nonconforming head code | 1 |

Categories overlap. The direct-head-only check found 55 heads with cross-suffix components; recursion adds one more. Examples:

- `300126` uses `110026` and `200057`; both fail the component suffix policy. This is the head selected in the saved draft.
- `300135` uses `110060`, which fails that policy.
- `300055` uses `110040` and `200040`, which fail that policy.
- `300040` reaches `BOM-100040-008` and `BOM-200040-010`. Their raw-stock rows use `uom=Meter` and `conversion_factor=1`, but retain `stock_uom=Nos` while the raw Items now have `stock_uom=Meter`.

The Product/head restriction removed in this work is separate from these component-family checks. Before expanding existing-head creation, decide whether reviewed legacy component reuse should be supported or new component-family revisions are required. Correct stale UOM metadata through reviewed manufacturing revisions. No automatic repair was made.

**Remaining finding — High: older lookup helpers bypass Item read authorization**

`get_reusable_bom_managed_components()` at `item_creation.py:260` and the related suggestion/detail helpers use direct SQL or `frappe.db.get_value()` without an Item read-permission check. An existing enabled authenticated account with Employee/Projects/HR roles had `frappe.has_permission('Item', 'read') == False`, passed Frappe's whitelist check for the helper, and received two component records including R&D references and material tags.

This was a direct dispatcher-whitelist/helper probe in a database-enforced read-only transaction; no login session or HTTP request was created. Anonymous HTTP access is separately blocked by the installed v12 dispatcher, so the finding concerns authenticated business authorization. The newer preview API correctly denies a principal without Item/BOM read permission.

Add explicit read authorization and permission-filtered queries to the exposed legacy helpers. If request access is shared more widely later, audit the planner's bulk SQL and result report against Item/BOM user permissions as well; their principal document filter is the request. This permission work was outside the two requested behavior changes.

**Remaining finding — High: transaction and revision containment depends on the workflow context**

Item Creation correctly enters `atomic_family_creation()` during execution. Its scoped hooks skip implicit parent propagation, preserve reviewed child links and use commit-free Item synchronization. The real integration test prohibited nested commits and passed.

Outside that context, `bom_updating.py:174` still calls parent propagation when a default BOM is saved; `:265` updates parent BOM Item links directly and `:291` commits per parent. `bom_child_bom_resolver.py:4` can replace selected child revisions with current defaults. `bom_mgt.py:699` still contains a save/commit helper that catches exceptions and rolls back. Future creation/import paths must not call these legacy paths without defining transaction and revision ownership. These source paths were inspected; no live parent updates were executed for the audit.

The separate pump updater also starts by inferring a head from Product suffix (`bom_updating_for_pump.py:66`) and then falls back to a head-reference lookup. That helper should be revised to use the actual selected BOM configuration before its next bulk use now that independent Product codes are supported. It was not invoked or changed here.

**Remaining findings — Medium: engineering policy and historical presentation**

The compatibility matrix and head parser encode engineering meaning in names and code constants. Geometry, custom designs, stock dimensions, screw/pin suitability and physical compatibility still require engineering judgment. Head references and Item descriptions are not a structured engineering specification. Product weights also remain fixed recipe constants (`0.53`/`2.18` Kg), rather than configuration-specific approved data.

Review, submission and delegated Item/BOM creation currently rely on System Manager. The workflow intentionally inserts generated masters with `ignore_permissions=True` after request approval; separate preparer/reviewer roles and company-aware creation policy need an explicit broader design if access is expanded.

The four historical submitted requests have no recorded plan/results and show `review_status=Draft`. The plan API correctly identifies them as historical, but the general form introduction still says execution completed for every submitted document (`item_creation.js:282`). The presentation should distinguish historical submissions from requests verified by the new execution workflow. Existing record metadata does not demonstrate that those historical submissions ran the present controller.

**Validation and deployment result**

- 142 focused/regression Python tests passed with initialized site settings. Two adjacent Work Order numeric tests initially failed without initialization because v12 rounding reads System Settings; both pass in the initialized run.
- Actual form-script Node checks passed, including plan invalidation on pin/Product-code edits and preservation of overrides when reopening the chooser.
- A real rollback-only request created six Items/six submitted BOMs, with Product `420Z7B` using head `300Z7A` and three of pin Item `700015` (`Pin ISO 2338 - D1x8`). It recorded six result links and rejected a changed pin choice as stale review.
- Quotation resolution returned the independent Product code. Normal standalone insertion also accepted Product `410Z7B` referencing head `300Z7A`.
- The integration took approximately 17.7 seconds, including focused tests, and prohibited nested commits. Full-table hashes confirmed rollback of Items, BOMs, BOM rows, requests, reviews, result rows, Series and File records. Public/private file inventories confirmed QR cleanup.
- The targeted migration is installed and recorded in Patch Log on `site1.local`. Business signatures for all existing Items, BOM headers, material rows and request states were unchanged by installation.
- `git diff --check` passed. No full browser session, HTTP authorization test, multi-process concurrency exercise or complete repository test suite was run.

Refresh the open form to load the new metadata/scripts. Other deployments need the new registered patch and the Python/form code together, with their normal application-process reload. Local Supervisor reported no managed programs to reload. No service restart or remote deployment was performed in this session.
