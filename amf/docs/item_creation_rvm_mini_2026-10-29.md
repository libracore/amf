# Item Creation: RVM mini configuration — 29 October 2026

AMF `0.7.10` adds the requested base RVM mini body `5D1000` to RVM Product Configurations. Enable **Rotary Valves (including RVM mini)**, open **Choose Product Configurations** and select **P202-O (RVM mini)**. No syringe is selected.

| Setting | Value |
| --- | --- |
| Body | `5D1000`, enabled Body Item, R&D reference `P202-O` |
| Product code prefix | `4D0`; head `300ABC` suggests `4D0ABC` when available |
| Generated Product reference | `P202O` + full head code, e.g. `P202O300ABC` |
| BOM | One body, one head, entered assembly-screw quantity, one selected head cap |
| New Product weight | `0.10 Kg`, matching all 37 inspected base Mini Products |
| Head requirements | Existing standard RVM head rules; HV heads remain excluded |

Existing-Product matching, independent Product code suggestions, code/reference overrides, Product-only mode and exact engineering review apply normally. New BOMs submit automatically with the reviewed request. Existing Item identities and BOM revisions remain protected. Reused Item master values are not overwritten.

Read-only catalogue inspection confirmed 37 enabled `4D0xxx` Products, all with `0.10 Kg` weight and non-batched/non-serialized Product flags. All 37 selected default BOMs were inspected by material count: 36 have the standard four material rows; `4D0040` additionally includes shipping foam `73A100`. That exception remains a recipe difference requiring **Propose Replacement BOMs** and fresh review. It is not silently removed. The exact `4D0080` recipe already matches the base Mini definition when its existing screws/cap are selected.

The extension adds only `5D1000`, not the separate RS485/CAN bodies `5D1001`/`5D1002`. No existing 4D interface migration or pending BOM is executed. Existing catalogue records are not backfilled or repaired.

Compatibility version is now `2026-10-29.1`; earlier draft approvals require refresh/review before submission. Historical submitted/cancelled snapshots remain intact. The standard RVM/LV maximum increases to 31 Products plus five new head-chain Items/BOMs, or 36 total. Bulk dependency reads remain unchanged.

The registered `amf.patches.v12_0.update_item_creation_rvm_mini` patch reloads only parent guidance metadata and clears its cache. It was executed twice on `site1.local`, verifying the Mini label, retained Product-only/reference fields, unchanged seat/plug quantity defaults and unchanged Item/BOM/request counts. Deploy Python/form code together with normal application-process reload and browser refresh.

**Verification:** 177 focused/regression Python tests and actual form-script Node tests passed. Coverage includes Mini selection, code/reference/weight/materials, enabled Body identity, compatible heads, reuse, overrides, unrequested interfaces/syringes, legacy RVM preview and the 36-action bulk-read plan.

A real rollback-only review/submission first reused Item `4D0080` and `BOM-4D0080-001`, then created custom-reference Product `4D0001` and one automatically submitted BOM. Its four reviewed materials, `0.10 Kg` weight, stock flags, and pinned `BOM-5D1000-001`/`BOM-300080-001` were verified. A read-only plan for `4D0040` retained its shipping-foam difference as a replacement-review requirement. Existing head/body/component and pending interface snapshots stayed unchanged. The case took about 3.2 seconds; nested commits were prohibited and all temporary Items/BOMs, requests, review/results, reservations and QR files were rolled back. No live Product/BOM was retained.

Full browser and multi-process concurrency tests were not performed. The maintained proposal list is [item_creation_improvements.md](item_creation_improvements.md).
