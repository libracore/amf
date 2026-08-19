# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import timedelta

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class WeeklyOperationsReport(Document):
    def autoname(self):
        self.set_report_defaults()

    def validate(self):
        self.set_report_defaults()

    def set_report_defaults(self):
        if not self.company:
            self.company = frappe.defaults.get_global_default("company")
        if not self.report_date:
            self.report_date = nowdate()
        report_date = getdate(self.report_date)
        iso_year, iso_week, iso_weekday = report_date.isocalendar()
        company_abbr = frappe.db.get_value("Company", self.company, "abbr") or "COMPANY"
        self.week_number = iso_week
        self.week_start = report_date - timedelta(days=iso_weekday - 1)
        self.report_key = "OPS-WEEKLY-{0}-W{1:02d}-{2}".format(
            iso_year, iso_week, company_abbr
        )
        self.report_title = "OPS Weekly — Production & Supply — {0}-W{1:02d}".format(
            iso_year, iso_week
        )
        if not self.status:
            self.status = "Draft"
        if not self.source:
            self.source = "Manual"
        if not self.owner_initials:
            self.owner_initials = "ATR"


@frappe.whitelist()
def generate_report(name, force=1):
    report = frappe.get_doc("Weekly Operations Report", name)
    report.check_permission("write")
    from amf.amf.utils.weekly_operations_report import generate_weekly_report

    return generate_weekly_report(report.name, force=force)


@frappe.whitelist()
def send_report_email(name, force=0):
    report = frappe.get_doc("Weekly Operations Report", name)
    report.check_permission("read")
    from amf.amf.utils.weekly_operations_report import email_weekly_report

    return email_weekly_report(report.name, force=force)

