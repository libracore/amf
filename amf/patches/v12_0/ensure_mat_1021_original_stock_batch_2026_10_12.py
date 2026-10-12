from __future__ import unicode_literals

import frappe
from frappe.utils import flt


ITEM_CODE = "MAT.1021"
BATCH_ID = "KRDLAT AMF"
SOURCE_ENTRY = "STE-14142"
TRANSFER_ENTRY = "STE-18224"
SOURCE_DETAIL = "11ca2ea32d"
TRANSFER_DETAIL = "4c67668fef"

DETAILS = (
    (SOURCE_DETAIL, SOURCE_ENTRY, "Material Receipt", 1.0, None, "Main Stock - AMF21"),
    (TRANSFER_DETAIL, TRANSFER_ENTRY, "Send to Subcontractor", 0.45, "Main Stock - AMF21", "Bossme'd - AMF21"),
)
LEDGER = (
    ("SLE/00112798", SOURCE_ENTRY, SOURCE_DETAIL, "Main Stock - AMF21", 1.0),
    ("SLE/00131129", TRANSFER_ENTRY, TRANSFER_DETAIL, "Main Stock - AMF21", -0.45),
    ("SLE/00131133", TRANSFER_ENTRY, TRANSFER_DETAIL, "Bossme'd - AMF21", 0.45),
)


def execute():
    """Keep the original 1 m stock and its transfer on a separate batch."""
    if frappe.local.site != "site1.local":
        return

    if not frappe.db.get_value("Item", ITEM_CODE, "has_batch_no"):
        frappe.throw("MAT.1021 must be batch tracked before assigning its original stock.")

    for detail_name, entry_name, purpose, qty, source, target in DETAILS:
        entry = frappe.db.get_value("Stock Entry", entry_name, ["docstatus", "purpose"], as_dict=True)
        detail = frappe.db.get_value(
            "Stock Entry Detail",
            detail_name,
            ["parent", "item_code", "docstatus", "qty", "transfer_qty", "s_warehouse", "t_warehouse", "batch_no"],
            as_dict=True,
        )
        if (
            not entry or entry.docstatus != 1 or entry.purpose != purpose
            or not detail or detail.parent != entry_name or detail.item_code != ITEM_CODE
            or detail.docstatus != 1 or abs(flt(detail.qty) - qty) > 0.000001
            or abs(flt(detail.transfer_qty) - qty) > 0.000001
            or detail.s_warehouse != source or detail.t_warehouse != target
        ):
            frappe.throw("Stock entry detail {0} changed; review the batch migration.".format(detail_name))

    expected_ledger = {row[0]: row for row in LEDGER}
    entries = frappe.db.sql(
        """
        SELECT name, voucher_type, voucher_no, voucher_detail_no, item_code,
               warehouse, actual_qty, batch_no
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
          AND voucher_type = 'Stock Entry'
          AND voucher_no IN (%s, %s)
          AND voucher_detail_no IN (%s, %s)
          AND docstatus = 1
          AND IFNULL(is_cancelled, 'No') = 'No'
        """,
        (ITEM_CODE, SOURCE_ENTRY, TRANSFER_ENTRY, SOURCE_DETAIL, TRANSFER_DETAIL),
        as_dict=True,
    )
    if {entry.name for entry in entries} != set(expected_ledger):
        frappe.throw("MAT.1021 original stock ledger entries changed; review the batch migration.")
    for entry in entries:
        name, voucher, detail, warehouse, qty = expected_ledger[entry.name]
        if (
            entry.voucher_no != voucher or entry.voucher_detail_no != detail
            or entry.warehouse != warehouse or abs(flt(entry.actual_qty) - qty) > 0.000001
        ):
            frappe.throw("Stock ledger entry {0} changed; review the batch migration.".format(name))

    linked = frappe.db.get_all(
        "Batch",
        filters={"item": ITEM_CODE, "reference_doctype": "Stock Entry", "reference_name": SOURCE_ENTRY},
        fields=["name"],
    )
    if len(linked) > 1:
        frappe.throw("Multiple MAT.1021 batches link to STE-14142.")
    batch_no = linked[0].name if linked else BATCH_ID
    for detail_name, unused_entry, unused_purpose, unused_qty, unused_source, unused_target in DETAILS:
        current = frappe.db.get_value("Stock Entry Detail", detail_name, "batch_no")
        if current and current != batch_no:
            frappe.throw("Stock Entry Detail {0} uses another batch.".format(detail_name))
    if any(entry.batch_no and entry.batch_no != batch_no for entry in entries):
        frappe.throw("MAT.1021 original stock ledger entries use another batch.")

    if not linked:
        if frappe.db.exists("Batch", BATCH_ID):
            frappe.throw("Batch KRDLAT AMF is already linked to a different source.")
        batch = frappe.get_doc({
            "doctype": "Batch",
            "batch_id": BATCH_ID,
            "item": ITEM_CODE,
            "reference_doctype": "Stock Entry",
            "reference_name": SOURCE_ENTRY,
            "manufacturing_date": None,
            "description": "Original 1 m material receipt; 0.45 m later sent to subcontractor via STE-18224.",
        }).insert(ignore_permissions=True)
        if batch.name != BATCH_ID:
            frappe.throw("MAT.1021 batch naming changed; review the patch before migrating.")
        if batch.manufacturing_date:
            frappe.db.set_value("Batch", batch.name, "manufacturing_date", None, update_modified=False)

    for detail_name, unused_entry, unused_purpose, unused_qty, unused_source, unused_target in DETAILS:
        if not frappe.db.get_value("Stock Entry Detail", detail_name, "batch_no"):
            frappe.db.set_value("Stock Entry Detail", detail_name, "batch_no", batch_no, update_modified=False)
    for entry in entries:
        if not entry.batch_no:
            frappe.db.set_value("Stock Ledger Entry", entry.name, "batch_no", batch_no, update_modified=False)
