# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, nowdate


CHANGE_TYPE_FIELDS = (
	"change_type_organization",
	"change_type_process",
	"change_type_manufacturing",
	"change_type_supplier",
	"change_type_erp_it",
	"change_type_documentation",
	"change_type_other",
)

IMPACT_FIELDS = (
	"impact_product_quality",
	"impact_customer_regulatory",
	"impact_production_capacity",
	"impact_organization_skills",
	"impact_suppliers",
	"impact_equipment_measurement",
	"impact_erp_traceability",
	"impact_qms_documents",
)

APPROVAL_DECISIONS = ("Approved", "Approved with Conditions", "Rejected")


class OrganizationalModificationRequest(Document):
	def before_insert(self):
		if not self.requester and frappe.session.user not in ("Guest", None):
			self.requester = frappe.session.user

	def validate(self):
		self._set_user_names()
		self._validate_request_dates()
		self._validate_change_scope()
		self._validate_impact_scope()
		self._validate_conditional_details()
		self._validate_actions()
		self._validate_implementation_and_closure()
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		self._validate_approval()
		self.status = self._get_status()

	def on_submit(self):
		self._sync_status()

	def before_update_after_submit(self):
		if self.closure_quality_reviewer:
			self.closure_quality_reviewer_name = self._get_user_full_name(
				self.closure_quality_reviewer
			)
		self._validate_request_dates()
		self._validate_conditional_details()
		self._validate_actions()
		self._validate_implementation_and_closure()
		self.status = self._get_status()

	def on_update_after_submit(self):
		self._sync_status()

	def on_cancel(self):
		self.status = "Cancelled"
		self.db_set("status", self.status, update_modified=False)

	def before_print(self):
		"""Expose stable display names to the Jinja print format."""
		if self.requester and not self.requester_name:
			self.requester_name = self._get_user_full_name(self.requester)
		if self.closure_quality_reviewer and not self.closure_quality_reviewer_name:
			self.closure_quality_reviewer_name = self._get_user_full_name(
				self.closure_quality_reviewer
			)
		for row in self.get("actions") or []:
			if row.responsible and not row.responsible_name:
				row.responsible_name = self._get_user_full_name(row.responsible)

	def _set_user_names(self):
		if self.requester:
			self.requester_name = self._get_user_full_name(self.requester)
		if self.closure_quality_reviewer:
			self.closure_quality_reviewer_name = self._get_user_full_name(
				self.closure_quality_reviewer
			)
		for row in self.get("actions") or []:
			if row.responsible:
				row.responsible_name = self._get_user_full_name(row.responsible)

	def _validate_request_dates(self):
		if (
			self.request_date
			and self.planned_implementation_date
			and getdate(self.planned_implementation_date) < getdate(self.request_date)
		):
			frappe.throw(
				_("Planned implementation date cannot be before the request date.")
			)

	def _validate_change_scope(self):
		if not any(cint(self.get(fieldname)) for fieldname in CHANGE_TYPE_FIELDS):
			frappe.throw(_("Select at least one change type."))
		if self.change_type_other and not (self.change_type_other_detail or "").strip():
			frappe.throw(_("Specify the other change type."))

	def _validate_impact_scope(self):
		if not any(cint(self.get(fieldname)) for fieldname in IMPACT_FIELDS):
			frappe.throw(_("Select at least one potentially impacted domain."))

	def _validate_conditional_details(self):
		if (
			self.training_documentation_required == "Yes"
			and not (self.training_documentation_details or "").strip()
		):
			frappe.throw(
				_("Describe the required training or documentation update.")
			)
		if (
			self.effectiveness_review_period == "Other"
			and not (self.effectiveness_review_period_other or "").strip()
		):
			frappe.throw(_("Specify the other effectiveness review period."))
		if (
			self.decision == "Approved with Conditions"
			and not (self.decision_conditions or "").strip()
		):
			frappe.throw(_("Approval conditions are required for a conditional approval."))

	def _validate_actions(self):
		for row in self.get("actions") or []:
			if (
				row.due_date
				and self.planned_implementation_date
				and getdate(row.due_date) > getdate(self.planned_implementation_date)
			):
				frappe.throw(
					_("Row {0}: action due date must be on or before the planned implementation date.")
					.format(row.idx)
				)
			if cint(row.completed) and not row.completion_date:
				row.completion_date = nowdate()

	def _validate_approval(self):
		if self.decision not in APPROVAL_DECISIONS:
			frappe.throw(_("An approval decision is required before submission."))

		if self.decision != "Rejected":
			if not self.effectiveness_review_period:
				frappe.throw(_("Select the planned effectiveness review period."))
			if not self.get("actions"):
				frappe.throw(_("At least one implementation action is required for approval."))

		required_fields = (
			("change_responsible_name_function", _("Responsible for change: name / function")),
			("change_responsible_approval_date", _("Responsible for change: date")),
			("change_responsible_signature", _("Responsible for change: visa")),
			("quality_name_function", _("Quality: name / function")),
			("quality_approval_date", _("Quality: date")),
			("quality_signature", _("Quality: visa")),
		)
		if self.change_level == "C3 - Major":
			required_fields += (
				("management_name_function", _("General Management: name / function")),
				("management_approval_date", _("General Management: date")),
				("management_signature", _("General Management: visa")),
			)

		missing = [label for fieldname, label in required_fields if not self.get(fieldname)]
		if missing:
			frappe.throw(
				_("Complete the approval fields before submission: {0}").format(
					", ".join(missing)
				)
			)

	def _validate_implementation_and_closure(self):
		if self.actual_implementation_date:
			if self.decision == "Rejected":
				frappe.throw(_("A rejected modification request cannot be implemented."))
			if self.request_date and getdate(self.actual_implementation_date) < getdate(
				self.request_date
			):
				frappe.throw(
					_("Actual implementation date cannot be before the request date.")
				)
			incomplete_actions = [row.idx for row in self.get("actions") or [] if not row.completed]
			if incomplete_actions:
				frappe.throw(
					_("Complete all implementation actions before recording the actual implementation date. Incomplete rows: {0}")
					.format(", ".join(str(idx) for idx in incomplete_actions))
				)

		closure_started = any(
			self.get(fieldname)
			for fieldname in (
				"effectiveness_review_result",
				"change_effective",
				"additional_actions",
				"follow_up_issue",
				"closure_quality_reviewer",
				"closure_date",
				"closure_quality_signature",
			)
		)
		if not closure_started:
			return
		if not self.actual_implementation_date:
			frappe.throw(_("Record the actual implementation date before starting closure."))

		if self.change_effective == "No" and not (self.additional_actions or "").strip():
			frappe.throw(_("Define additional actions when the change is not effective."))

		closure_completed = bool(self.closure_quality_signature or self.closure_date)
		if closure_completed:
			required_fields = (
				("effectiveness_review_result", _("Effectiveness review result")),
				("change_effective", _("Effective and controlled decision")),
				("closure_quality_reviewer", _("Closure Quality reviewer")),
				("closure_date", _("Closure date")),
				("closure_quality_signature", _("Closure Quality visa")),
			)
			missing = [label for fieldname, label in required_fields if not self.get(fieldname)]
			if missing:
				frappe.throw(
					_("Complete the closure fields: {0}").format(", ".join(missing))
				)
			if getdate(self.closure_date) < getdate(self.actual_implementation_date):
				frappe.throw(
					_("Closure date cannot be before the actual implementation date.")
				)

	def _get_status(self):
		if self.docstatus == 2:
			return "Cancelled"
		if self.decision == "Rejected":
			return "Rejected"
		if self.closure_quality_signature and self.closure_date:
			return "Closed"
		if self.actual_implementation_date:
			return "Effectiveness Review"
		if self.decision == "Approved with Conditions":
			return "Approved with Conditions"
		if self.decision == "Approved":
			return "Approved"
		return "Draft"

	def _sync_status(self):
		status = self._get_status()
		self.status = status
		if not self.is_new():
			self.db_set("status", status, update_modified=False)

	@staticmethod
	def _get_user_full_name(user):
		return frappe.db.get_value("User", user, "full_name") or user
