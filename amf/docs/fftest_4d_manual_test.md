# Manually test the full 4D FFTest stock flow

The helper at `tools/fftest_manual_server.py` replaces the FFTest Connect browser
handoff for a manual test. It does not communicate with hardware. It sends the
same URL inputs to ERP and receives the existing `/run_test` return redirect.

Run the helper **on the computer running the browser**. The Web Page's
`127.0.0.1:5001` address refers to that computer, not to the ERP server.

## Initial site check

The initial read-only checks on `site1.local` on 2026-10-29 found:

- No BOMs for items beginning `5D0`.
- No submitted, active `4D` Work Orders with at least one unit remaining.
- `5D0000` and `5D0001` use serials and batches, but have no default BOM.
- `5D000A` has serial tracking disabled.
- `5D1000` and `5D100A` use serials and have default BOMs.

The lack of a `5D0000` BOM is expected: it is purchased and received into Main
Stock with its serial. The complete purchased-item flow manufactures only `5D1`
and `4D`; it must not create a `5D0000` Work Order.

## 1. Prepare one unit in the ERP you will test

Run submits real Stock Entries in the selected ERP site. Use your test site for
an isolated trial. That site's AMF checkout must contain commit `ef87569`.

Prepare the real or dedicated test item/BOM chain:

```text
4D product BOM -> one serialized 5D1 component
5D1 BOM        -> one purchased, serialized 5D0000 component
5D0000         -> already received in Main Stock with its serial and batch
```

Both component items must be enabled serialized stock items. If a variant such
as `5D000A` is the component, its current configuration needs attention before
it can exercise a serialized flow. Do not create an artificial BOM or Work Order
for purchased `5D0000`, or manually create an unreceived Serial No.

Submit and activate the BOMs. Ensure the relevant BOM Item rows link to the
selected `5D1` BOM, or the component has that BOM as its default. The purchased
`5D0000` serial and any other required material stock/batches must be available
in Main Stock before the flow.

For a predictable first trial, prepare the two manufacturing Work Orders:

| Order | Production item | Quantity | Parent Work Order |
|---|---|---:|---|
| Final | Your `4D` item | 1 | As appropriate |
| Body | Its exact `5D1` component | 1 | Final order |

Use the same company, the same Sales Order or empty Sales Orders, and the selected
BOMs. Disable **Use Multi-Level BOM** so each order directly requires its immediate
components. Use Main Stock as the finished-goods warehouse and configure each
order's WIP warehouse/transfer settings as required by your process.

Submit the orders and complete any required operations/Job Cards. Before running,
Produced Quantity should still be zero. Let the algorithm create the manufacturing
Stock Entries and any required material-transfer entries.

Enter the existing serial recorded on the purchased `5D0000`, exactly as shown
in ERP. For example, use `0070` if that is its received serial. A fresh, unknown
serial is rejected rather than triggering a raw-body BOM lookup. The new 4D flow
uses the same serial for `5D1` and does not require the old P202 transformation.

## 2. Duplicate the Web Page for this test

The existing record is named `fftest-stock-entry`, but its public route is
`fftest_stock_entry` (underscores).

The published test copy verified on `site1.local` on 2026-10-29 is named
`fftest-stock-entry-test`, with Route `fftest_stock_entry_test`. It already calls
`amf.www.fftest_master_debug_4d.make_stock_entry`. If using that copy, check its
printing setting below; another duplicate is unnecessary.

In Desk, open that **Web Page** record and use **Menu -> Duplicate**. In the copy:

- Set an identifiable title such as `FFTest Stock Entry 4D Test`.
- Set Route to `fftest_stock_entry_test` (or another unused test route).
- Enable Published.
- In JavaScript, replace the backend method:

```javascript
method: 'amf.www.fftest_master_debug.make_stock_entry',
```

with:

```javascript
method: 'amf.www.fftest_master_debug_4d.make_stock_entry',
```

For a stock-flow test without label printing, also replace:

```javascript
const linePrinted = await print_serial_no_document(mixerSn);
```

with:

```javascript
const linePrinted = []; // Manual stock-flow test: skip the printer.
```

Save the copy. Retain the original Web Page unchanged.

The duplicate executes automatically when it receives both `of` and `sn` query
parameters. Open its route without parameters if you only want to check that it
loads. The helper's Preview button goes to a separate read-only method.

## 3. Start the local helper

Copy `tools/fftest_manual_server.py` onto the browser computer. It needs Python 3
and no additional packages. From the directory containing the copied file:

```bash
python3 fftest_manual_server.py --erp-url https://YOUR-ERP-HOST --route fftest_stock_entry_test
```

Replace `https://YOUR-ERP-HOST` with the ERP base URL from your browser's address
bar, without `/desk`, a Web Page route, or query parameters. On Windows, use `py`
instead of `python3` if that is your Python launcher.

For the local ERP at `http://localhost:8000` and the existing test copy, use:

```bash
python3 fftest_manual_server.py --erp-url http://localhost:8000 --route fftest_stock_entry_test
```

`fftest_manual_server.py` is the script Python runs. The `--route` value is the
ERP Web Page's saved **Route** field. Supplying the script filename there sends
the browser to `/fftest_manual_server.py` on ERP and produces a Frappe 404 page.
The helper now rejects that configuration before starting.

Before execution, open `http://localhost:8000/fftest_stock_entry_test` without
query parameters to confirm the test page exists. That URL does not start a
stock request because it has neither `of` nor `sn`. If your copy uses a different
route, substitute its exact Route field in both the URL and the helper command.

Keep this terminal open. The helper listens on `127.0.0.1:5001`, matching the
existing page. If FFTest Connect already uses that port on this computer, close
it before running the helper.

## 4. Log in and fill the test form

Log into the selected ERP site in the same browser you will use for the test.
This bypasses the page's automatic-login path. The helper does not supply ERP
credentials.

Open `http://127.0.0.1:5001` and enter:

- **4D Work Order:** the final-product Work Order name.
- **Manually entered Serial No:** the received `5D0000` serial selected above.
- **Batch selections:** `[]` for standard automatic source-batch selection, or
  an array of actual batch names, e.g. `[{"batch_no":"YOUR-MATERIAL-BATCH"}]`.
- **Test ID:** leave `MANUAL-TEST` or enter your own label.
- **COM label:** leave `SIMULATED`; no serial port is opened.

The helper maps these to the page's `of`, `sn`, `batch_list`, `id` and `com` query
parameters, with correct URL encoding.

## 5. Preview

Click **Open read-only preview**. A new tab shows the ERP JSON response. Inspect
the report inside `message`:

- `ok` must be `true`; resolve any `errors` first.
- `can_execute` must be `true` for the logged-in user's permissions.
- The two `Manufacture` plans must produce `5D1`, then `4D`.
- The first must consume the existing `5D0000` with your entered serial, and
  produce `5D1` with that same serial. There must be no `5D0000` production plan.
- The plan may include material transfers, depending on the Work Orders.

The preview creates no stock entries. Its success does not replace native
stock, operation-completion and submit-hook validation during execution.

## 6. Execute once

Return to the local form and click **Run through ERP Web Page** once.

The browser navigates to the copied ERP page. That page submits the new backend
method, optionally prints, and returns to:

```text
http://127.0.0.1:5001/run_test?com=SIMULATED&id=MANUAL-TEST
```

On a backend error, the page adds `erreur=...`, and the helper displays the error.
Do not refresh an execution URL containing `of` and `sn` to inspect the result:
that starts another request. Use Desk to inspect the created documents.

## 7. Verify the ERP records

In Stock Entry List, filter by each of the two Work Orders. Check:

1. The received `5D0000` was available in Main Stock before the test; no raw-body
   BOM, Work Order or Manufacture entry is created by this flow.
2. A submitted Manufacture entry consumes that `5D0000` and produces one `5D1`,
   carrying the same serial in that entry.
3. A submitted Manufacture entry consumes the `5D1` and produces one `4D`.
4. Each Work Order's Produced Quantity has increased by one.
5. Any additional material-transfer entries use the configured WIP warehouses.
6. The final finished-goods row has `product_serial_no` set when that custom
   field exists. Component quantities and batches match their actual BOM needs.

There is one Serial No record carried between serialized items. If the final
4D item is not serialized, after consumption that record normally belongs to the
5D1 item and has no warehouse. That is expected; it was consumed into the final
product. If 4D is serialized, the record instead ends on the 4D item in Main Stock.

If printing is enabled and the page stalls after stock was submitted, inspect
the Stock Entries before retrying; a printing issue does not undo posted stock.
If the backend returns an error, inspect its `log_id` in the network response or
the latest FFTest Log Entry for the underlying validation message.

Stop the local helper with Ctrl+C when finished.
