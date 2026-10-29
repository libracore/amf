# FFTest serialized 4D production flow

Implementation: `amf/www/fftest_master_debug_4d.py`, copied from the working
`fftest_master_debug.py`. The original file and existing Web Page configuration
are unchanged. The copy keeps the original method names and argument names.

## Calling the copy

Read-only preview:

```python
amf.www.fftest_master_debug_4d.debug_stock_entry_flow(
    source_work_order_id="OF-...",
    serial_no_id="HAND-0070",
    batch_no_id='[{"batch_no": "MATERIAL-BATCH"}]',
)
```

Execution:

```python
amf.www.fftest_master_debug_4d.make_stock_entry(
    source_work_order_id="OF-...",
    serial_no_id="HAND-0070",
    batch_no_id='[{"batch_no": "MATERIAL-BATCH"}]',
)
```

`batch_no_id` is optional and accepts a JSON array or a decoded list. Explicit
batches are routed to the stages that consume their items. Omitted source batches
are selected by ERPNext's normal save-time selection. Component quantities come
from ERPNext; a quantity supplied inside a batch-selection object does not override
the BOM.

The production page/FFTest caller must use the new module path to activate this
copy. No production call was made while implementing or testing it.

## Production sequence

Only Work Orders whose production item starts with `4D` use the new sequence.
The actual component codes and linked BOMs are read from the selected product's
BOM; the implementation is not limited to `5D0000`/`5D1000`.

For a previously unused operator-entered serial:

1. Manufacture one `5D0___` from its manufacturing BOM, assigning that serial.
2. Manufacture one `5D1___`, consuming the `5D0___` and assigning the same serial
   to the output within the same Manufacture entry.
3. Manufacture one `4D____`, consuming the `5D1___`.

ERPNext V12 explicitly permits carrying a serial between a consumed item and an
output item in a Manufacture entry. Its native
`allow_serial_nos_with_different_item()` validates this case. One Serial No record
changes its current item from `5D0___` to `5D1___`; stock ledger rows retain each
stage's item, batch, and serial. The implementation does not create duplicate
Serial No records or rename serials.

The entered value is normalized using V12's standard parser (trimmed and
uppercased, with leading zeroes preserved). The 4D branch adds no P202 prefix.
The final Stock Entry output records the value in `product_serial_no` when that
custom field exists. If the 4D item itself is serialized, its output also carries
the same Serial No using the native mechanism.

An available existing serial for the exact `5D0___` component resumes at step 2.
An available existing serial for the exact `5D1___` component resumes at step 3.
Consumed serials and serials for other items/companies are rejected. A serial in
WIP must belong to the correct submitted manufacturing transfer and configured
Work Order warehouse; the final Work Order must match the requested one.

The 4D branch returns the submitted **final-product** Stock Entry. Failures return
`{"error": "...", "log_id": "..."}`.

## Required manufacturing data

- The supplied 4D Work Order must be submitted, active, have capacity for another
  unit, and directly require its `5D1___` component. An exploded Work Order that
  requires only deeper raw materials is rejected with an explanatory error.
- Its BOM must contain exactly one `5D1___` row, consuming one stock unit per
  product. That component's BOM must similarly consume one serialized `5D0___`.
- Both components must be enabled, serialized stock items. Additional serialized
  input components require a separate serial and are rejected by this one-serial
  API.
- To manufacture a new `5D0___`, it needs a submitted, active manufacturing BOM
  and available component stock. The code does not manufacture stock through an
  unsupported Material Receipt when a BOM is missing. An already manufactured
  available `5D0___` can be consumed without a raw-layer BOM.
- Existing component Work Orders must match the item, selected BOM, company,
  Sales Order scope and parent scope. Suitable orders are reused; otherwise new
  component Work Orders are submitted with single-level BOMs and parent links.
  Native operation/Job Card completion requirements still apply.

## Corrections included in the copy

- Batch stock queries use V12's string cancellation state:
  `IFNULL(is_cancelled, 'No') = 'No'`.
- The source/final Work Order and serial are locked before reuse or manufacture.
  Current locking reads refresh serial state and Work Order capacity after waits.
- Each stage respects its configured WIP warehouse. `wip_step` or `skip_transfer`
  uses Main Stock directly; transfers cover only the next required unit.
- Source tracking is checked after saving, allowing normal automatic source batch
  selection. Explicit serial/batch conflicts remain errors.
- Work Order selection excludes other companies and unrelated Sales Orders.
- The 4D preview uses the same stage planner as execution, including missing
  component orders, resumed stages, spare final batches, and transfer decisions.
  Supplied-batch demand is aggregated and checked by warehouse. It remains a
  preview: current stock, native validations and submit hooks are checked again
  during execution.
- During the execution scope, database commits requested by legacy hooks are
  deferred. This is necessary because the existing Batch barcode `after_insert`
  hook commits immediately. The request's database commit method is restored on
  success and failure; failures roll back all stock stages. The initial execution
  log is committed before this stock scope, as in the original master.

For other product prefixes, the original production routing and P202 mapping are
retained, together with the shared validation and transaction corrections.

## Validation

```bash
env/bin/python -m unittest \
  amf.amf.utils.test_fftest_4d_flow \
  amf.amf.utils.test_fftest_serial_mapping -v
```

The new tests use an in-memory document/stock adapter and the installed ERPNext
V12 serial validator. They cover the full chain, serial carryover, normalized BOM
quantities, existing-stage reuse, custom WIP, automatic and explicit batches,
Work Order creation/scope, preview behavior, unchanged non-4D routing, and rollback
after a final-stage failure. They do not initialize a site or post live stock.
