from __future__ import unicode_literals

import frappe


ITEM_CODE = "MAT.1021"
RECEIPT_NAME = "PREC-02877"
BATCH_ID = "8UREHM DAL"


def execute():
    """Preserve the requested batch setup through the next site migration."""
    if frappe.local.site != "site1.local":
        return

    item = frappe.db.get_value(
        "Item", ITEM_CODE, ["is_stock_item", "disabled", "has_batch_no"], as_dict=True
    )
    if not item or not item.is_stock_item or item.disabled:
        frappe.throw("MAT.1021 must exist as an active stock item before batching it.")

    receipt = frappe.db.get_value(
        "Purchase Receipt", RECEIPT_NAME, ["docstatus", "is_return", "supplier"], as_dict=True
    )
    if not receipt or receipt.docstatus != 1 or receipt.is_return:
        frappe.throw("PREC-02877 must be a submitted purchase receipt.")

    rows = frappe.db.get_all(
        "Purchase Receipt Item",
        filters={"parent": RECEIPT_NAME, "item_code": ITEM_CODE},
        fields=["name", "batch_no", "stock_qty"],
    )
    if not rows:
        frappe.throw("PREC-02877 has no MAT.1021 item row.")

    linked = frappe.db.get_all(
        "Batch",
        filters={
            "item": ITEM_CODE,
            "reference_doctype": "Purchase Receipt",
            "reference_name": RECEIPT_NAME,
        },
        fields=["name"],
    )
    if len(linked) > 1:
        frappe.throw("Multiple MAT.1021 batches link to PREC-02877.")

    if not item.has_batch_no:
        frappe.db.set_value("Item", ITEM_CODE, "has_batch_no", 1, update_modified=False)

    if linked:
        batch_no = linked[0].name
    else:
        if frappe.db.exists("Batch", BATCH_ID):
            frappe.throw("Batch 8UREHM DAL is already linked to a different source.")
        batch = frappe.get_doc(
            {
                "doctype": "Batch",
                "batch_id": BATCH_ID,
                "item": ITEM_CODE,
                "supplier": receipt.supplier,
                "reference_doctype": "Purchase Receipt",
                "reference_name": RECEIPT_NAME,
                "manufacturing_date": None,
            }
        ).insert(ignore_permissions=True)
        batch_no = batch.name
        if batch_no != BATCH_ID:
            frappe.throw("MAT.1021 batch naming changed; review the patch before migrating.")
        if batch.manufacturing_date:
            frappe.db.set_value("Batch", batch_no, "manufacturing_date", None, update_modified=False)

    for row in rows:
        if row.batch_no and row.batch_no != batch_no:
            frappe.throw("Purchase Receipt Item {0} uses another batch.".format(row.name))

        entries = frappe.db.sql(
            """
            SELECT name, batch_no, actual_qty
            FROM `tabStock Ledger Entry`
            WHERE voucher_type = 'Purchase Receipt'
              AND voucher_no = %s
              AND voucher_detail_no = %s
              AND item_code = %s
              AND docstatus = 1
              AND IFNULL(is_cancelled, 'No') = 'No'
            """,
            (RECEIPT_NAME, row.name, ITEM_CODE),
            as_dict=True,
        )
        if not entries or abs(sum(entry.actual_qty for entry in entries) - row.stock_qty) > 0.000001:
            frappe.throw("Receipt row {0} has missing or inconsistent stock ledger entries.".format(row.name))
        if any(entry.batch_no and entry.batch_no != batch_no for entry in entries):
            frappe.throw("Receipt row {0} has stock ledger entries using another batch.".format(row.name))

        if not row.batch_no:
            frappe.db.set_value("Purchase Receipt Item", row.name, "batch_no", batch_no, update_modified=False)
        for entry in entries:
            if not entry.batch_no:
                frappe.db.set_value("Stock Ledger Entry", entry.name, "batch_no", batch_no, update_modified=False)
