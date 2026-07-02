# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe.model.meta import get_field_precision
from frappe.utils import cint, flt


PATCHED_FLAG = "_amf_plain_return_lcv_gl_override"
ORIGINAL_METHOD = "_amf_original_get_gl_entries"


def install_purchase_receipt_gl_override(doc=None, method=None):
    """
    Keep AMF-specific Purchase Receipt return accounting outside ERPNext core.

    ERPNext v12 posts return divisional-loss adjustments to the company's
    Expenses Included In Valuation account. For AMF, a plain purchase receipt
    return without any Landed Cost Voucher or valuation tax must not touch the
    landed freight adjustment account.
    """
    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt

    if getattr(PurchaseReceipt, PATCHED_FLAG, False):
        return

    setattr(PurchaseReceipt, ORIGINAL_METHOD, PurchaseReceipt.get_gl_entries)
    PurchaseReceipt.get_gl_entries = _get_gl_entries_with_amf_plain_return_guard
    setattr(PurchaseReceipt, PATCHED_FLAG, True)


def _get_gl_entries_with_amf_plain_return_guard(self, warehouse_account=None):
    original_get_gl_entries = getattr(self.__class__, ORIGINAL_METHOD)
    gl_entries = original_get_gl_entries(self, warehouse_account)

    if not cint(self.get("is_return")):
        return gl_entries

    if not _has_valuation_charges(self):
        gl_entries = _move_valuation_expense_entries_to_rbnb(self, gl_entries)

    return _without_zero_value_gl_entries(self, gl_entries)


def _has_valuation_charges(doc):
    if _has_linked_landed_cost_voucher(doc):
        return True

    for row in doc.get("items"):
        if flt(row.get("landed_cost_voucher_amount")) or flt(row.get("item_tax_amount")):
            return True

    for tax in doc.get("taxes"):
        if (
            tax.get("category") in ("Valuation", "Valuation and Total")
            and flt(tax.get("base_tax_amount_after_discount_amount"))
        ):
            return True

    return False


def _has_linked_landed_cost_voucher(doc):
    receipt_names = [doc.name]
    if doc.get("return_against"):
        receipt_names.append(doc.return_against)

    return bool(frappe.db.sql(
        """
        select lcv.name
        from `tabLanded Cost Voucher` lcv
        inner join `tabLanded Cost Purchase Receipt` lcv_pr
            on lcv_pr.parent = lcv.name
        where lcv.docstatus = 1
            and lcv_pr.receipt_document_type = 'Purchase Receipt'
            and lcv_pr.receipt_document in %(receipt_names)s
        limit 1
        """,
        {"receipt_names": tuple(receipt_names)},
    ))


def _move_valuation_expense_entries_to_rbnb(doc, gl_entries):
    expenses_included_in_valuation = doc.get_company_default("expenses_included_in_valuation")
    stock_rbnb = doc.get_company_default("stock_received_but_not_billed")

    if not expenses_included_in_valuation or not stock_rbnb:
        return gl_entries

    moved_entries = False
    for entry in gl_entries:
        if entry.account == expenses_included_in_valuation:
            entry.account = stock_rbnb
            moved_entries = True

    if not moved_entries:
        return gl_entries

    from erpnext.accounts.general_ledger import process_gl_map
    return process_gl_map(gl_entries)


def _without_zero_value_gl_entries(doc, gl_entries):
    precision = get_field_precision(
        frappe.get_meta("GL Entry").get_field("debit"),
        currency=frappe.get_cached_value("Company", doc.company, "default_currency"),
    )

    return [
        entry for entry in gl_entries
        if flt(entry.debit, precision) or flt(entry.credit, precision)
    ]
