# Copyright (c) 2013, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    """
    Returns two values:
      1) columns: list of dicts defining your report columns
      2) data: list of rows (each a dict matching fieldnames in columns)
    """
    filters = filters or {}
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    # validation
    if not from_date or not to_date:
        frappe.throw(_("Please select both From Date and To Date"))
    if from_date > to_date:
        frappe.throw(_("From Date cannot be greater than To Date"))

    # fetch the average of amf_overall in the given date range
    sql = """
        SELECT
            AVG(amf_overall) AS global_average
        FROM `tabCustomer Satisfaction Survey`
        WHERE DATE(creation) BETWEEN %(from_date)s AND %(to_date)s
            AND docstatus = 1
    """
    result = frappe.db.sql(sql, {"from_date": from_date, "to_date": to_date}, as_dict=True)

    avg_value = flt(result[0].global_average*20 or 0, 2)

    # define columns
    columns = [
        {
            "fieldname": "global_average",
            "label": _("Global CSAT %"),
            "fieldtype": "Float",
            "width": 200
        }
    ]

    # single‐row result
    data = [
        {"global_average": avg_value}
    ]

    return columns, data
