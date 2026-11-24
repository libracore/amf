"""Approved expected billing for a specific Sales Order row."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, nowdate

from amf.amf.sales_analytics.definitions import COMPANY, COMMERCIAL_ORDER_TYPES, CLOSED_ORDER_STATUSES, number


class SalesAnalyticsBilling(Document):
    def validate(self):
        if self.company != COMPANY:
            frappe.throw(_("Choose the company configured for Sales Analytics."))
        order = frappe.get_doc("Sales Order", self.sales_order)
        order.check_permission("read")
        if (order.company != self.company or order.docstatus != 1
                or order.sales_order_type not in COMMERCIAL_ORDER_TYPES or order.status in CLOSED_ORDER_STATUSES):
            frappe.throw(_("Choose a submitted, open commercial Sales Order."))
        line = next((row for row in order.items if row.idx == cint(self.line_number)), None)
        if line is None:
            frappe.throw(_("Select an existing order item row number."))
        if not 0 < number(self.quantity) <= number(line.qty):
            frappe.throw(_("Billing quantity must be positive and within the ordered quantity."))
        if getdate(self.billing_date) < getdate(nowdate()):
            frappe.throw(_("Choose today or a later billing date."))
        self.order_item = line.name
        self.item_code = line.item_code

    def before_submit(self):
        self.approved_by = frappe.session.user
