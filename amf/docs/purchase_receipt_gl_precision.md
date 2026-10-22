# Purchase Receipt GL precision guard

The AMF Purchase Receipt override filters GL entries that round to zero at the
same configured precision used by ERPNext's GL posting and validation. This
applies to ordinary receipts and returns. It fixes the failure reproduced on
PREC-03061, where a CHF 0.0033 project-specific adjustment became a zero-value
entry on account 2210 during posting.

The original receipt controller merges entries first, so sub-cent amounts on the
same account and dimensions can accumulate into a postable total. The guard
preserves meaningful entries, account-currency amounts, accounting dimensions,
normal validation errors, and the existing AMF return-accounting rules for
receipts with or without landed costs and valuation taxes.

Installation runs on Purchase Receipt `before_submit` and Stock Ledger Entry
`before_validate`. The latter covers future receipt GL reposts triggered by
other stock transactions, cancellations and landed-cost updates in a fresh
process. Installation is protected by a lock and is idempotent: concurrent
requests cannot replace the saved original controller with the wrapper itself.
Calls without a warehouse-account map resolve it from the receipt's company.
Manual scripts that call receipt GL calculation without posting stock must
explicitly call `install_purchase_receipt_gl_override()` first.

Run the regression suite from the bench directory:

```sh
env/bin/python -m unittest amf.amf.utils.test_purchase_receipt_gl_override -v
```

The tests cover the original amount/project pattern, merged sub-cent components,
rounding boundaries and methods, configured precisions of zero/two/three,
foreign account currencies, negative entries, dimension preservation, landed
costs, valuation taxes, omitted/empty warehouse maps, validation errors and
concurrent/idempotent installation.

Validation on 2026-10-22: all 23 focused tests and all 12 adjacent item-batch
tests pass (35 total). A wider run including `test_stock_entry_repair` has 42
passes and two existing failures: the manufacture wrapper test expects a
2024 start date where the implementation uses 2026, and the serialized wrapper
test expects dry-run mode where the implementation defaults to apply. Both
failures reproduce with the pre-change hooks; those repair functions and their
tests are unchanged by this patch. The fixture-based Stock Entry submission
suite requires an isolated Frappe test site and was not run against business data.

A rollback-only integration check on PREC-03061 reproduced the exact failure
before the fix and passed core stock/GL posting afterward. It exercises six
stock ledger entries and balanced GL debits/credits of CHF 2,167.25. Commit,
email, background job, barcode and notification side effects were suppressed;
the quality/assignment workflow after core posting was excluded. The hardened
check also verifies installation through Frappe's real Stock Ledger Entry hook
in a fresh process. The receipt remains Draft with no persisted ledger entries.

On deployment, clear the site's hooks cache and reload Python web/worker
processes using the bench's normal service-management procedure. No schema
migration or accounting-setting change is required.

## Independent historical valuation finding

The integration check also identified inconsistent MAT.1011 valuation history in
STE-18224. Its source and target transfer rates and FIFO queue are zero, but
the target SLE reports CHF 40.50 at CHF 90/m. Consuming 0.30 m then produces a
CHF 40.50 stock movement against the receipt's CHF 27.00 material cost, a
CHF 13.50 difference. This is independent of the zero-entry error and needs a
historical source-valuation correction; the precision guard does not rewrite
stock history. Review that discrepancy before submitting PREC-03061.
