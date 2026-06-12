# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import getdate


CUSTOMER_DOCTYPE = "Customer"

TYPOLOGY_OPTIONS = "\nNew client\nRecurring\nBlanket\nDistributor"
SOURCE_OPTIONS = "\nBlanket\nDigital\nDistributor\nEvent\nNetwork\nOther\nProspection\nVector"
PRODUCT_FAMILY_OPTIONS = "\nSPM\nRVM\nCustom\nSpare Part"

COMPUTED_FIELDS = (
    "amf_history_date",
    "amf_history_class",
    "sales",
    "first_purchase",
    "qr_new_client",
    "first_qr",
)

CUSTOMER_MARKETING_CUSTOM_FIELDS = {
    CUSTOMER_DOCTYPE: [
        {
            "fieldname": "marketing_options_section",
            "fieldtype": "Section Break",
            "label": "Marketing Options",
            "insert_after": "expected_sales_volume",
            "collapsible": 1,
        },
        {
            "fieldname": "typology",
            "fieldtype": "Select",
            "label": "Typology",
            "options": TYPOLOGY_OPTIONS,
            "insert_after": "marketing_options_section",
            "in_standard_filter": 1,
        },
        {
            "fieldname": "source",
            "fieldtype": "Select",
            "label": "Source",
            "options": SOURCE_OPTIONS,
            "insert_after": "typology",
            "in_standard_filter": 1,
        },
        {
            "fieldname": "from_source",
            "fieldtype": "Data",
            "label": "From Source",
            "insert_after": "source",
            "depends_on": "eval:doc.source",
            "description": "Free text source detail.",
        },
        {
            "fieldname": "request_date",
            "fieldtype": "Date",
            "label": "Request Date",
            "insert_after": "from_source",
            "in_standard_filter": 1,
            "description": "Date used for month, quarter, and year reporting.",
        },
        {
            "fieldname": "request_type",
            "fieldtype": "Data",
            "label": "Request Type",
            "insert_after": "request_date",
        },
        {
            "fieldname": "marketing_options_column_break",
            "fieldtype": "Column Break",
            "insert_after": "request_type",
        },
        {
            "fieldname": "product_family",
            "fieldtype": "Select",
            "label": "Product Family",
            "options": PRODUCT_FAMILY_OPTIONS,
            "insert_after": "marketing_options_column_break",
            "in_standard_filter": 1,
        },
        {
            "fieldname": "sales",
            "fieldtype": "Check",
            "label": "Sales",
            "insert_after": "product_family",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "description": "Yes when the customer has at least one submitted Sales Order.",
        },
        {
            "fieldname": "first_purchase",
            "fieldtype": "Check",
            "label": "First Purchase",
            "insert_after": "sales",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "description": "Yes once the customer's first submitted Sales Order exists.",
        },
        {
            "fieldname": "qr_new_client",
            "fieldtype": "Check",
            "label": "QR New Client",
            "insert_after": "first_purchase",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "description": "Yes when Source is Digital.",
        },
        {
            "fieldname": "first_qr",
            "fieldtype": "Check",
            "label": "First QR",
            "insert_after": "qr_new_client",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "description": "Yes when the customer's first submitted Sales Order exists and Source is Digital.",
        },
        {
            "fieldname": "amf_history_date",
            "fieldtype": "Date",
            "label": "AMF History Date",
            "insert_after": "first_qr",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "description": "First submitted Sales Order date.",
        },
        {
            "fieldname": "amf_history_class",
            "fieldtype": "Data",
            "label": "AMF History Class",
            "insert_after": "amf_history_date",
            "read_only": 1,
            "no_copy": 1,
            "in_standard_filter": 1,
            "description": "Customer class based on the year of the first submitted Sales Order.",
        },
    ]
}


def sync_customer_marketing_custom_fields():
    """Install Customer marketing fields and refresh their derived values."""
    create_custom_fields(CUSTOMER_MARKETING_CUSTOM_FIELDS, update=True)
    frappe.clear_cache(doctype=CUSTOMER_DOCTYPE)
    return sync_all_customer_marketing_values()


def apply_customer_marketing_values(doc, method=None):
    """Keep derived marketing flags current when a Customer is saved."""
    if not _has_computed_columns():
        return

    values = get_customer_marketing_values(doc.name, source=doc.get("source"))
    for fieldname, value in values.items():
        doc.set(fieldname, value)


def sync_customer_marketing_from_sales_order(doc, method=None):
    """Refresh Customer marketing history when a Sales Order changes state."""
    customer = doc.get("customer")
    if not customer or not frappe.db.exists(CUSTOMER_DOCTYPE, customer):
        return

    sync_customer_marketing_values(customer)


@frappe.whitelist()
def sync_customer_marketing_values(customer):
    """Backfill the computed Customer marketing values for one Customer."""
    if not _has_computed_columns() or not frappe.db.exists(CUSTOMER_DOCTYPE, customer):
        return {"updated": 0, "skipped": "missing_customer_or_columns"}

    source = frappe.db.get_value(CUSTOMER_DOCTYPE, customer, "source")
    values = get_customer_marketing_values(customer, source=source)
    current_values = frappe.db.get_value(
        CUSTOMER_DOCTYPE,
        customer,
        list(values.keys()),
        as_dict=True,
    )

    updates = {
        fieldname: value
        for fieldname, value in values.items()
        if current_values.get(fieldname) != value
    }
    if not updates:
        return {"updated": 0}

    frappe.db.set_value(
        CUSTOMER_DOCTYPE,
        customer,
        updates,
        update_modified=False,
    )
    return {"updated": 1}


@frappe.whitelist()
def sync_all_customer_marketing_values():
    """Backfill computed marketing values for all Customers."""
    if not _has_computed_columns():
        return {"updated": 0, "skipped": "missing_columns"}

    order_summary_by_customer = get_sales_order_summary_by_customer()
    updated = 0
    customer_fields = ["name", "source"] + list(COMPUTED_FIELDS)

    for customer in frappe.get_all(CUSTOMER_DOCTYPE, fields=customer_fields):
        values = get_customer_marketing_values(
            customer.name,
            source=customer.get("source"),
            order_summary=order_summary_by_customer.get(customer.name),
        )
        updates = {
            fieldname: value
            for fieldname, value in values.items()
            if customer.get(fieldname) != value
        }
        if not updates:
            continue

        frappe.db.set_value(
            CUSTOMER_DOCTYPE,
            customer.name,
            updates,
            update_modified=False,
        )
        updated += 1

    return {"updated": updated}


def get_customer_marketing_values(customer, source=None, order_summary=None):
    if order_summary is None:
        order_summary = get_sales_order_summary(customer)

    first_order_date = order_summary.get("first_order_date")
    has_sales = 1 if order_summary.get("submitted_order_count") else 0
    is_digital_source = 1 if source == "Digital" else 0

    return {
        "amf_history_date": first_order_date,
        "amf_history_class": get_amf_history_class(first_order_date),
        "sales": has_sales,
        "first_purchase": has_sales,
        "qr_new_client": is_digital_source,
        "first_qr": 1 if has_sales and is_digital_source else 0,
    }


def get_sales_order_summary(customer):
    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS submitted_order_count,
            MIN(transaction_date) AS first_order_date
        FROM `tabSales Order`
        WHERE docstatus = 1
          AND customer = %s
        """,
        (customer,),
        as_dict=True,
    )
    return rows[0] if rows else {}


def get_sales_order_summary_by_customer():
    rows = frappe.db.sql(
        """
        SELECT
            customer,
            COUNT(*) AS submitted_order_count,
            MIN(transaction_date) AS first_order_date
        FROM `tabSales Order`
        WHERE docstatus = 1
          AND IFNULL(customer, '') != ''
        GROUP BY customer
        """,
        as_dict=True,
    )
    return {row.customer: row for row in rows}


def get_amf_history_class(first_order_date):
    if not first_order_date:
        return ""

    return "Customer {0}".format(getdate(first_order_date).year)


def _has_computed_columns():
    columns = set(frappe.db.get_table_columns(CUSTOMER_DOCTYPE))
    return all(fieldname in columns for fieldname in COMPUTED_FIELDS)
