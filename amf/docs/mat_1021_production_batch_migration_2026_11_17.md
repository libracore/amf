# MAT.1021 production batch migration

Production URL: https://amf.libracore.ch/

The next normal production merge and site migration must run:

`amf.patches.v12_0.apply_mat_1021_production_batch_setup_2026_11_17`

The patch is registered in `amf/patches.txt`. It has a new Patch Log identity so
earlier migrations recorded as complete do not suppress this correction. It
selects the target data using MAT.1021 on PREC-02877, independently of the site's
filesystem name. The source-document, quantity, warehouse, and ledger checks in
the existing helpers remain in force.

The migration enables `Item.has_batch_no` and creates or reuses these batches:

| Source | Batch | Later usage |
| --- | --- | --- |
| PREC-02877, 6 m | `8UREHM DAL` | Purchase Receipt item and its stock ledger entry |
| STE-14142, 1 m | `KRDLAT AMF` | STE-18224 transfer, then PREC-03061-1 supplied material consumption |

The original 1 m stays on its own batch, as requested. Both Stock Entry item
rows, both sides of the transfer ledger, and the subcontract consumption item
and ledger use that same original-stock batch. Existing conflicting batches
raise an error instead of being overwritten. Every active MAT.1021 stock
movement must be batched, and warehouse batch totals must agree with stock.
The migration does not post quantity, valuation, or GL adjustments.

Deployment uses the actual configured production site name with the normal
`bench --site <production-site> migrate` workflow. For a targeted application
after the code is deployed, the equivalent command is:

```sh
bench --site <production-site> execute amf.patches.v12_0.apply_mat_1021_production_batch_setup_2026_11_17.execute
```

Verification on 17 November 2026 used the development database with a simulated
production site name and blocked internal commits. Rollback checks covered
disabled batch tracking, missing batch masters, blank source/transfer/consumption
links, repeated execution, conflicting existing batches, unrelated-site scope,
and unchanged stock quantities, values, and GL. All database changes were rolled
back. No authenticated production connection is configured in this workspace;
production application and verification remain part of deployment.
