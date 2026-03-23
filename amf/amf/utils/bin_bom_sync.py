from __future__ import unicode_literals

import frappe
from frappe.utils import flt, now

_BIN_UPDATE_STOCK_PATCHED = False


def install_update_stock_patch():
    """
    Patch ERPNext Bin.update_stock so normal stock movements also refresh
    Item.bom_table.stock_qty after the Bin quantity is finalized.
    """
    global _BIN_UPDATE_STOCK_PATCHED

    if _BIN_UPDATE_STOCK_PATCHED:
        return

    try:
        from erpnext.stock.doctype.bin.bin import Bin
    except ImportError:
        return

    original_update_stock = getattr(Bin, "update_stock", None)
    if not original_update_stock or getattr(original_update_stock, "_amf_bom_stock_qty_patched", False):
        _BIN_UPDATE_STOCK_PATCHED = True
        return

    def wrapped_update_stock(self, args, allow_negative_stock=False, via_landed_cost_voucher=False):
        result = original_update_stock(
            self,
            args,
            allow_negative_stock=allow_negative_stock,
            via_landed_cost_voucher=via_landed_cost_voucher,
        )

        try:
            sync_item_bom_stock_qty(self.item_code, self.warehouse)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "AMF BOM stock_qty sync failed after Bin.update_stock")

        return result

    wrapped_update_stock._amf_bom_stock_qty_patched = True
    Bin.update_stock = wrapped_update_stock
    _BIN_UPDATE_STOCK_PATCHED = True


def sync_item_bom_stock_qty_on_bin_update(doc, method=None):
    """
    Keep Item.bom_table.stock_qty aligned when Bin is saved directly.
    This covers flows like reposting where Bin.save() is used instead of update_stock().
    """
    if not doc or getattr(doc, "doctype", None) != "Bin":
        return

    sync_item_bom_stock_qty(doc.item_code, doc.warehouse, actual_qty=doc.actual_qty)


def sync_item_bom_stock_qty(item_code, warehouse, actual_qty=None):
    if not item_code or not warehouse:
        return 0

    if actual_qty is None:
        actual_qty = frappe.db.get_value(
            "Bin",
            {"item_code": item_code, "warehouse": warehouse},
            "actual_qty",
        )

    actual_qty = flt(actual_qty)
    timestamp = now()
    user = frappe.session.user if getattr(frappe.session, "user", None) else "Administrator"

    frappe.db.sql(
        """
        UPDATE `tabBOM Item Child`
        SET stock_qty = %s,
            modified = %s,
            modified_by = %s
        WHERE parenttype = 'Item'
          AND parentfield = 'bom_table'
          AND item_code = %s
          AND IFNULL(source_warehouse, '') = %s
        """,
        (actual_qty, timestamp, user, item_code, warehouse),
    )

    return actual_qty
