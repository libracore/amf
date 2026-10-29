# Item Creation: Product Reference overrides — 29 October 2026

AMF `0.7.9` implements the user's request to modify a planned Product Reference directly when preview reports an existing owner. This extends the [existing-head/Product-only release](item_creation_audit_2026-10-29.md). Existing Item masters and head/component recipes remain preserved.

## Using the option

1. Refresh the complete plan. Beside a reference-conflict error, click **Change Product Reference**.
2. The dialog shows the generated reference and links to its existing owner. Enter the desired unique reference and click **Apply Reference**. For example, `P200O300080-R1` can distinguish a planned P200-O Product from the disabled `/410080` that owns `P200O300080`, subject to availability.
3. Save the request, refresh the plan and record fresh engineering review before submission. The plan shows the actual Product Reference and notes its generated counterpart. Only submission creates the Item/BOM.

The optional **Product Reference** field can also be edited in the expanded configuration row. Empty means the normal generated body/head/syringe reference. Clearing an override restores that behavior; it may restore the original conflict. The configuration chooser retains entered code/reference overrides.

References must be one line of at most 140 characters and retain the selected head code exactly once, with no other head code. This preserves the existing managed-Product head-reference convention. Uniqueness checks include disabled Items, other Item Groups, case differences and other Products in the same plan. An already-owned override is rejected again with the editor available.

Changing the reference does not rename or reactivate the historical owner. If an explicit Product Code points at an existing Item with a different reference, that Item's identity remains protected. Leave the code override blank to suggest an appropriate available Product code, or review the existing master separately. A matching enabled Product with the entered reference can be reused on subsequent requests. Body/head/syringe BOM selections remain explicit and unchanged by reference editing.

Missing assembly screws, screw quantity or head cap must still be supplied according to the selected Product recipe; a reference override does not fill accessory fields.

## Implementation and validation

- The new field belongs to `Item Creation Variant`. The conflict's structured configuration key targets the correct row. Preview renders escaped text/links and binds a delegated click handler; it uses no inline executable HTML.
- Dialog application changes the draft row and invalidates the cached plan. A changed definition rejects an old dialog response. Reference editing is disabled for submitted/cancelled requests.
- The shared recipe uses the entered reference; code suggestions match against it, and the catalogue includes its global owners. Reference uniqueness is also checked across selected configurations before approval.
- Both the override and final reference participate in input/plan hashes and immutable review snapshots. Saved reference changes clear active approval while retaining review history. Submission rebuilds the plan under locks and uses the normal exact Item/BOM guards and transaction.
- Plan version is `5`. Earlier draft approvals require refresh/review; historical submitted snapshots are retained.
- The registered additive patch `amf.patches.v12_0.update_item_creation_product_references` reloads only variant metadata and clears child/parent caches. It performs no business backfill, reference repair or automatic reactivation. Deploy code and metadata together with normal application-process reload/browser refresh.

**Verification:** 171 focused/regression Python tests and actual form-script Node tests passed. Tests cover resolving retired references, restoring defaults, reuse, global/planned duplicates, field/head validation, identity protection, escaped browser/server errors, stale approval/dialog behavior and chooser preservation. Two targeted metadata passes confirmed the editable field and unchanged Item/BOM/request counts.

A real rollback-only submission reproduced the user's `300080`/P200-O conflict, applied a unique test reference, reviewed it and created Product `410001` with an automatically submitted BOM pinned to `BOM-300080-001`. Changing its reference invalidated approval and required another review. A repeat plan reused the custom-reference Item/BOM. SQL snapshots confirmed the retired owner and all original head/component Items/BOMs/material rows were unchanged. The case took about 7.1 seconds; nested commits were prohibited, and all temporary records/reservations/QR files were rolled back. No live Product or historical reference edit was retained.

Full browser and multi-process concurrency tests were not performed. The Quotation composition selector still searches its generated reference/code fallback; broader discovery of independently numbered custom-reference Products remains [proposed](item_creation_improvements.md). Such Products remain directly selectable by Item Code.
