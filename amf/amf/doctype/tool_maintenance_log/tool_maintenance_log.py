# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from amf.amf.utils.tool_maintenance import (
	rebuild_plan_completion,
	sync_item_maintenance_summary,
	validate_tool_item,
)


class ToolMaintenanceLog(Document):
	def validate(self):
		self._previous_item_code = None
		self._previous_plan = None
		if not self.is_new():
			previous = frappe.db.get_value(
				self.doctype,
				self.name,
				["item_code", "maintenance_plan"],
				as_dict=True,
			)
			if previous:
				self._previous_item_code = previous.item_code
				self._previous_plan = previous.maintenance_plan

		item = validate_tool_item(self.item_code)
		self.item_name = item.item_name

		if self.next_due_date and getdate(self.next_due_date) < getdate(self.intervention_date):
			frappe.throw(_("Next Due Date cannot be before the Intervention Date."))

		if self.maintenance_plan:
			plan = frappe.db.get_value(
				"Tool Maintenance Plan",
				self.maintenance_plan,
				["item_code", "maintenance_type", "activity", "responsible"],
				as_dict=True,
			)
			if not plan:
				frappe.throw(_("Maintenance Plan {0} does not exist.").format(self.maintenance_plan))
			if plan.item_code != self.item_code:
				frappe.throw(_("The Maintenance Plan must belong to Item {0}.").format(self.item_code))
			self.intervention_type = self.intervention_type or plan.maintenance_type
			self.intervention = self.intervention or plan.activity
			self.responsible = self.responsible or plan.responsible

	def on_update(self):
		if self.maintenance_plan:
			rebuild_plan_completion(self.maintenance_plan)
		if self._previous_plan and self._previous_plan != self.maintenance_plan:
			rebuild_plan_completion(self._previous_plan)
		sync_item_maintenance_summary(self.item_code)
		if self._previous_item_code and self._previous_item_code != self.item_code:
			sync_item_maintenance_summary(self._previous_item_code)

	def on_trash(self):
		if not self.maintenance_plan:
			return
		last_log = frappe.db.get_value(
			"Tool Maintenance Plan", self.maintenance_plan, "last_log"
		)
		if last_log == self.name:
			frappe.db.set_value(
				"Tool Maintenance Plan",
				self.maintenance_plan,
				"last_log",
				None,
				update_modified=False,
			)

	def after_delete(self):
		if self.maintenance_plan:
			rebuild_plan_completion(self.maintenance_plan)
		sync_item_maintenance_summary(self.item_code)
