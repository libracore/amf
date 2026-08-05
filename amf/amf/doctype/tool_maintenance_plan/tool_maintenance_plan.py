# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from amf.amf.utils.tool_maintenance import (
	sync_item_maintenance_summary,
	validate_tool_item,
)


class ToolMaintenancePlan(Document):
	def validate(self):
		self._previous_item_code = None
		self._schedule_changed = False
		if not self.is_new():
			previous = frappe.db.get_value(
				self.doctype,
				self.name,
				["item_code", "frequency_value", "frequency_unit"],
				as_dict=True,
			)
			if previous:
				self._previous_item_code = previous.item_code
				self._schedule_changed = (
					cint(previous.frequency_value) != cint(self.frequency_value)
					or previous.frequency_unit != self.frequency_unit
				)

		item = validate_tool_item(self.item_code)
		self.item_name = item.item_name
		self.status = self.status or "Active"
		self.warning_days = max(cint(self.warning_days), 0)

		if cint(self.frequency_value) < 0:
			frappe.throw(_("Frequency must not be negative."))
		if cint(self.frequency_value) and not self.frequency_unit:
			frappe.throw(_("Select a Frequency Unit when a Frequency is set."))
		if self.frequency_unit and not cint(self.frequency_value):
			frappe.throw(_("Set a Frequency greater than zero or clear the Frequency Unit."))
		if (
			self._previous_item_code
			and self._previous_item_code != self.item_code
			and frappe.db.exists("Tool Maintenance Log", {"maintenance_plan": self.name})
		):
			frappe.throw(_("A Maintenance Plan with intervention logs cannot be moved to another Item."))
		if self.status != "Closed" and cint(self.get("closed_on_completion")):
			self.closed_on_completion = 0

	def on_update(self):
		if self._schedule_changed and frappe.db.exists(
			"Tool Maintenance Log", {"maintenance_plan": self.name}
		):
			from amf.amf.utils.tool_maintenance import rebuild_plan_completion

			updates = rebuild_plan_completion(self.name) or {}
			for fieldname, value in updates.items():
				self.set(fieldname, value)
		else:
			sync_item_maintenance_summary(self.item_code)
		if self._previous_item_code and self._previous_item_code != self.item_code:
			sync_item_maintenance_summary(self._previous_item_code)

	def after_delete(self):
		sync_item_maintenance_summary(self.item_code)
