# Item Creation: RVM body and interface variants — 29 October 2026

AMF `0.7.11` implements the user's extension to RVM Mini RS485/CAN and all `511___`/`521___` Body variants. AMF `0.7.12` applies the user's subsequent numbering correction: new NM/TH Products use `421xxx` and new P201-O RS485 Products use `422xxx`. Enable **Rotary Valves (including RVM mini)** and open **Choose Product Configurations**. All these configurations have no syringe.

## Current catalogue and reference mapping

| Body | Configuration | Product prefix | Generated reference for head `300ABC` |
| --- | --- | --- | --- |
| `511000` | P200-O | `410` | `P200O300ABC` |
| `521000` | P201-O | `420` | `P201O300ABC` |
| `521001` | P201-O RSB | `420` | `P201O300ABCRSB` |
| `521002` | P201-O RS485 | `422` | `P201O300ABCRS485` |
| `521003` | P201-O LPH | `420` | `P201O300ABCLPH`; enter the exact address/customer reference where applicable |
| `521004` | P201-O AIR | `420` | `P201O300ABCAIR` |
| `521005` | P201-O ELV | `420` | `P201O300ABCELV` |
| `521006` | P201-O SYS | `420` | `P201O300ABCSYS` |
| `521101` | P211-O NM/TH | `421` | `P211O300ABC` |
| `5D1000` | RVM Mini base | `4D0` | `P202O300ABC` |
| `5D1001` | RVM Mini RS485 | `4D1` | `P202O300ABC/RS485` |
| `5D1002` | RVM Mini CAN | `4D2` | `P202O300ABC/CAN` |

The inspected catalogue has twelve enabled supported Body Items. `511000` is currently its only `511___` Body; no missing hardware master is invented. Additional enabled `511___`/`521___` Body records are discovered at request time. Supported RVM reference roots P200-O/P201-O/P211-O/P221-O determine the namespace; dot variants determine the trailing reference suffix. Unknown/missing definitions appear as requirements and cannot be approved until the Item master is reviewed. Fixed known bodies retain their exact reference checks. Disabled/non-Body records are not selectable for creation.

The two explicit numbering exceptions above override reference-root numbering. `430xxx` remains the P211-O namespace for body `531000`; the historical `430081` using `521101` is a preserved exception, not the rule for new NM/TH Products. New codes for head `300ABC` prefer `421ABC` for NM/TH and `422ABC` for RS485. The inspected catalogue and member reservations contained no `421xxx` or `422xxx` allocations before this change. Existing Product Reference formats are retained; the existing reviewed override resolves reference conflicts when required.

The separate prototype `5D100A` is outside this requested base/RS485/CAN Mini extension. The historical six pending interface BOMs are not activated or backfilled. A request can explicitly select/review a new Product using an enabled interface Body that has no default BOM; existing interface Products already use such stock-body dependencies.

LPH records demonstrate why address settings cannot be guessed: `420082` and `420083` share body `521003`/head `300041` but identify I2C addresses 2 and 3. Use the existing editable **Product Reference** override for the intended address/customer identity. Reuse preserves the matching existing Item name/reference; disagreements with its actual BOM still require reviewed replacements.

## Code allocation, recipes and review

- All selected variants sharing a prefix receive distinct six-character codes. The base prefers prefix + head suffix; occupied, retired and other planned codes are skipped using numeric then alphanumeric serials. This applies to new heads as well as reused heads.
- Existing-head suggestions also search explicitly declared historical prefixes for the same enabled Product reference: `430` for NM/TH and `420` for RS485. Exact existing recipes are reused without renaming Items or changing submitted BOMs. Recipe differences still require reviewed replacements; disabled/retired reference owners still block duplicates. These historical prefixes are reuse-only; new code overrides must use the current `421`/`422` prefix.
- Entered code overrides are reserved for their selected rows before automatic allocation. Canonical ordering makes code suggestions and approval fingerprints independent of grid row order.
- Head and newly created components retain their matching family suffix. Product references/BOMs identify that head explicitly even when Product serials differ.
- Each RVM Product consumes one selected body, one head, the entered screw quantity and one selected cap. Accessories remain shared explicit request inputs; separate requests can express different requirements. No quantity is inferred from a different historical Product.
- New Mini interface Products use `0.10 Kg`, NM/TH `521101` uses its observed `0.70 Kg`, and existing ordinary RVM recipe defaults remain. Reused Item master weights are preserved. Broader configuration-specific weight/engineering-template policy remains proposed.
- Runtime discovery, occupied Product inventory and reservations are read once per plan. Suggested Product BOM dependencies are loaded together, avoiding per-variant lookup loops. The current largest standard plan has 40 Products plus five head-chain Items/BOMs (45 total); requests are bounded to 256 configurations.
- Compatibility version `2026-10-29.3` requires refreshing/reviewing previous draft approvals. Review, automatic BOM submission, immutable history and transaction-owned rollback remain in force.

Canonical Quotation reference resolution, fallback namespaces and head suggestions now use the same RVM variant rules. They still verify actual body/head/syringe composition. Discovery of arbitrary custom/address-specific reference overrides remains proposed; such Products remain directly selectable by Item Code.

## Numbering correction in AMF 0.7.12

The new prefixes are shared by Item Creation choices, manual code validation, automatic suggestions, legacy RVM previews and Quotation fallbacks. Existing reference lookup still finds historical RS485/NMTH Products under their original codes. The registered `update_item_creation_rvm_numbering` patch reloads only parent-form guidance and clears its metadata cache. It performs no business-record migration, renaming, historical BOM creation or repair. Deploy with the normal application-process reload and browser refresh; earlier draft engineering approvals require a new preview and review.

Verification for `0.7.12`: **194 focused/regression Python tests** and actual form-script Node checks passed. Coverage includes dedicated prefixes, manual overrides, exact legacy reuse, disabled/retired reference-owner rejection, BOM mismatch protection and Quotation's preserved `430` fallback for body `531000`. Version, JSON field order, shared preview prefixes and unique next-patch registration passed static checks. A real rollback-only integration reused `420099`, `430081`, Mini interfaces and an address-specific LPH Product without renumbering; it then created a new head family and all twelve RVM variants, including NM/TH `421122` and RS485 `422122`: **17 Items and 17 automatically submitted BOMs** in about 25 seconds. Quotation resolved the new variants. Existing head/body/component records and pending interface records stayed unchanged. All test records, reservations and QR files were rolled back, with nested commits forbidden. No production migration was executed for this numbering correction; its guidance patch is registered for the next upgrade.

## Verification and deployment

Original `0.7.11` verification: read-only inspection confirmed each body/reference and representative submitted recipes, including RSB/RS485/AIR/ELV/SYS trailing suffixes, LPH address variants and the `430081` NM/TH exception. No historical reference or recipe was repaired.

**189 focused/regression Python tests** and actual form-script Node tests passed. They cover all current mappings, additional discovered `511001`/`52100A` fixtures, disabled/incomplete definitions, distinct shared-prefix allocation, preserved overrides, row-order stability, reuse, reference dependency changes, Mini interfaces, canonical Quotation lookup and the 45-action bulk-read case.

A real rollback-only integration reused existing `420099`, `4D1080`, `4D2080`, address-specific `420082` and NM/TH `430081`. It then created a matching head/component family and all twelve RVM variants: **17 Items and 17 automatically submitted BOMs**. Every Product retained the correct body, head revision, reference and distinct code. RS485/CAN/NMTH Products resolved through Quotation; the interface head selector found the new head. The complete case took about **23.6 seconds**. Snapshots of existing Body/head/component Items/BOMs and the six pending interface records stayed identical. All temporary Items/BOMs, requests, reviews/results, reservations and QR files were rolled back; nested commits were prohibited.

The first integration attempt exposed existing `BOM-210122-001`, whose current `BOM.item` is `210120`, even though Item code `210122` was available. ERPNext v12's autoname searches by `BOM.item`, so it reused that occupied name. Execution now checks occupied names under locks and advances to an available revision without modifying the historical BOM. Resolved child links use the actual new revision. The failed first test rolled back completely; the subsequent full submission passed. A separate injected result-write failure also propagated and rolled back all Items/BOMs, requests, links, reservations and QR files.

The registered patch `amf.patches.v12_0.update_item_creation_rvm_variants` reloads only parent guidance metadata and clears its cache. Two targeted passes preserved Item/BOM/request counts and existing fields/defaults. No broad migration, interface backfill or paused cost writer ran. Deploy Python/form code together with the normal application-process reload and browser refresh. Full browser and multi-process concurrency tests are outside this verification.

The maintained proposals are in [item_creation_improvements.md](item_creation_improvements.md).
