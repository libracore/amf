# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class OperationsKPIReportSettings(Document):
    def validate(self):
        self.update_api_key()
        if not self.company:
            self.company = frappe.defaults.get_global_default("company")
        if not self.generate_english and not self.generate_french:
            frappe.throw(_("Enable at least one report language."))
        if self.send_email and not self.email_recipients:
            frappe.throw(_("Email Recipients are required when automatic email is enabled."))
        if self.enable_ai_insights:
            from amf.amf.utils.openai_credentials import has_openai_api_key

            if not has_openai_api_key(self):
                frappe.throw(_("Configure an OpenAI API key before enabling AI Insights."))
            if not self.ai_model:
                frappe.throw(_("AI Model is required when AI Insights are enabled."))
            if not self.ai_prompt_version:
                frappe.throw(_("Prompt Version is required when AI Insights are enabled."))
            if not 0 <= flt(self.ai_minimum_confidence) <= 100:
                frappe.throw(_("Minimum Confidence must be between 0 and 100."))
            if not 1 <= cint(self.ai_max_insights) <= 15:
                frappe.throw(_("Maximum Insights must be between 1 and 15."))
            if not 15 <= cint(self.ai_timeout_seconds) <= 600:
                frappe.throw(_("API Timeout must be between 15 and 600 seconds."))

    def update_api_key(self):
        from amf.amf.utils.openai_credentials import (
            clear_openai_api_key,
            has_openai_api_key,
            store_openai_api_key,
        )

        if cint(self.clear_openai_api_key):
            clear_openai_api_key(self)
            self.clear_openai_api_key = 0
        elif (self.openai_api_key or "").strip():
            store_openai_api_key(self, self.openai_api_key)
        else:
            self.openai_api_key = ""
            self.openai_api_key_configured = int(has_openai_api_key(self))


@frappe.whitelist()
def generate_previous_month_now():
    frappe.only_for("System Manager")
    from amf.amf.utils.monthly_operations_report import generate_previous_month_report

    return generate_previous_month_report(force=True, source="Manual")


@frappe.whitelist()
def generate_previous_semester_now():
    frappe.only_for("System Manager")
    from amf.amf.utils.monthly_operations_report import (
        generate_previous_semester_report,
    )

    return generate_previous_semester_report(force=True, source="Manual")


@frappe.whitelist()
def generate_current_semester_now():
    frappe.only_for("System Manager")
    from amf.amf.utils.monthly_operations_report import (
        generate_current_semester_report,
    )

    return generate_current_semester_report(force=True, source="Manual")
