from __future__ import unicode_literals

import frappe
from frappe.utils import flt, nowdate, nowtime

from erpnext.stock.doctype.batch.batch import get_batch_qty


ITEM_CODE = "110137"
BATCH_NO = "CTD694 AMF"
WAREHOUSE = "Main Stock - AMF21"
SOURCE_ENTRY = "STE-16191"
ADJUSTMENT_ACCOUNT = "4900 - Stock variation - AMF21"
COST_CENTER = "General - AMF21"

DETAILS = (
    ("c3e86e06a2", "STE-16191", 45.0, None, WAREHOUSE),
    ("7089a5a30f", "STE-16192", 15.0, WAREHOUSE, "Work In Progress - AMF21"),
    ("1dfb4e17f7", "STE-16193", 15.0, "Work In Progress - AMF21", None),
)
LEDGER = (
    ("SLE/00121741", "STE-16191", "c3e86e06a2", WAREHOUSE, 45.0),
    ("SLE/00121742", "STE-16192", "7089a5a30f", WAREHOUSE, -15.0),
    ("SLE/00121744", "STE-16192", "7089a5a30f", "Work In Progress - AMF21", 15.0),
    ("SLE/00121747", "STE-16193", "1dfb4e17f7", "Work In Progress - AMF21", -15.0),
)


def execute():
    """Batch the original manufacture and remove its duplicate 30 Nos balance."""
    if frappe.local.site != "site1.local":
        return

    if not frappe.db.get_value("Item", ITEM_CODE, "has_batch_no"):
        frappe.throw("Item 110137 must be batch tracked before this correction.")

    original_adjustment = frappe.db.get_value(
        "Stock Reconciliation", "SR/00723", ["docstatus", "difference_amount", "expense_account"], as_dict=True
    )
    if (
        not original_adjustment or original_adjustment.docstatus != 1
        or abs(flt(original_adjustment.difference_amount) - 70.5) > 0.000001
        or original_adjustment.expense_account != ADJUSTMENT_ACCOUNT
    ):
        frappe.throw("Original stock reconciliation SR/00723 changed; review the correction.")

    for name, parent, qty, source, target in DETAILS:
        row = frappe.db.get_value(
            "Stock Entry Detail",
            name,
            ["parent", "item_code", "docstatus", "qty", "transfer_qty", "s_warehouse", "t_warehouse", "batch_no"],
            as_dict=True,
        )
        if (
            not row or row.parent != parent or row.item_code != ITEM_CODE or row.docstatus != 1
            or abs(flt(row.qty) - qty) > 0.000001
            or abs(flt(row.transfer_qty) - qty) > 0.000001
            or row.s_warehouse != source or row.t_warehouse != target
            or (row.batch_no and row.batch_no != BATCH_NO)
        ):
            frappe.throw("Stock Entry Detail {0} changed; review the correction.".format(name))

    expected = {row[0]: row for row in LEDGER}
    entries = frappe.db.sql(
        """
        SELECT name, voucher_no, voucher_detail_no, warehouse, actual_qty, batch_no
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s AND voucher_type = 'Stock Entry'
          AND voucher_no IN ('STE-16191', 'STE-16192', 'STE-16193')
          AND docstatus = 1 AND IFNULL(is_cancelled, 'No') = 'No'
        """,
        (ITEM_CODE,),
        as_dict=True,
    )
    if {entry.name for entry in entries} != set(expected):
        frappe.throw("Original stock ledger entries for 110137 changed; review the correction.")
    for entry in entries:
        unused_name, parent, detail, warehouse, qty = expected[entry.name]
        if (
            entry.voucher_no != parent or entry.voucher_detail_no != detail
            or entry.warehouse != warehouse or abs(flt(entry.actual_qty) - qty) > 0.000001
            or (entry.batch_no and entry.batch_no != BATCH_NO)
        ):
            frappe.throw("Stock Ledger Entry {0} changed; review the correction.".format(entry.name))

    source_batches = frappe.db.get_all(
        "Batch",
        filters={"item": ITEM_CODE, "reference_doctype": "Stock Entry", "reference_name": SOURCE_ENTRY},
        fields=["name"],
    )
    if any(row.name != BATCH_NO for row in source_batches):
        frappe.throw("Another batch is already linked to STE-16191.")

    batch = frappe.db.get_value(
        "Batch", BATCH_NO, ["item", "reference_doctype", "reference_name"], as_dict=True
    )
    if batch and (
        batch.item != ITEM_CODE or batch.reference_doctype != "Stock Entry"
        or batch.reference_name != SOURCE_ENTRY
    ):
        frappe.throw("Batch CTD694 AMF is linked to another source.")
    if not batch:
        batch = frappe.get_doc({
            "doctype": "Batch",
            "batch_id": BATCH_NO,
            "item": ITEM_CODE,
            "reference_doctype": "Stock Entry",
            "reference_name": SOURCE_ENTRY,
            "manufacturing_date": "2026-06-11",
            "description": (
                "Retroactive batch for 45 Nos manufactured in STE-16191; "
                "15 Nos later consumed through STE-16192 and STE-16193."
            ),
        }).insert(ignore_permissions=True)
        if batch.name != BATCH_NO:
            frappe.throw("Batch naming changed; review the correction before migrating.")

    for name, unused_parent, unused_qty, unused_source, unused_target in DETAILS:
        if not frappe.db.get_value("Stock Entry Detail", name, "batch_no"):
            frappe.db.set_value("Stock Entry Detail", name, "batch_no", BATCH_NO, update_modified=False)
    for entry in entries:
        if not entry.batch_no:
            frappe.db.set_value("Stock Ledger Entry", entry.name, "batch_no", BATCH_NO, update_modified=False)

    corrections = frappe.db.sql(
        """
        SELECT sle.voucher_no, sle.actual_qty, sle.stock_value_difference,
               sr.docstatus, sr.expense_account, sr.cost_center
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabStock Reconciliation` sr ON sr.name = sle.voucher_no
        WHERE sle.item_code = %s AND sle.batch_no = %s AND sle.warehouse = %s
          AND sle.voucher_type = 'Stock Reconciliation'
          AND sle.actual_qty < 0 AND sle.docstatus = 1
          AND IFNULL(sle.is_cancelled, 'No') = 'No'
        """,
        (ITEM_CODE, BATCH_NO, WAREHOUSE),
        as_dict=True,
    )
    if corrections:
        if len(corrections) != 1:
            frappe.throw("Multiple stock corrections exist for batch CTD694 AMF.")
        correction = corrections[0]
        if (
            correction.docstatus != 1 or abs(flt(correction.actual_qty) + 30) > 0.000001
            or abs(flt(correction.stock_value_difference) + 70.5) > 0.000001
            or correction.expense_account != ADJUSTMENT_ACCOUNT or correction.cost_center != COST_CENTER
        ):
            frappe.throw("The existing 110137 stock correction has changed.")
        return

    bin_qty = frappe.db.get_value("Bin", {"item_code": ITEM_CODE, "warehouse": WAREHOUSE}, "actual_qty")
    if abs(flt(bin_qty) - 30) > 0.000001 or abs(get_batch_qty(BATCH_NO, WAREHOUSE) - 30) > 0.000001:
        frappe.throw("The 110137 stock balance changed; review before removing the 30 Nos.")

    reconciliation = frappe.get_doc({
        "doctype": "Stock Reconciliation",
        "naming_series": "SR/",
        "company": "Advanced Microfluidics SA",
        "purpose": "Stock Reconciliation",
        "posting_date": nowdate(),
        "posting_time": nowtime(),
        "set_posting_time": 1,
        "expense_account": ADJUSTMENT_ACCOUNT,
        "cost_center": COST_CENTER,
        "items": [{
            "item_code": ITEM_CODE,
            "warehouse": WAREHOUSE,
            "batch_no": BATCH_NO,
            "qty": 0,
            "valuation_rate": 2.35,
        }],
    })
    reconciliation.flags.ignore_permissions = True
    reconciliation.insert(ignore_permissions=True)
    reconciliation.submit()
    reconciliation.add_comment(
        "Info",
        "Corrects the duplicate 30 Nos balance for item 110137: the original 45 Nos in "
        "STE-16191 had 15 Nos consumed through STE-16192/STE-16193, while "
        "SR/00723 added another 30 Nos for OF-04073.",
    )
    if abs(get_batch_qty(BATCH_NO, WAREHOUSE)) > 0.000001:
        frappe.throw("The 110137 stock correction did not clear the batch.")
