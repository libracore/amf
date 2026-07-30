# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from erpnext.controllers.trends import get_columns, get_data

from amf.amf.utils.sales_invoice_total_ht import TOTAL_HT_FIELD, TOTAL_HT_LABEL


# Sales Invoice Trends joins one invoice to all of its item rows. Allocate the
# invoice-level Total HT proportionally so shipping/card charges are counted once
# in customer, territory, project, and item groupings.
TOTAL_HT_ITEM_AMOUNT_SQL = """
CASE
    WHEN ABS(IFNULL(t1.base_total, 0)) > 0.000001
    THEN (
        IFNULL(t2.base_amount, 0)
        * IFNULL(t1.{total_ht_field}, t1.base_total)
        / t1.base_total
    )
    ELSE 0
END
""".format(total_ht_field=TOTAL_HT_FIELD).strip()

CUSTOMER_DISPLAY_FIELD = "_customer_display_name"
CUSTOMER_DISPLAY_COLUMN = {
    "label": "Customer Name",
    "fieldname": CUSTOMER_DISPLAY_FIELD,
    "fieldtype": "Data",
    "hidden": 1,
}


def apply_total_ht_to_conditions(conditions):
    """Replace the standard item amount measure with allocated Total HT."""
    conditions["period_wise_select"] = conditions["period_wise_select"].replace(
        "t2.base_net_amount",
        TOTAL_HT_ITEM_AMOUNT_SQL,
    )
    conditions["columns"][-1] = _(
        TOTAL_HT_LABEL
    ) + ":Currency:190"
    return conditions


def apply_customer_link_to_conditions(filters, conditions):
    """Use the Customer document name as the Link value, not its display title."""
    if filters.get("based_on") != "Customer":
        return conditions

    conditions["based_on_select"] = conditions["based_on_select"].replace(
        "t1.customer_name,",
        "t1.customer,",
    )
    return conditions


def add_customer_display_names(columns, data, customer_names):
    """Keep the organization title visible while the link value remains its ID."""
    columns.insert(1, CUSTOMER_DISPLAY_COLUMN.copy())
    for row in data:
        customer = row[0]
        row.insert(1, customer_names.get(customer, customer))
    return columns, data


def get_customer_names(data):
    customer_ids = tuple(sorted({row[0] for row in data if row and row[0]}))
    if not customer_ids:
        return {}

    return {
        customer.name: customer.customer_name
        for customer in frappe.get_all(
            "Customer",
            filters={"name": ["in", customer_ids]},
            fields=["name", "customer_name"],
        )
    }


def execute(filters=None):
    filters = filters or {}
    conditions = get_columns(filters, "Sales Invoice")
    apply_total_ht_to_conditions(conditions)
    apply_customer_link_to_conditions(filters, conditions)
    data = get_data(filters, conditions)
    if filters.get("based_on") == "Customer":
        add_customer_display_names(
            conditions["columns"],
            data,
            get_customer_names(data),
        )
    return conditions["columns"], data
