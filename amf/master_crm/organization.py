# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe import _

def update_global_csat():
    """
    Nightly job that:
      1. Aggregates each Customer’s mean CSAT across its Contacts in one go.
      2. Writes the result back to Customer.global_csat (NULL if no scores).
    """

    # 1. Compute per-customer averages
    rows = frappe.db.sql("""
        SELECT
            dl.link_name        AS customer,
            ROUND(AVG(c.customer_satisfaction_survey), 2)/20 AS avg_csat
        FROM `tabDynamic Link` dl
        JOIN `tabContact` c
          ON dl.parent = c.name
        WHERE dl.link_doctype = %s
          AND dl.parenttype  = %s
          AND c.customer_satisfaction_survey IS NOT NULL
        GROUP BY dl.link_name
    """, ("Customer", "Contact"), as_dict=True)

    # Build lookup: {customer_name: avg_csat}
    avg_map = {d["customer"]: d["avg_csat"] for d in rows}
    # 2. Fetch all customers
    all_customers = frappe.get_all("Customer", fields=["name"])

    # 3. Update each one (NULL for those not in avg_map)
    for cust in all_customers:
        cust_name = cust["name"]
        frappe.db.set_value(
            "Customer",
            cust_name,
            "global_csat",
            avg_map.get(cust_name),        # None if missing → clears the field
            update_modified=False
        )

    # 4. Commit & log
    frappe.db.commit()
    frappe.logger().info("Global CSAT scores updated for %d customers", len(all_customers))
