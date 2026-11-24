"""Approved CHF target for a calendar month, quarter or year."""

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document

from amf.amf.sales_analytics.definitions import COMPANY, HISTORY_START, day, number, shift_month


class SalesAnalyticsTarget(Document):
    def validate(self):
        start = day(self.from_date)
        finish = day(self.to_date)
        if self.company != COMPANY or self.metric not in ("revenue", "order_intake"):
            frappe.throw(_("Choose an available Sales Analytics measure and company."))
        if not start or not finish or start < HISTORY_START or start.day != 1:
            frappe.throw(_("Choose the start of a calendar month from 2022 onward."))
        endings = {shift_month(start, 1) - timedelta(days=1)}
        if start.month in (1, 4, 7, 10):
            endings.add(shift_month(start, 3) - timedelta(days=1))
        if start.month == 1:
            endings.add(shift_month(start, 12) - timedelta(days=1))
        if finish not in endings or number(self.target_amount) <= 0:
            frappe.throw(_("Enter a positive CHF target for a full calendar month, quarter or year."))

    def before_submit(self):
        if frappe.db.exists(self.doctype, {
            "company": self.company, "metric": self.metric, "from_date": self.from_date,
            "to_date": self.to_date, "docstatus": 1,
        }):
            frappe.throw(_("A submitted target already exists for that measure and period."))
        self.approved_by = frappe.session.user
