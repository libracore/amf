from __future__ import unicode_literals

import frappe
from frappe.utils import flt

from erpnext.stock.doctype.batch.batch import get_batch_qty

from amf.patches.v12_0 import ensure_mat_1021_original_stock_batch_2026_10_12 as original
from amf.patches.v12_0 import ensure_mat_1021_receipt_batch_2026_10_12 as purchased


CONSUMPTION_RECEIPT = "PREC-03061-1"
CONSUMPTION_DETAIL = "6b56205504"
CONSUMPTION_LEDGER = "SLE/00135747"
SUBCONTRACTOR_WAREHOUSE = "Bossme'd - AMF21"


def _validate_consumption():
    receipt = frappe.db.get_value(
        "Purchase Receipt", CONSUMPTION_RECEIPT,
        ["docstatus", "is_subcontracted", "supplier_warehouse"], as_dict=True,
    )
    detail = frappe.db.get_value(
        "Purchase Receipt Item Supplied", CONSUMPTION_DETAIL,
        ["parent", "docstatus", "rm_item_code", "consumed_qty", "batch_no", "reference_name"],
        as_dict=True,
    )
    ledger = frappe.db.get_value(
        "Stock Ledger Entry", CONSUMPTION_LEDGER,
        ["voucher_type", "voucher_no", "voucher_detail_no", "docstatus", "is_cancelled",
         "item_code", "warehouse", "actual_qty", "batch_no"], as_dict=True,
    )
    if (
        not receipt or receipt.docstatus != 1 or receipt.is_subcontracted != "Yes"
        or receipt.supplier_warehouse != SUBCONTRACTOR_WAREHOUSE
        or not detail or detail.parent != CONSUMPTION_RECEIPT or detail.docstatus != 1
        or detail.rm_item_code != original.ITEM_CODE
        or abs(flt(detail.consumed_qty) - 0.3) > 0.000001
        or not ledger or ledger.voucher_type != "Purchase Receipt"
        or ledger.voucher_no != CONSUMPTION_RECEIPT
        or ledger.voucher_detail_no != CONSUMPTION_DETAIL
        or ledger.docstatus != 1 or ledger.is_cancelled == "Yes"
        or ledger.item_code != original.ITEM_CODE
        or ledger.warehouse != SUBCONTRACTOR_WAREHOUSE
        or abs(flt(ledger.actual_qty) + 0.3) > 0.000001
    ):
        frappe.throw("MAT.1021 subcontract consumption changed; review the batch repair.")

    purchase_order = frappe.db.get_value(
        "Purchase Receipt Item", detail.reference_name, "purchase_order"
    )
    if purchase_order != frappe.db.get_value("Stock Entry", original.TRANSFER_ENTRY, "purchase_order"):
        frappe.throw("MAT.1021 transfer and consumption refer to different purchase orders.")
    return detail, ledger


def execute():
    """Restore missing MAT.1021 batches and include the later subcontract consumption.

    A new patch is needed because the earlier setup patches are already in Patch Log
    even though the Item flag, batches, and transaction batch links are absent.
    Only batch metadata changes; quantities, valuation, and GL remain unchanged.
    The caller owns the transaction.
    """
    if frappe.local.site != "site1.local":
        return

    detail, ledger = _validate_consumption()
    bins_before = frappe.get_all(
        "Bin", filters={"item_code": original.ITEM_CODE},
        fields=["name", "actual_qty", "stock_value", "valuation_rate"], order_by="name",
    )

    # Restore the two source batches even when their older migrations are logged.
    purchased.execute()
    original.execute()
    batch_no = frappe.db.get_value("Stock Entry Detail", original.SOURCE_DETAIL, "batch_no")
    # The original receipt has no recorded manufacturing date. Batch defaults
    # must not substitute the repair date for the material's actual age.
    if frappe.db.get_value("Batch", batch_no, "manufacturing_date"):
        frappe.db.set_value("Batch", batch_no, "manufacturing_date", None, update_modified=False)
    for row in (detail, ledger):
        if row.batch_no and row.batch_no != batch_no:
            frappe.throw("MAT.1021 subcontract consumption uses a different batch.")
    if not detail.batch_no:
        frappe.db.set_value(
            "Purchase Receipt Item Supplied", CONSUMPTION_DETAIL,
            "batch_no", batch_no, update_modified=False,
        )
    if not ledger.batch_no:
        frappe.db.set_value(
            "Stock Ledger Entry", CONSUMPTION_LEDGER,
            "batch_no", batch_no, update_modified=False,
        )

    unbatched = frappe.db.sql(
        """SELECT name FROM `tabStock Ledger Entry`
        WHERE item_code = %s AND docstatus = 1
          AND IFNULL(is_cancelled, 'No') = 'No' AND IFNULL(batch_no, '') = ''""",
        (original.ITEM_CODE,),
    )
    if unbatched:
        frappe.throw("MAT.1021 has other unbatched stock movements; review the batch repair.")

    # Each warehouse's batch balances must agree with its physical stock balance.
    for stock_bin in frappe.get_all(
        "Bin", filters={"item_code": original.ITEM_CODE}, fields=["warehouse", "actual_qty"]
    ):
        batch_qty = get_batch_qty(item_code=original.ITEM_CODE, warehouse=stock_bin.warehouse)
        if (
            any(flt(row.qty) < -0.000001 for row in batch_qty)
            or abs(sum(flt(row.qty) for row in batch_qty) - flt(stock_bin.actual_qty)) > 0.000001
        ):
            frappe.throw("MAT.1021 batch balance differs from stock in {0}.".format(stock_bin.warehouse))

    bins_after = frappe.get_all(
        "Bin", filters={"item_code": original.ITEM_CODE},
        fields=["name", "actual_qty", "stock_value", "valuation_rate"], order_by="name",
    )
    if bins_before != bins_after:
        frappe.throw("MAT.1021 stock quantities or values changed during the batch repair.")

    for doctype, name in (
        ("Item", original.ITEM_CODE),
        ("Stock Entry", original.SOURCE_ENTRY),
        ("Stock Entry", original.TRANSFER_ENTRY),
        ("Purchase Receipt", purchased.RECEIPT_NAME),
        ("Purchase Receipt", CONSUMPTION_RECEIPT),
    ):
        frappe.clear_document_cache(doctype, name)
