# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr, flt


SALES_INVOICE_DOCTYPE = "Sales Invoice"
TOTAL_HT_FIELD = "total_ht_company_currency"
TOTAL_HT_LABEL = "Total HT (Company Currency)"
SALES_INVOICE_TRENDS_REPORT = "Sales Invoice Trends"
AMF_MODULE = "AMF"

# AMF's current and legacy non-tax invoice charge accounts.
TOTAL_HT_CHARGE_ACCOUNT_CODES = ("3410", "3495")
TOTAL_HT_CHARGE_KEYWORDS = (
    "shipping",
    "transport",
    "card processing",
    "card surcharge",
    "paypal",
)


SALES_INVOICE_TOTAL_HT_CUSTOM_FIELDS = {
    SALES_INVOICE_DOCTYPE: [
        {
            "fieldname": TOTAL_HT_FIELD,
            "fieldtype": "Currency",
            "label": TOTAL_HT_LABEL,
            "insert_after": "base_total",
            "options": "Company:company:default_currency",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "description": (
                "Product total plus shipping and card processing charges, "
                "excluding VAT, in company currency."
            ),
        }
    ]
}


def sync_sales_invoice_total_ht_customization():
    """Install the Total HT field, backfill it, and activate the AMF trends report."""
    create_custom_fields(SALES_INVOICE_TOTAL_HT_CUSTOM_FIELDS, update=True)
    frappe.clear_cache(doctype=SALES_INVOICE_DOCTYPE)

    updated = sync_all_sales_invoice_total_ht()
    report_updated = route_sales_invoice_trends_report_to_amf()
    return {"invoices_updated": updated, "report_updated": report_updated}


def is_total_ht_charge(tax_row):
    """Return whether a tax-table row is shipping or card processing."""
    account_head = cstr(tax_row.get("account_head")).strip()
    account_code = account_head.split(" ", 1)[0]
    if account_code in TOTAL_HT_CHARGE_ACCOUNT_CODES:
        return True

    searchable_text = " ".join(
        (
            account_head,
            cstr(tax_row.get("description")),
        )
    ).lower()
    return any(keyword in searchable_text for keyword in TOTAL_HT_CHARGE_KEYWORDS)


def get_sales_invoice_total_ht(base_total=0, taxes=None):
    """Calculate product + shipping + card processing in company currency."""
    total_ht = flt(base_total)
    for tax_row in taxes or []:
        if not is_total_ht_charge(tax_row):
            continue

        amount = tax_row.get("base_tax_amount_after_discount_amount")
        if amount is None:
            amount = tax_row.get("base_tax_amount")
        total_ht += flt(amount)

    return round(flt(total_ht), 6)


def apply_sales_invoice_total_ht(doc, method=None):
    """Set Total HT after ERPNext has calculated the Sales Invoice totals."""
    if not doc.meta.get_field(TOTAL_HT_FIELD):
        return

    total_ht = get_sales_invoice_total_ht(
        base_total=doc.get("base_total"),
        taxes=doc.get("taxes"),
    )
    doc.set(TOTAL_HT_FIELD, flt(total_ht, doc.precision(TOTAL_HT_FIELD)))


@frappe.whitelist()
def sync_all_sales_invoice_total_ht():
    """Backfill Total HT on existing invoices without changing their timestamps."""
    if not frappe.db.has_column(SALES_INVOICE_DOCTYPE, TOTAL_HT_FIELD):
        return 0

    invoices = frappe.get_all(
        SALES_INVOICE_DOCTYPE,
        fields=["name", "base_total", TOTAL_HT_FIELD],
    )
    taxes_by_invoice = {}
    for tax_row in frappe.get_all(
        "Sales Taxes and Charges",
        filters={
            "parenttype": SALES_INVOICE_DOCTYPE,
            "parentfield": "taxes",
        },
        fields=[
            "parent",
            "account_head",
            "description",
            "base_tax_amount",
            "base_tax_amount_after_discount_amount",
        ],
    ):
        taxes_by_invoice.setdefault(tax_row.parent, []).append(tax_row)

    updated = 0
    for invoice in invoices:
        total_ht = get_sales_invoice_total_ht(
            base_total=invoice.base_total,
            taxes=taxes_by_invoice.get(invoice.name),
        )
        if (
            invoice.get(TOTAL_HT_FIELD) is not None
            and round(flt(invoice.get(TOTAL_HT_FIELD)), 6) == total_ht
        ):
            continue

        frappe.db.set_value(
            SALES_INVOICE_DOCTYPE,
            invoice.name,
            TOTAL_HT_FIELD,
            total_ht,
            update_modified=False,
        )
        updated += 1

    return updated


def route_sales_invoice_trends_report_to_amf():
    """Use the AMF implementation while retaining the standard report record."""
    if not frappe.db.exists("Report", SALES_INVOICE_TRENDS_REPORT):
        return False

    current_module = frappe.db.get_value(
        "Report",
        SALES_INVOICE_TRENDS_REPORT,
        "module",
    )
    if current_module == AMF_MODULE:
        return False

    frappe.db.set_value(
        "Report",
        SALES_INVOICE_TRENDS_REPORT,
        "module",
        AMF_MODULE,
        update_modified=False,
    )
    frappe.clear_cache(doctype="Report")
    return True
