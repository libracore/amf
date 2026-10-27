# Item Creation audit — 27 October 2026

The main risks are unauthorized creation, partially committed creation, and unintended changes to existing BOMs. These need to be resolved before expanding the creation features. Several independently reproduced defects also affect HV pump recipes, product descriptions, code assignment, and previews.

This records the original audit findings. The subsequent shared-suffix numbering update is described in the [implementation record](item_creation_algorithm_implementation_2026-10-27.md); findings below describe the code before that update. Initial database inspection used a MariaDB-enforced read-only transaction on `site1.local`, followed by rollback. Later lifecycle tests also rolled back all test business records.

The follow-up [catalogue-derived specification](item_creation_catalogue_specification_2026-10-27.md) records the user's confirmed requirements and expands the evidence to 2,649 Items and 582 enabled Products with selected active submitted default BOMs. The final three alphanumeric characters must identify the same head throughout six-character codes. New-family allocation must verify that suffix globally from Products down to `10_ABC`/`20_ABC` components. The corrected snapshot-wide check rejects `085` and finds `117` next.

The subsequent [engineering workflow](item_creation_engineering_workflow_2026-10-27.md) implements the selected preview/review, compatibility, raw-material BOM, guided-form and execution improvements. The [maintained tracker](item_creation_improvements.md) distinguishes completed work from the remaining recommendations; findings below preserve the original audit evidence.

## Inspected environment and scope

| Area | Evidence |
| --- | --- |
| AMF baseline | Git HEAD `6b7a95e`; Item Creation files had no pre-existing working-tree changes. Unrelated working-tree changes were retained. |
| Frappe | Local `v12` branch; `frappe.__version__ = 2023.6.2`. |
| ERPNext | Local `v12` branch; `erpnext.__version__ = 2023.8.3`. These are patched local v12 builds. |
| Primary files | [Controller](../amf/doctype/item_creation/item_creation.py), [form script](../amf/doctype/item_creation/item_creation.js), [DocType schema](../amf/doctype/item_creation/item_creation.json), [numbering tests](../amf/doctype/item_creation/test_item_creation.py). |
| Dependencies | `bom_creation.py`, Item and BOM hooks, `bom_updating.py`, `bom_mgt.py`, `bom_child_bom_resolver.py`, batch rules, reporting/custom-item hooks, QR generation, Item form creation and BOM helpers, learned descriptions, legacy numbering callers, and recent 4D migrations. |
| Site configuration | Standard/custom DocPerm, Custom Scripts, Server Scripts, Custom Fields, Property Setters, workflows, relevant Item groups, Items, and selected current default BOM rows. |
| Existing documentation | October costing containment and rollback records. These are historical context; current rules and state must be distinguished from those records. |
| Scope limits | No real browser session, HTTP authorization exercise, complete dependency graph audit, or write-based integration run. The local database inspection does not establish the state of another deployment. |

The inspected site contains **three submitted Item Creation records and one draft**. The latest submitted record dates to **7 January 2026**; the draft dates to **12 February 2026**. They predate the July 2026 Item Creation changes and therefore cannot establish that the current implementation works.

There are no Item Creation Custom Fields, Property Setters, Custom Scripts, Server Scripts, or workflows on this site. There are separate `Item-Client` and `BOM-Client` Custom Scripts, which were inspected. The older numbering dialog in `Item-Client` is commented out; it is not an active additional numbering path.

## Existing execution flow

1. Form events derive names and request a proposed head code. Plug and seat codes are filled by separate checkbox events.
2. Selecting an existing head calls `populate_fields_from_existing_item()`. That method may create and submit a replacement default BOM immediately.
3. The browser's `before_submit` handler calls up to six creation endpoints in sequence: plug, seat, head, RVM, pump, HV pump.
4. Item helpers, BOM helpers, and downstream hooks commit independently. Only after the creation calls does the browser submit the Item Creation document.
5. `ItemCreation` itself is an empty server controller. Standard server/API submission has no corresponding creation orchestration.

All current selections request up to **43 Items and 41 BOMs**: two plug Items, two seat Items, one head, two RVM products, 28 pump products, and eight HV pump products. The DocType does not retain a structured list of all created/reused Items and BOMs.

## Findings

Severity reflects potential consequences and reproducibility, rather than an assertion that a particular historical record was created by the current code. **Critical** findings affect authorization or existing manufacturing recipes. **High** findings affect transactional correctness, identity, or generated recipes.

### 1. Critical — creation endpoints lack business authorization

**Sources:** `item_creation.py:659`, `:1211`; `bom_creation.py:622`; Frappe `handler.py:35` and `frappe/__init__.py:479`.

`create_item_from_doc()` accepts arbitrary client JSON and a group. It does not load a saved Item Creation, check its permissions/status, or verify Item/BOM create/submit rights. `_create_item_if_not_exists()` inserts with `ignore_permissions=True`; the BOM helper does likewise. In v12, that flag persists on the document for later saves/submission. Whitelisting checks authentication and method exposure; it supplies no Item Creation role check.

Read/suggestion endpoints also use SQL, `get_all()`, and `get_doc()` without explicit read checks. These mechanisms do not enforce document read permissions automatically.

**Reproduced:** the Item helper called `insert(ignore_permissions=True)` and committed with no permission check in the helper. The creation router is allowed over GET, POST, PUT, and DELETE by the installed whitelist defaults.

**Change needed:** explicitly authorize each exposed operation; restrict mutations to POST; load and validate the saved source document; protect all downstream writes. Any deliberate delegated creation capability must be role checked and documented. Verify this with a limited user in staging.

### 2. Critical — selecting an existing head can replace its manufacturing recipe

**Sources:** `item_creation.js:125`; `item_creation.py:461`, `:556`; `bom_creation.py:544`.

A field-population request derives expected component names, judges the current BOM, and calls `create_bom_for_assembly()` when they differ. That helper submits a new active default BOM and commits. This can occur before saving or submitting Item Creation.

The lookup assumes one named plug sub-assembly and one named seat sub-assembly constitute every correct head recipe. Current data contradicts that assumption:

- Head `300126`, used in the existing draft, currently has default `BOM-300126-007`, containing plug sub-assembly `110026` and seat component `200057` directly. The lookup treats the `20` seat as incorrect and attempts to find a replacement by name.
- Head `300135` currently uses plug `110060` named `PLUG-V-2-2-160-P`, which differs from the component name implied by its `SPE` head name. Its actual reference is `DBM.1032`, which also fails the lookup's assumed reference grammar. The audit does not determine whether that engineering choice is correct.

**Reproduced:** the lookup invoked the BOM creation helper for a mocked existing head with a direct seat component.

**Change needed:** field population must be read-only. Return the actual selected BOM/components and discrepancies. Handle reviewed recipe changes through an explicit operation with a separate policy and authorization.

### 3. Critical — a default BOM save can rewrite and commit existing parent BOMs

**Sources:** `hooks.py:91`; `bom_updating.py:174`, `:207`, `:263`.

The `before_save` hook calls `update_depending_boms()` whenever a BOM has `is_default` set. It updates matching component rows in every non-canceled parent BOM and commits per parent. It does not require the new child BOM to be submitted or active. The updates bypass the parent document's validation and revision workflow and do not recalculate its explosion/cost fields.

Item Creation always constructs default BOMs, so retries or an existing-head lookup can affect already existing parents. Changing the new BOM policy to draft-only would not make this hook safe by itself.

**Reproduced:** saving a mocked default draft BOM issued a parent-row UPDATE and a commit.

**Change needed:** remove implicit parent mutation from this creation path; preserve existing parent revision links. Any parent propagation needs an explicit, validated, separately reviewed plan. This dependency must be addressed alongside the Item Creation controller.

### 4. High — the operation cannot roll back as a unit

**Sources:** `item_creation.js:14`; `item_creation.py:715`, `:744`, `:771`, `:796`, `:817`, `:1228`; `bom_creation.py:628`; `bom_mgt.py:691`; the parent hook above.

Each successful browser call is a separate transaction. Helpers also commit within each call. A later missing material, permission failure, network interruption, or failed Item Creation submission can leave Items and submitted BOMs behind while the source request remains a draft.

The BOM submission hook calls `_safe_save()`, which also commits; on error it rolls back and suppresses the exception. That makes rollback ownership and the reported outcome unreliable. Removing commits only from `item_creation.py` would leave these problems in place.

**Reproduced:** the Item helper committed independently. An injected `_safe_save()` failure rolled back and returned without raising.

**Change needed:** one server-owned transaction for the validated creation plan, including the source document and every required dependency hook. Failures must propagate. Any background-job alternative needs an explicit durable job state and recovery design.

### 5. High — browser submission and server submission have different outcomes

**Source:** `item_creation.py:13`; `item_creation.js:14`.

Creation exists entirely in a browser event; the server controller is `pass`. A standard server/API submission can submit the request without executing its creation workflows. Cancellation and amendment have no domain behavior, and generated records lack durable request links.

**Change needed:** move validation and orchestration into the server document lifecycle. The browser should show previews and results. Define cancellation/amendment semantics and retain created/reused Item/BOM links. Cancellation must not be assumed to authorize deleting manufacturing masters.

### 6. High — reuse and retries are not safe

**Sources:** `item_creation.py:1211`; `bom_creation.py:569`.

An existing Item code is accepted without comparing its group, name, reference, material, disabled state, or intended identity. The next step can create a new default BOM for that existing Item. The BOM helper's existence check defaults to false, and the Item Creation callers do not enable it.

Simply enabling that check is insufficient: it accepts any BOM for the Item, without proving its status or recipe matches the plan.

**Reproduced:** a request for a different product with an existing code was accepted without loading the existing Item.

**Change needed:** distinguish a compatible reusable Item/BOM from a collision. Compare canonical identity and normalized recipe, return explicit reuse results, and reject conflicts before writing. Repeating the same submitted request should return the same recorded outcome without new BOM revisions.

### 7. High — product numbering collides with existing configurations and truncates head identity

**Sources:** `item_creation.py:988`, `:1054`, `:1144`; `quotation_product_definition.py:329`; catalogue-derived specification and collision CSV.

The broader follow-up establishes an immediate failure: the next free family suffix is `0085`, proposing head `300085`, while generated product `420085` already belongs to an AIR configuration with body `521004` and head `300033`. Fourteen other current enabled-head cases conflict with the actual body/head in an existing generated-code candidate. Product suffixes already distinguish configurations and cannot be treated as unique head identifiers.

The family allocator supports four-digit head suffixes through `9999`, but all finished-product builders use only `head_code[-3:]`. Heads `300040` and `301040` both generate RVM code `410040`, with equivalent collisions across matching pump variants. Silent existing-Item reuse makes this more serious.

**Reproduced:** both heads generated `410040`. No such enabled-head suffix collisions were found in the inspected database; the highest managed suffix currently present is `0138`.

**Change needed:** allocate one globally free three-character suffix for the complete new head family and use it consistently in every Product, head, sub-assembly and component code. Product family/configuration differences must use the preceding characters, preserving that head suffix. Check all relevant variants, including disabled/retired identifiers, and reserve the suffix transactionally. Existing mismatches require reviewed correction. The Quotation resolver and pump BOM updater belong in this scope and must validate the actual selected configuration. Catalogue-backed isolated executions confirmed that selecting body `521000` and head `300049` currently resolves to `420049`, whose reference instead identifies head `300033` and RS485.

### 8. High — suggestions are not reservations, and form codes become inconsistent

**Sources:** `item_creation.py:130`, `:185`; `item_creation.js:88`, `:200`, `:213`.

Two users can receive the same suffix. There is no reservation or lock around final family allocation, and the factories do not recheck family ownership. The primary-key constraint alone cannot prevent partial creation or an incorrect reuse decision.

Plug/seat codes are generated only when their checkboxes change. A later head-code suggestion does not update them. Callbacks also apply after the user changes the head name because they have no request sequence or input comparison.

**Reproduced:** head `300041` was displayed with seat `200040` and plug `100040`; an older response replaced the seat name after the user changed the head input.

**Change needed:** keep previews advisory, allocate/reserve the common final three characters globally under transaction-level locking and revalidation, and derive new family codes together on the server. Check every relevant Product and component variant before accepting a suffix. Reject stale browser responses and invalidate dependent previews on input changes. Existing-family continuation/reuse must verify head/family ownership and recipe identity separately from fresh allocation.

### 9. High — HV pump screws and the required adapter are omitted

**Sources:** `item_creation.json` field `screw_quantity`; `item_creation.py:1125`; `bom_creation.py:595`.

The form uses `screw_quantity`; `_prepare_pump_hv_data()` reads `screw_qty`. Its screw row therefore gets `None`, which the BOM helper omits because it is falsey.

**Reproduced:** input `screw_quantity=2` produced a screw row with `qty=None`.

The subsequent catalogue evaluation also found that all 101 enabled HV product recipes with selected active submitted defaults consume `RVM.1204` positively as a material. `_prepare_pump_hv_data()` does not include that adapter. Correcting the screw field alone leaves an incomplete HV recipe.

**Change needed:** use a shared validated recipe input and verify screw quantities and adapter consumption for every applicable variant. Required materials must not disappear through a generic falsey-quantity check.

### 10. High — the workflow omits machined-component raw-material BOMs

**Sources:** `item_creation.py:692`, `:827`; `item_bom_creation.py:14`, `:113`.

Item Creation creates the `10`/`20` component and `11`/`21` assembly Items, then only the assembly BOM. It sets components to Manufacture and seeds fixed valuation rates of `0.20` and `30`, without selecting a raw-material Item or creating its production recipe.

The separate Item form helper supports the missing lower layer: a raw-material BOM, then the component-plus-accessory BOM. It uses provisional quantities `0.02` for plugs and `0.03` for seats and can require selection among multiple raw materials with the same tag. Those quantities are existing code, not an independently verified engineering specification.

Current enabled six-digit components have submitted active BOMs for **65 of 66 plugs and 65 of 65 seats**. The lower layer matters to the current catalogue.

**Change needed:** agree whether Item Creation must create that layer and obtain the correct material, quantity, and UOM rules. Share the validated planning logic with the Item form. Its current helpers still require a downstream transaction audit before reuse.

### 11. High — recipe validation relies on fragile string and BOM assumptions

**Sources:** `item_creation.py:360`, `:494`, `:524`, `:581`, `:827`, `:934`, `:1051`.

- `populate_fields('VALVE HEAD')` raises `UnboundLocalError`; short hyphenated inputs index missing parts before checking their length. The empty-input return also lacks the material keys returned on success.
- Existing-head lookup fails on missing or short `reference_code`. Enabled head `300084` has no reference code in the inspected catalogue.
- Prefix checks `110`/`210` and SQL pattern `_10%` fail for valid `11`/`21` suffixes above `0999`. Name lookup does not constrain Item group or resolve multiple matches explicitly.
- Exactly two BOM rows does not prove there is one plug and one seat, with the correct quantities. A mocked BOM with two plugs was accepted and returned an empty seat code.
- The creation factories splice code characters without validating group/prefix/length; generated names and material tags are trusted from the client.
- Syringe reference parsing assumes an existing Item and a valid hyphenated reference. Compatibility, required screws/cap, material quantities, and UOMs are not preflighted across the entire selected plan.
- The helper uses a truthiness check for material quantities. It forwards negative quantities, which ERPNext subsequently rejects during BOM validation; by that time earlier helper commits may already exist. Zero/None materials are omitted, and even optional zero-quantity materials are checked for existence before omission.

**Change needed:** parse a documented grammar once into typed data, allow explicitly supported custom designs, and validate the complete creation plan before the first write. Validate actual Item identity and selected submitted BOMs rather than reconstructing all engineering choices from names.

### 12. High — existing valuation fields are overwritten without a creation-specific policy

**Sources:** `item_creation.py:709`, `:738`, `:765`, `:790`, `:811`, `:833`, `:842`.

The workflows write `BOM.total_cost` into `Item.valuation_rate`, including on Items silently reused by code. They also seed new component rates with arbitrary constants. A stored BOM estimate and stock valuation are different sources; this behavior needs an explicit policy for creation and reuse.

The site configuration currently has `pause_amf_cost_writers=1`. The existing [containment record](bom_cost_containment_2026-10-09.md) documents purchased/made material source rules and warns that manual writers outside the guarded jobs are not blocked. The [rollback record](bom_valve_head_rollback_applied_2026-10-12.md) documents a later restoration of selected BOM amounts and child links. Item Creation's direct valuation assignments do not consult the pause flag.

**Change needed:** preserve existing valuation and BOM financial fields by default; define the policy for new records separately. Reuse the established costing sources only where applicable and verified. Recipe creation must not silently initiate historical repricing or undo preserved BOM links.

### 13. Medium — generated descriptions and previews contain confirmed defects

**Sources:** `item_creation.py:1006`, `:1086`, `:1155`, `:1178`; `item_creation.js:226`, `:280`, `:334`.

- HV descriptions display `S-2500-P` as **2500 ml**, while the Item catalogue identifies **2500 µL**. Correct mL formatting would be **2.5 mL**; the same issue applies to the 5000 µL syringe.
- The P200-O RVM branch always describes the body as P201-O and the version as Fast.
- A laboratory pump body label uses `P1{M}O-L`, with letter O where the family uses digit 0. The HV laboratory syringe label has a stray leading `S`.
- HV preview checks `pump_check`, rather than `pump_hv_check`. Selecting HV alone performs no preview request.
- Preview HTML is assembled without escaping returned strings; saved-document sanitization does not protect a preview generated from unsaved client JSON. This is an HTML-injection concern, not a demonstrated browser exploit in this audit.
- Previews refresh on checkbox events, but not all input changes, and errors do not clear HTML options consistently.
- `createPlug()` calls the browser global `print()`, potentially opening the print dialog during submission.
- Client callbacks consider the response object itself a success, without validating `message`. RVM's server success message leaves `{0}` uninterpolated.

**Reproduced:** wrong HV units, wrong P200 description, no HV-only preview request, a call to the mocked browser print function, and a success notice for an empty response object.

**Change needed:** a single server-side variant plan should generate both preview and execution data. Use structured volume values/units, shared descriptions, escaped HTML/text rendering, and an explicit result schema.

### 14. Medium — permissions and company defaults depend on site state

**Sources:** `item_creation.json:392`; `item_creation.py:876` and other `item_defaults` factories; `bom_creation.py:582`.

The checked-in DocType grants System Manager create/write/read but omits submit, cancel, and amend. The inspected site's Custom DocPerm grants all three, so submission is enabled there. A fresh installation may behave differently.

Factories hard-code `Main Stock - AMF21` and omit company in Item Default rows. The BOM helper reads `User.company`; that field is absent from both the site's User schema and physical table. In this v12 implementation, `get_cached_value()` reads the document and returns no value for that missing field. Frappe may subsequently fill missing company values from user/global defaults, so this audit does **not** claim a guaranteed SQL error or universal creation failure. It is an implicit default dependency and possible company/warehouse mismatch.

**Change needed:** define the authorized roles and ship their permissions intentionally. Resolve and validate company/warehouse explicitly and consistently, preserving existing valid defaults for reused Items.

### 15. Medium — family variants, raw-material tags, and selection filters have drifted

**Sources:** `item_creation.js:53`, `:60`, `:67`; `item_creation.py:616`, `:750`, `:777`, `:800`; `item_bom_creation.py`; recent 4D patches.

The wizard generates only RVM 41/42, seven syringe variants across four low-volume pump bodies, and two syringe variants across four HV bodies. The wider codebase also supports other RVM families and 4D RS485/CAN variants. Their presence does not establish that every family should be included in this wizard; a compatibility matrix is needed.

The screw filter uses exact Item group `Part`, excluding screws in child group `Fasteners`. Current examples include `700009`, `700025`, `700030`, `RVM.3002`, and `RVM.3003`. The existing filter still returns five enabled screws, so it is restrictive rather than entirely empty.

The parser maps material E to `EPDM`, whereas the Item raw-material selector contains `EPDM-E`. It has no mapping for some catalogue tags such as PEI. The wizard's `plug_mat` Select has no options. These inconsistencies need a shared material vocabulary with a defined custom-code path.

The broader follow-up resolves the repeated adapter pattern: all 226 observed enabled low-volume pump defaults list `RVM.1204` as scrap; all 101 HV defaults consume it positively as a material. The limited first-pass example `46E040` is disabled and carries a historical negative conversion, so it is unsuitable as a new-recipe template. All 40 laboratory low-volume defaults also include `T100`, which the wizard omits. The detailed specification retains design-specific exceptions and review requirements.

### 16. Medium — tests do not cover the main creation lifecycle

Eight existing Item Creation tests cover family numbering/reuse suggestions. Fourteen tests cover the separate Item form BOM helper. There are no corresponding tests for Item Creation's six creation workflows, request permissions, rollback, retries, actual v12 document submission, or browser dependencies.

**Change needed:** add behavior tests around the confirmed defects and meaningful integration tests on a disposable v12 site, including the actual Item/BOM hooks. Passing the present unit tests is insufficient evidence that creation is safe.

## Algorithm assessment

| Algorithm | Assessment | Direction |
| --- | --- | --- |
| First free family suffix | Scans only the five managed component/head prefixes using four-digit suffixes; it misses occupied Product suffixes and shared final-three-character collisions. Its bounded search handles holes/exhaustion for that narrower set, but does not satisfy the confirmed business rule. The earlier 20–32 ms probes measured this narrower pure search, excluding SQL. | Build a global set of occupied final-three-character suffixes across every relevant Product and component variant, including disabled/retired aliases. Search a deterministic numeric-then-alphanumeric sequence and persist reservation/ownership under concurrency control. |
| Code construction | Straightforward mapping, but accepts arbitrary suffix strings and silently defaults unknown variants to Component. Several consumers require numeric-only component codes. | Validate exactly three shared ASCII alphanumeric characters and construct six-character codes at all layers. Update component BOM, batch, machining, drawing, reporting and form consumers. Handle the legacy `get_last_item_code()` compatibility contract explicitly. |
| Product identity | Does not ensure that the final three characters identify the actual head; legacy configurations already violate that invariant. | Preserve the common suffix in all newly generated layers and distinguish configurations in their prefixes. Validate actual recipes and review existing mismatches. Test blocked suffix `085`, currently free `117`, and alphanumeric/concurrency cases. |
| Cartesian product of bodies and syringes | 2 + 28 + 8 variants are computationally small. The weakness is missing compatibility rules and repeated database/transaction work. Pump previews repeat seven syringe lookups across four bodies; HV repeats two across four. | Load required catalogue data once, create a deterministic plan, and validate supported combinations. A worker is optional and should follow measured request time and recovery requirements. |
| Name parsing | Repeated splitting/indexing with partial validation; naming logic duplicated in population, factories, and learned descriptions. | One parser/formatter returning structured values and explicit validation errors; preserve reviewed custom designs. |
| Existing-BOM detection | Heuristic name/prefix matching cannot establish recipe correctness; name lookup can be ambiguous. | Resolve the current Item default pointer, validate matching Item/status/company, and compare a normalized, policy-aware recipe. |
| Component reuse suggestions | Useful tag/group/disabled checks, but no authorization/reservation or proof of common head-family ownership. | Separate existing-family continuation from fresh allocation, validate ownership and recipe, share the policy across creation interfaces and repeat validation under the final transaction. |

The existing `bom_child_bom_resolver` already validates that Item default BOM pointers match the child Item and are active/submitted. It also overrides supplied links on save, and its non-strict mode clears invalid pointers instead of rejecting the plan. The new planner must reconcile that behavior with strict validation for required manufactured components and with revision preservation. The generic creation helper still independently queries BOMs without a submitted-status filter; that logic should be unified.

## Recommended implementation sequence

1. **Settle the workflow contract:** intended families, recipe/naming authority, existing-BOM preservation, new-BOM submission policy, roles, cancellation, and costing behavior.
2. **Build a read-only planner:** normalize inputs; validate identities, permissions, quantities, materials, UOMs, company, compatibility, and reusable records; return every Item/BOM action and discrepancy. Share plan data with the UI preview.
3. **Repair transaction ownership and hooks:** eliminate incidental commits/rollback suppression for this path; prevent draft/default creation from updating existing parents; add locked allocation and retry protection. Address dependencies explicitly before moving execution into the server document lifecycle.
4. **Execute the validated plan:** create required lower layers in dependency order, record created/reused Item/BOM links, apply the chosen submission policy, and propagate failures.
5. **Repair the form:** derive related codes together, discard stale responses, fix HV recipes/units/previews and print calls, expose useful validation errors, and render the actual plan/result.
6. **Validate on a disposable v12 site:** restricted-role API tests; failure injection at each layer; repeated submission; concurrent allocation; existing/custom/disabled Items; missing material/default BOM; component reuse; every supported product variant; permission migration; company defaults; QR/File cleanup; and existing-parent/financial-field preservation.

Production data repair, retrospective BOM replacement, renumbering, valuation changes, and expanding the product catalogue require their own concrete plans after the audit decisions. The presence of historical inconsistent data does not authorize automatic correction.

## Information needed before application updates

| Decision | Evidence already available | Still needed |
| --- | --- | --- |
| Intended deployment and examples | Repository and `site1.local` inspected; numbering is the user's stated priority. | Validate implementation on a disposable site before deployment. |
| Catalogue scope and compatibility | The user instructed us to learn from existing Items. The follow-up derives 44 observed combinations and documents the ordinary/custom design boundaries. | Use the evidence for suggestions; require reviewed definitions for ambiguous or unobserved new configurations. |
| Naming and numbering | The user requires six-character alphanumeric codes whose final three characters identify the same head. Suffix availability must be checked across the entire chain. Historical Product/head suffix mismatches are review cases. | Implement global shared-suffix allocation/reservation, complete family-code generation and consumer validation. The snapshot's first valid numeric suffix is `117`; `085` is blocked by a Product. |
| Recipe and reuse authority | The user requires a reviewed replacement for disagreements. Repeated raw-material, accessory, and adapter patterns plus their exceptions are documented in the follow-up. | Show the exact proposed replacement and record its review; obtain explicit component/recipe selections for genuine custom-design ambiguities within that workflow. |
| Submission and lifecycle | The user confirmed automatic submission of new BOMs. Current System Manager access is known. | Tie automatic submission to the reviewed, revalidated plan and define cancellation/amendment behavior without automatic master-data deletion. |
| Defaults and costing | AMF company/warehouse conventions, raw-material lower layers, historical costing policy, and active pause flag are known. | Preserve financial fields and validate new-record defaults. Do not copy UOM inconsistencies or historical rates into a universal rule. |

The user's follow-up identified numbering as the priority, instructed us to derive specifications from Items, confirmed automatic new-BOM submission, required reviewed replacements for BOM disagreements, and specified six-character alphanumeric codes with a globally available common three-character suffix across the whole head family. These decisions and the additional catalogue evaluation are incorporated above. The [shared-suffix implementation](item_creation_algorithm_implementation_2026-10-27.md) is now complete in the local checkout, with automated and rollback-only lifecycle verification. Broader audit recommendations remain explicitly scoped in that record.

## Verification performed

- `env/bin/python -m unittest amf.amf.doctype.item_creation.test_item_creation amf.amf.utils.test_item_bom_creation`: **22 tests passed**.
- `node --check apps/amf/amf/amf/doctype/item_creation/item_creation.js`: passed.
- Additional Python probes reproduced parser failures, missing HV screw quantity, wrong HV units, product collisions, blind Item reuse, existing-head lookup writes, incomplete component validation, unchecked inserts, individual commits, draft-parent propagation, and swallowed rollback errors. All writes were mocked.
- Additional Node VM probes reproduced the HV-only preview condition, inconsistent family codes after a new suggestion, stale response application, browser print invocation, and success reporting for an empty response. This was script-level execution, not a full browser test.
- Pure numbering probes covered suffix `9999`, exhaustion, and partial family occupancy.
- Read-only SQL checked the deployed metadata, permissions, customizations, historical usage, material tags, dependencies, and selected actual recipes. No data repair was run.

Temporary inspection/probe files are `/tmp/item_creation_audit_readonly.py`, `/tmp/item_creation_audit_db.json`, `/tmp/item_creation_audit_probes.py`, and `/tmp/item_creation_audit_browser_probes.js`. The database output contains internal catalogue/script information and is not a public export. No credentials were included in the report or probe output.
