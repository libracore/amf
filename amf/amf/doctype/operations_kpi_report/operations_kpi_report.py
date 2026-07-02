# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from datetime import date

from frappe.utils import add_days, get_first_day, get_last_day, getdate, nowdate


class OperationsKPIReport(Document):
    def autoname(self):
        self.set_period_defaults()
        company_abbr = frappe.db.get_value("Company", self.company, "abbr") or "COMPANY"
        self.report_key = "OPR-{0}-{1}".format(
            self.get_period_label(),
            company_abbr,
        )

    def validate(self):
        self.set_period_defaults()
        if self.send_email and not self.email_recipients:
            frappe.throw(_("Email Recipients are required when Send by Email is enabled."))

    def set_period_defaults(self):
        if not self.company:
            self.company = frappe.defaults.get_global_default("company")
        if not self.period_type:
            self.period_type = "Monthly"
        if not self.report_mode:
            self.report_mode = "Single Period"

        if self.period_type == "Semester":
            reference = getdate(self.reporting_month or nowdate())
            self.reporting_year = int(self.reporting_year or reference.year)
            self.reporting_semester = (
                self.reporting_semester
                or ("H1" if reference.month <= 6 else "H2")
            )
            start_month = 1 if self.reporting_semester == "H1" else 7
            self.period_start = date(self.reporting_year, start_month, 1)
            semester_end = (
                date(self.reporting_year, 6, 30)
                if self.reporting_semester == "H1"
                else date(self.reporting_year, 12, 31)
            )
            if self.period_start > getdate(nowdate()):
                frappe.throw(_("A semester report cannot start in the future."))
            self.period_end = min(semester_end, getdate(nowdate()))
            self.reporting_month = self.period_start
        else:
            if not self.reporting_month:
                self.reporting_month = get_first_day(
                    add_days(get_first_day(nowdate()), -1)
                )
            reporting_month = getdate(self.reporting_month)
            self.reporting_month = get_first_day(reporting_month)
            self.period_start = get_first_day(reporting_month)
            self.period_end = get_last_day(reporting_month)
            self.reporting_year = None
            self.reporting_semester = None

        self.set_comparison_period_defaults()

        title = (
            _("Operations KPI Comparative Report - {0}")
            if self.report_mode == "Comparative"
            else _("Operations KPI Report - {0}")
        )
        self.report_title = title.format(self.get_period_label().replace("_vs_", " vs "))
        if not self.status:
            self.status = "Draft"
        if not self.source:
            self.source = "Manual"
        if self.generate_ai_insights is None:
            settings = frappe.get_single("Operations KPI Report Settings")
            self.generate_ai_insights = int(settings.enable_ai_insights)
        if self.status == "Draft":
            self.ai_status = (
                "Pending" if self.generate_ai_insights else "Disabled"
            )

    def set_comparison_period_defaults(self):
        if self.report_mode != "Comparative":
            self.comparison_month = None
            self.comparison_year = None
            self.comparison_semester = None
            self.comparison_period_start = None
            self.comparison_period_end = None
            return

        if self.period_type == "Semester":
            if not self.comparison_year or not self.comparison_semester:
                comparison_start = add_days(self.period_start, -1)
                self.comparison_year = comparison_start.year
                self.comparison_semester = (
                    "H1" if comparison_start.month <= 6 else "H2"
                )
            start_month = 1 if self.comparison_semester == "H1" else 7
            self.comparison_period_start = date(
                int(self.comparison_year),
                start_month,
                1,
            )
            self.comparison_period_end = (
                date(int(self.comparison_year), 6, 30)
                if self.comparison_semester == "H1"
                else date(int(self.comparison_year), 12, 31)
            )
            self.comparison_month = self.comparison_period_start
        else:
            if not self.comparison_month:
                self.comparison_month = get_first_day(add_days(self.period_start, -1))
            comparison_month = getdate(self.comparison_month)
            self.comparison_month = get_first_day(comparison_month)
            self.comparison_period_start = self.comparison_month
            self.comparison_period_end = get_last_day(comparison_month)
            self.comparison_year = None
            self.comparison_semester = None

        if self.comparison_period_start > getdate(nowdate()):
            frappe.throw(_("A comparison period cannot start in the future."))
        if getdate(self.comparison_period_start) == getdate(self.period_start):
            frappe.throw(_("The comparison period must differ from the primary period."))

    def get_period_label(self):
        label = self.get_primary_period_label()
        if self.report_mode == "Comparative":
            label = "{0}_vs_{1}".format(label, self.get_comparison_period_label())
        return label

    def get_primary_period_label(self):
        if self.period_type == "Semester":
            return "{0}-{1}".format(
                self.reporting_year,
                self.reporting_semester,
            )
        return getdate(self.reporting_month).strftime("%Y-%m")

    def get_comparison_period_label(self):
        if self.period_type == "Semester":
            return "{0}-{1}".format(
                self.comparison_year,
                self.comparison_semester,
            )
        return getdate(self.comparison_month).strftime("%Y-%m")


@frappe.whitelist()
def enqueue_generation(name, force=0):
    doc = frappe.get_doc("Operations KPI Report", name)
    doc.check_permission("write")

    if doc.status in ("Queued", "Generating") and not int(force):
        return {"name": doc.name, "status": doc.status}

    doc.db_set("source", "Manual", update_modified=False)
    doc.db_set("status", "Queued", update_modified=True)
    frappe.enqueue(
        "amf.amf.utils.monthly_operations_report.generate_report",
        queue="long",
        timeout=15000,
        report_name=doc.name,
        force=bool(int(force)),
    )
    return {"name": doc.name, "status": "Queued"}


@frappe.whitelist()
def send_report_email(name):
    doc = frappe.get_doc("Operations KPI Report", name)
    doc.check_permission("email")
    from amf.amf.utils.monthly_operations_report import email_report

    return email_report(doc.name, force=True)


@frappe.whitelist()
def approve_ai_insights(name):
    doc = frappe.get_doc("Operations KPI Report", name)
    doc.check_permission("write")
    if not doc.ai_insights_json:
        frappe.throw(_("No validated AI insights are available for approval."))
    if doc.ai_status not in ("Approval Required", "Rejected"):
        frappe.throw(
            _("AI insights can only be approved from Approval Required or Rejected status.")
        )

    frappe.db.set_value(
        "Operations KPI Report",
        doc.name,
        {
            "ai_status": "Approved",
            "ai_approved": 1,
            "ai_approved_by": frappe.session.user,
            "ai_approved_on": frappe.utils.now_datetime(),
            "ai_rejection_reason": "",
        },
        update_modified=True,
    )
    from amf.amf.utils.monthly_operations_report import rebuild_report_outputs

    return rebuild_report_outputs(
        doc.name,
        include_ai=True,
        send_email_after=bool(doc.send_email),
    )


@frappe.whitelist()
def reject_ai_insights(name, reason):
    doc = frappe.get_doc("Operations KPI Report", name)
    doc.check_permission("write")
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("A rejection reason is required."))
    if doc.ai_status not in ("Approval Required", "Approved"):
        frappe.throw(
            _("AI insights can only be rejected from Approval Required or Approved status.")
        )

    frappe.db.set_value(
        "Operations KPI Report",
        doc.name,
        {
            "ai_status": "Rejected",
            "ai_approved": 0,
            "ai_approved_by": None,
            "ai_approved_on": None,
            "ai_rejection_reason": reason,
        },
        update_modified=True,
    )
    from amf.amf.utils.monthly_operations_report import rebuild_report_outputs

    return rebuild_report_outputs(
        doc.name,
        include_ai=False,
        send_email_after=bool(doc.send_email),
    )
