# Item Creation numbering implementation — 27 October 2026

This records the first numbering phase. The subsequent [engineering workflow implementation](item_creation_engineering_workflow_2026-10-27.md) supersedes the execution, form and compatibility details below: complete raw-material BOMs, recorded engineering review, explicit variant selections and commit-free execution are now implemented. Current status is maintained in the [improvement tracker](item_creation_improvements.md).

The shared three-character head-family allocator is implemented in [item_code_family.py](../amf/utils/item_code_family.py). [Item Creation](../amf/doctype/item_creation/item_creation.py) now creates its complete family on the server when submitted. This implements the numbering work identified by the [catalogue specification](item_creation_catalogue_specification_2026-10-27.md); it does not implement every improvement in the initial audit.

## Allocation algorithm

1. Read the complete relevant Item catalogue, without filtering disabled Items. Include `10`, `11`, `20`, `21`, `30`, every `4` prefix, and other six-character identifiers in the Product/Products groups.
2. Canonicalize known retired/variant identifiers. `/48E113` occupies `113`; `4D0006-P` occupies `006`. Leading slashes and known alias separators do not make an old identifier available again. Bodies, syringes, raw materials and accessories use separate namespaces.
3. Extract the final three characters into a set. Thus `101ABC`, `20CABC`, `301ABC`, `420ABC`, and `4D2ABC` all occupy the same token `ABC`, regardless of which groups the user selects for creation.
4. Combine that set with persistent reservations. Search `001` through `999`, then the remaining uppercase base-36 tokens in lexical order (`00A`, `00B`, …). Keep `000` unavailable. There are 46,655 possible tokens.
5. Return a read-only suggestion. A suggestion has no ownership and may become unavailable before saving.
6. When the source is saved, lock allocation and reserve its entire suffix in that transaction. Use a locking read of the reservation keys, so a competing transaction's committed claim is visible even after an earlier repeatable-read snapshot. Reject a conflict; the client must refresh its suggestion.
7. Derive all new member codes from the reserved suffix. Recheck ownership during Item insertion. Exact member identifiers also receive permanent reservations, preventing their reuse after deletion or retirement.

At the inspected catalogue snapshot, `085` is rejected because `420085` already exists. The next free token is `117`: `100117`, `110117`, `200117`, `210117`, `300117`, `410117`, `420117`, and the corresponding pump variants. Availability is checked again against the live catalogue and reservations on save.

For a later alphanumeric token `ABC`, the same algorithm gives `100ABC`, `110ABC`, `200ABC`, `210ABC`, `300ABC`, `420ABC`, `452ABC`, and `46EABC`. Codes remain six characters. The third character is a component/product variant character, rather than another head serial digit.

## Reservation storage and concurrency

The implementation uses the existing InnoDB `tabSeries` table; no new DocType, column, index or schema migration is needed.

| Series key | Purpose |
| --- | --- |
| `AMF-IC-FAMILY-LOCK` | Transactional allocation mutex. |
| `AMF-IC-FAMILY:ABC` | Permanent reservation of the complete family suffix. |
| `AMF-IC-FAMILY:ABC:<64-character hash>` | Ownership by the source DocType/name; long document names fit within the v12 column limit. |
| `AMF-IC-MEMBER:100ABC` | Permanent exact-code allocation history. |

These rows use `current = 0` and are distinct from ordinary naming series. Helpers never commit. Successful request transactions retain reservations; failed transactions roll them back. Saving the same source again is idempotent. Deleting a saved draft, changing its suffix, or cancelling a source does not release its earlier reservation. Reclaiming reservations requires a separate reviewed administrative decision.

The mutex remains held until the transaction ends. Concurrent requests for the same suggestion cannot both succeed. A long family submission also holds this mutex; this implementation prioritizes correctness and does not introduce background execution or a new job-status workflow.

## Submission and existing-family rules

Submission performs these steps inside the Frappe request transaction:

1. Validate the head and source ownership on the server. Derive checked plug/seat codes from the head rather than trusting browser fields.
2. Build a dependency-ordered plan for every selected component, subassembly, head and finished product.
3. Before inserting any Item, check every code, required enabled material, positive quantity, existing Item identity and existing default BOM. A matching existing BOM must be active, submitted, for the correct Item, and have the same per-unit material/scrap quantities.
4. Insert missing Items and create/submit their BOMs in dependency order. Reuse only the verified existing definitions.
5. Add a source comment listing the created/verified Item codes.

Legacy helpers and hooks contain internal commits and broad exception handlers. A context limited to family submission defers those commits and converts a swallowed hook rollback into a submission failure. The normal Frappe request handler then rolls back a failed request. The parent-BOM propagation hook is bypassed inside this context, preventing incidental replacement of pre-existing parent BOMs.

The old browser sequence of independent group-creation calls is removed. Its legacy HTTP endpoint now rejects creation and directs callers to submit the saved source. API submission follows the same controller path as the form.

Continuing an existing family is an explicit, separate path:

- An existing head must be enabled and have a valid submitted active default BOM. Validation follows linked/default BOMs through its managed subassemblies and components, rejecting a different suffix or disabled component at any managed layer.
- A standalone subassembly must match the corresponding existing component's name, reference and material context.
- A standalone Product must explicitly reference an enabled existing head with the same suffix and a validated component chain.
- Component, subassembly and head BOM definitions reject managed material rows from another suffix. Product BOMs require exactly one matching head, including custom Product-group identifiers. Draft saves and submission both recheck this rule; existing submitted revisions are not rewritten.
- A historical disagreement blocks generation with a reviewed-replacement error. Merely selecting an existing head performs no BOM repair. Review and replacement remain an engineering action; this change does not add an approval screen or automatically replace submitted historical BOMs.

## Related consumers

- Quotation reference and fallback matches now require a valid active submitted selected BOM and an exact match of the requested head/body/syringe tuple. Wrong catalogue matches return `configuration_mismatch`, with a reviewed-replacement message. Mini RVM interface fallbacks retain their distinct `4D1`/`4D2` prefixes.
- Batch rules, Work Order calculations and field visibility, drawing lists, machining/yield reports, relevant manufacturing charts and Product costing filters accept uppercase alphanumeric codes.
- The Item form's BOM-creation helper accepts alphanumeric identifiers and joins the verified existing component family. The legacy Item-number suggestion uses the shared allocator.
- The old Item-master renumbering utility recognizes six-character alphanumeric codes, preventing it from treating new identifiers as unnumbered legacy Items.
- Form component codes refresh when the head changes; delayed new-head suggestion responses cannot overwrite newer input. HV preview uses its own selection checkbox.
- New HV recipes use the selected screw quantity and consume `RVM.1204`, as observed across all 101 active HV recipes. Laboratory LV recipes include `T100`; LV adapter scrap treatment is retained. HV description volumes use µL.

## Verification

- All 75 focused Python tests passed, covering full-chain occupancy, old four-character ranges, disabled/retired identifiers, custom Products, decimal/alphanumeric ordering, exhaustion, source ownership, exact-code retention, recursive continuation, server submission, BOM mismatches, preflight failure, recipe corrections and Quotation configuration checks.
- Node tests execute the actual Item Creation form script, covering alphanumeric synchronization, changed heads, stale suggestions, HV preview and removal of browser-driven creation.
- Fifteen existing Work Order and operations-report tests passed with initialized site settings in a MariaDB-enforced read-only transaction.
- A real two-connection MariaDB test established an older repeatable-read snapshot in the competing connection. It waited for the first claim, rejected the suffix after commit, and acquired it after rollback. Isolated test registry rows were removed.
- A real Frappe lifecycle test created 43 Items and 41 submitted BOMs with all 38 original finished-product variants selected. All database writes and generated QR files were rolled back. This verifies execution and rollback, not engineering approval of every product combination.
- A second lifecycle test injected failure on the second BOM; no source, Item, family/member reservation or generated QR file remained after rollback.
- After the final member and BOM guards were added, a further lifecycle check created a five-Item head family, then added a standalone Product through the ordinary Item-insertion guard and submitted its BOM. All six Items and four BOMs passed; rollback and the injected-failure case passed again.

## Activation and remaining audit scope

The changes are in the local checkout. No service restart, asset deployment, broad migration, historical Item renaming or historical BOM repair was performed.

Use the normal deployment process to build AMF assets, reload Python web/worker processes and clear site caches. The existing `sync_work_order_estimated_time_custom_fields` helper also needs to run to update the stored Work Order visibility expressions; it is already registered in `after_migrate`. It can be invoked directly during deployment without running unrelated pending patches:

```sh
bench --site site1.local execute amf.amf.utils.work_order_estimated_time.sync_work_order_estimated_time_custom_fields
bench build --app amf
bench --site site1.local clear-cache
```

Restart services through the installation's existing process manager. No family reservation backfill is necessary: the allocator reads existing identifiers before every fresh claim.

Broader engineering work remains as described in the audit: reviewed recipe/template selection, a recorded replacement-approval interface, custom name/material grammar, raw-material stock selection, and full physical compatibility rules. The original product selection matrix is retained, including the two LV syringe variants found only in disabled product recipes; enabling those combinations still needs engineering review. No paused cost writers or six pending 4D interface BOMs were activated.
