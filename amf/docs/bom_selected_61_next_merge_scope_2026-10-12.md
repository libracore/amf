# Next merge: selected 61 Item material-cost scope

Source list: `bom_cost_old_vs_new_2026-10-12_updated.csv` (61 literal Item codes,
including the corrected `46E...` and `48E...` codes). This preview was made on
`site1.local` on 2026-10-12. It did **not** apply BOM changes.

## Exact scope

The scoped runner starts at each selected Item's active submitted
`Item.default_bom` and follows only recursively made child BOMs. When the
approved latest qualifying Purchase Receipt prices a component, that component
is a purchased leaf and its linked child BOM is not traversed. The runner uses
the existing material-only pricing rules, including the current stock valuation
fallback and stored scrap credit. It leaves operating costs alone.

| Scope or result | BOMs |
| --- | ---: |
| Selected finished Item defaults | 61 |
| Additional reachable made-child defaults | 55 |
| Total reachable defaults | 116 |
| Ready to change: selected roots | 61 |
| Ready to change: child BOMs | 43 |
| Already at calculated amounts | 12 |
| Blocked branches | 0 |

The BOM-by-BOM old/new values are in
`bom_selected_61_recursive_reprice_proposal_2026-10-12.csv`. The JSON proposal
contains every material row, its source and method, and the exact reviewed
scope. For `458040`, the current total is CHF 413.021300 and the proposal total
is CHF 374.565279 (CHF 375.565279 raw material less CHF 1 stored scrap credit).
The new total matches the 2026-10-09 proposal; all 61 selected root proposed
totals match that proposal.

## Shared child impact

There are 125 **other current default BOMs** with a direct production link to a
child BOM that this scoped run would change. The affected parent rows are in
`bom_selected_61_recursive_reprice_proposal_2026-10-12_outside_parents.csv`.
The scoped runner does not update those parent BOM headers, material rows, or
exploded rows. Their stored parent costs may therefore disagree with the newly
stored child costs until a separate parent review. Non-default BOMs are not
included in this dependency count.

## Controlled next-merge run

The implementation is
`../amf/report/bom_cost_breakdown/selected_bom_reprice.py`. The automatic
`site1.local` migration entry is
`../patches/v12_0/reprice_selected_61_boms_2026_10_12.py` in `../patches.txt`.
The preceding `migrate_private_data_artifacts_2026_10_26` patch imports the
reviewed JSON proposal, the literal 61-Item CSV, and the original material
snapshot into private **AMF Data Artifact** database records. Its checksum
manifest and seed resources in `amf/patches/data/private_bom_inputs/` must be
included in the merge. No runtime tool reads the `docs` directory. The proposal is bound to current BOM rows, qualifying
receipts, and the outside-parent dependency list. If any of these change before
migration, the patch raises an error before writing costs. Regenerate and review
a new database proposal, then explicitly update the reviewed seed and manifest
before retrying the repricing migration. Existing named artifacts cannot be
overwritten; updating the reviewed version also requires changing the artifact
name used by the repricing patch. It also requires both automatic cost writers
to remain paused.

The patch writes only fully calculable changed BOMs in the scoped route, in
child-before-parent order, rebuilds their ERPNext exploded rows, and verifies
stored amounts and exploded quantities. Frappe commits those changes together
with the Patch Log entry. A failure rolls the transaction back.

The 2026-10-12 transactional preflight exercised all 104 proposed writes and
all 104 explosion read-backs, then rolled back. Its representative calculated
`458040` total was CHF 374.565279. The preview JSON SHA-256 is
`eacfc6fe2caaec05ef28988ea1ca0c902fa05ae7af90461d0983598093e54b26`.
