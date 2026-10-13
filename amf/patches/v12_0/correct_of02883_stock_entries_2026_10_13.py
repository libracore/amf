from __future__ import unicode_literals

import frappe
from frappe.utils import flt, nowdate, nowtime

from erpnext.stock.stock_ledger import update_entries_after


OLD = "520000"
NEW = "520006"
WORK_ORDER = "OF-02883"
MAIN = "Main Stock - AMF21"
WIP = "Work In Progress - AMF21"
COMPANY = "Advanced Microfluidics SA"
ADJUSTMENT_ACCOUNT = "4900 - Stock variation - AMF21"
REPACK_REMARKS = "OF-02883 correction: reclassify 20 Nos 520000 to 520006 before STE-13919"
RECONCILIATION_COMMENT = "OF-02883 correction: remove 20 Nos 520006 after correcting STE-13919 and STE-13921."

DETAILS = (
    ("b5fd16c9fa", "STE-13919", MAIN, WIP),
    ("8810feb901", "STE-13921", WIP, None),
)
LEDGER = (
    ("SLE/00111427", "STE-13919", "b5fd16c9fa", MAIN, -20),
    ("SLE/00111429", "STE-13919", "b5fd16c9fa", WIP, 20),
    ("SLE/00111432", "STE-13921", "8810feb901", WIP, -20),
)


def _assert_close(actual, expected, label):
    if abs(flt(actual) - expected) > 0.000001:
        frappe.throw("{0} changed; expected {1}, found {2}.".format(label, expected, actual))


def _get_repack():
    names = frappe.get_all(
        "Stock Entry", filters={"purpose": "Repack", "remarks": REPACK_REMARKS}, fields=["name"]
    )
    if len(names) > 1:
        frappe.throw("More than one OF-02883 reclassification exists.")
    return names[0].name if names else None


def _get_reconciliation():
    names = frappe.get_all(
        "Comment", filters={
            "reference_doctype": "Stock Reconciliation",
            "content": RECONCILIATION_COMMENT,
        }, fields=["reference_name"]
    )
    if len(names) > 1:
        frappe.throw("More than one OF-02883 stock removal exists.")
    return names[0].reference_name if names else None


def _assert_entries(item_code):
    for name, parent, source, target in DETAILS:
        row = frappe.db.get_value(
            "Stock Entry Detail", name,
            ["parent", "item_code", "docstatus", "qty", "transfer_qty", "s_warehouse", "t_warehouse"],
            as_dict=True,
        )
        if (
            not row or row.parent != parent or row.item_code != item_code or row.docstatus != 1
            or row.s_warehouse != source or row.t_warehouse != target
        ):
            frappe.throw("Stock Entry Detail {0} changed; review OF-02883.".format(name))
        _assert_close(row.qty, 20, name + " qty")
        _assert_close(row.transfer_qty, 20, name + " transfer_qty")

    for name, parent, detail, warehouse, qty in LEDGER:
        row = frappe.db.get_value(
            "Stock Ledger Entry", name,
            ["voucher_type", "voucher_no", "voucher_detail_no", "item_code", "warehouse", "actual_qty", "docstatus", "is_cancelled"],
            as_dict=True,
        )
        if (
            not row or row.voucher_type != "Stock Entry" or row.voucher_no != parent
            or row.voucher_detail_no != detail or row.item_code != item_code
            or row.warehouse != warehouse or row.docstatus != 1
            or row.is_cancelled == "Yes"
        ):
            frappe.throw("Stock Ledger Entry {0} changed; review OF-02883.".format(name))
        _assert_close(row.actual_qty, qty, name + " actual_qty")


def _assert_applied(repack_name, reconciliation_name):
    _assert_entries(NEW)
    if frappe.db.get_value("Stock Entry", repack_name, "docstatus") != 1:
        frappe.throw("OF-02883 reclassification is not submitted.")
    repack_items = frappe.db.get_all(
        "Stock Entry Detail", filters={"parent": repack_name},
        fields=["item_code", "qty", "s_warehouse", "t_warehouse"], order_by="idx",
    )
    if len(repack_items) != 2 or [row.item_code for row in repack_items] != [OLD, NEW]:
        frappe.throw("OF-02883 reclassification rows changed.")
    _assert_close(repack_items[0].qty, 20, "reclassification outgoing qty")
    _assert_close(repack_items[1].qty, 20, "reclassification incoming qty")
    if (
        repack_items[0].s_warehouse != MAIN or repack_items[0].t_warehouse
        or repack_items[1].s_warehouse or repack_items[1].t_warehouse != MAIN
    ):
        frappe.throw("OF-02883 reclassification warehouses changed.")

    reconciliation = frappe.db.get_value(
        "Stock Reconciliation", reconciliation_name, ["docstatus", "expense_account", "cost_center"], as_dict=True
    )
    if (
        not reconciliation or reconciliation.docstatus != 1
        or reconciliation.expense_account != ADJUSTMENT_ACCOUNT
        or reconciliation.cost_center != "General - AMF21"
    ):
        frappe.throw("OF-02883 stock removal changed.")
    removed = frappe.db.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": "Stock Reconciliation", "voucher_no": reconciliation_name},
        fields=["item_code", "warehouse", "actual_qty", "qty_after_transaction", "stock_value_difference", "docstatus"],
    )
    if len(removed) != 1 or removed[0].item_code != NEW or removed[0].warehouse != MAIN or removed[0].docstatus != 1:
        frappe.throw("OF-02883 stock removal ledger changed.")
    _assert_close(removed[0].qty_after_transaction, 0, "OF-02883 stock removal final qty")
    if flt(removed[0].stock_value_difference) >= 0:
        frappe.throw("OF-02883 stock removal did not reduce stock value.")
    reconciliation_items = frappe.db.get_all(
        "Stock Reconciliation Item", filters={"parent": reconciliation_name},
        fields=["item_code", "warehouse", "qty"],
    )
    if len(reconciliation_items) != 1 or reconciliation_items[0].item_code != NEW or reconciliation_items[0].warehouse != MAIN:
        frappe.throw("OF-02883 stock removal item changed.")
    _assert_close(reconciliation_items[0].qty, 0, "OF-02883 stock removal item qty")

    work_order_items = frappe.db.get_all("Work Order Item", filters={"parent": WORK_ORDER}, fields=["item_code", "required_qty"])
    if len([row for row in work_order_items if row.item_code == NEW and abs(flt(row.required_qty) - 20) < 0.000001]) != 1:
        frappe.throw("OF-02883 material row changed.")


def execute():
    """Correct OF-02883 inputs and clear its 20 Nos of 520006 without restoring 520000 stock."""
    if frappe.local.site != "site1.local":
        return

    repack_name = _get_repack()
    reconciliation_name = _get_reconciliation()
    if repack_name or reconciliation_name:
        if not repack_name or not reconciliation_name:
            frappe.throw("OF-02883 correction is only partially present.")
        _assert_applied(repack_name, reconciliation_name)
        return

    _assert_entries(OLD)
    work_order = frappe.db.get_value(
        "Work Order", WORK_ORDER, ["production_item", "bom_no", "qty", "produced_qty", "docstatus"], as_dict=True
    )
    if (
        not work_order or work_order.production_item != NEW
        or work_order.bom_no != "BOM-320104-004" or work_order.docstatus != 1
    ):
        frappe.throw("OF-02883 changed; review before correcting stock.")
    _assert_close(work_order.qty, 20, "OF-02883 qty")
    _assert_close(work_order.produced_qty, 20, "OF-02883 produced_qty")
    work_order_row = frappe.db.get_value("Work Order Item", {"parent": WORK_ORDER, "item_code": OLD}, "name")
    if not work_order_row:
        frappe.throw("OF-02883 original 520000 material row is missing.")
    if frappe.db.get_value("Item", OLD, "stock_uom") != frappe.db.get_value("Item", NEW, "stock_uom"):
        frappe.throw("OF-02883 items have different stock units.")
    _assert_close(frappe.db.get_value("Bin", {"item_code": OLD, "warehouse": MAIN}, "actual_qty"), 145, "520000 Main Stock qty")
    _assert_close(frappe.db.get_value("Bin", {"item_code": NEW, "warehouse": MAIN}, "actual_qty"), 20, "520006 Main Stock qty")

    item = frappe.db.get_value("Item", NEW, ["item_name", "description"], as_dict=True)
    for name, unused_parent, unused_source, unused_target in DETAILS:
        frappe.db.set_value(
            "Stock Entry Detail", name,
            {"item_code": NEW, "item_name": item.item_name, "description": item.description},
            update_modified=False,
        )
    for name, unused_parent, unused_detail, unused_warehouse, unused_qty in LEDGER:
        frappe.db.set_value("Stock Ledger Entry", name, "item_code", NEW, update_modified=False)
    frappe.db.set_value(
        "Work Order Item", work_order_row,
        {"item_code": NEW, "item_name": item.item_name, "description": item.description},
        update_modified=False,
    )

    repack = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Repack", "purpose": "Repack",
        "company": COMPANY, "posting_date": "2026-02-27", "posting_time": "15:10:56",
        "set_posting_time": 1, "remarks": REPACK_REMARKS,
        "items": [
            {"item_code": OLD, "qty": 20, "s_warehouse": MAIN, "basic_rate": 51,
             "expense_account": ADJUSTMENT_ACCOUNT, "cost_center": "Automation - AMF21"},
            {"item_code": NEW, "qty": 20, "t_warehouse": MAIN, "basic_rate": 51,
             "expense_account": ADJUSTMENT_ACCOUNT, "cost_center": "Automation - AMF21"},
        ],
    })
    repack.insert(ignore_permissions=True)
    repack.submit()

    for item_code in (OLD, NEW):
        update_entries_after({
            "item_code": item_code, "warehouse": WIP,
            "posting_date": "2026-02-27", "posting_time": "15:10:57",
        })

    bin_values = frappe.db.get_value(
        "Bin", {"item_code": NEW, "warehouse": MAIN}, ["actual_qty", "valuation_rate", "stock_value"], as_dict=True
    )
    _assert_close(bin_values.actual_qty, 20, "520006 qty before stock removal")
    reconciliation = frappe.get_doc({
        "doctype": "Stock Reconciliation", "naming_series": "SR/", "company": COMPANY,
        "purpose": "Stock Reconciliation", "posting_date": nowdate(),
        "posting_time": nowtime(), "set_posting_time": 1,
        "expense_account": ADJUSTMENT_ACCOUNT, "cost_center": "General - AMF21",
        "items": [{"item_code": NEW, "warehouse": MAIN, "qty": 0,
                   "valuation_rate": bin_values.valuation_rate}],
    })
    reconciliation.insert(ignore_permissions=True)
    reconciliation.submit()
    reconciliation.add_comment("Info", RECONCILIATION_COMMENT)

    _assert_close(frappe.db.get_value("Bin", {"item_code": OLD, "warehouse": MAIN}, "actual_qty"), 145, "final 520000 Main Stock qty")
    _assert_close(frappe.db.get_value("Bin", {"item_code": NEW, "warehouse": MAIN}, "actual_qty"), 0, "final 520006 Main Stock qty")
    _assert_close(frappe.db.get_value("Bin", {"item_code": OLD, "warehouse": WIP}, "actual_qty"), 0, "final 520000 WIP qty")
    _assert_close(frappe.db.get_value("Bin", {"item_code": NEW, "warehouse": WIP}, "actual_qty"), 0, "final 520006 WIP qty")
    _assert_applied(repack.name, reconciliation.name)
