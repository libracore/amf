# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest
from datetime import date, datetime
from uuid import uuid4
from unittest.mock import patch

import frappe

from amf.amf.utils.tool_maintenance import (
	_names_compatible,
	_resolve_item,
	calculate_next_due_date,
	get_plan_state,
	get_tool_item_groups,
	is_tool_item_group,
	parse_workbook_date,
	tool_item_query,
)
from amf.amf.page.tool_maintenance.tool_maintenance import get_dashboard, get_tool_detail
from frappe.utils import add_days, nowdate


class TestToolMaintenance(unittest.TestCase):
	def test_workbook_name_guard_accepts_matching_equipment(self):
		self.assertTrue(
			_names_compatible(
				"Table de mesure en granit NERIOX",
				"Table de mesure en granite NERIOX",
			)
		)
		self.assertTrue(
			_names_compatible("Outil oscillant Bosch", "Bosch Professional GOP 40-30")
		)

	def test_workbook_name_guard_rejects_reused_item_codes(self):
		self.assertFalse(
			_names_compatible("Fer à souder", "Nettoyeur Ultrasons Pro 20L")
		)
		self.assertFalse(
			_names_compatible("Scie plastique", "Diatest Measurement Tool")
		)

	def test_workbook_dates_are_strict_and_do_not_invent_precision(self):
		self.assertEqual(parse_workbook_date(datetime(2025, 8, 29)), date(2025, 8, 29))
		self.assertEqual(parse_workbook_date("17.06.2022"), date(2022, 6, 17))
		self.assertIsNone(parse_workbook_date(2028))
		self.assertIsNone(parse_workbook_date("Juin 2024"))

	def test_recurring_due_date_supports_calendar_months_and_years(self):
		self.assertEqual(
			calculate_next_due_date(date(2024, 2, 29), 1, "Years"),
			date(2025, 2, 28),
		)
		self.assertEqual(
			calculate_next_due_date(date(2025, 1, 31), 1, "Months"),
			date(2025, 2, 28),
		)

	def test_plan_state_uses_each_plans_warning_window(self):
		plans = [
			frappe._dict(
				name="TMP-1",
				activity="Inspection",
				next_due_date=date(2026, 8, 20),
				warning_days=20,
			),
			frappe._dict(
				name="TMP-2",
				activity="Calibration",
				next_due_date=date(2026, 10, 1),
				warning_days=10,
			),
		]
		state = get_plan_state(plans, today=date(2026, 8, 5))
		self.assertEqual(state["status"], "Due Soon")
		self.assertEqual(state["next_plan"].name, "TMP-1")

	def test_overdue_plan_has_priority(self):
		plans = [
			frappe._dict(
				name="TMP-1",
				activity="Inspection",
				next_due_date=date(2026, 8, 4),
				warning_days=30,
			)
		]
		state = get_plan_state(plans, today=date(2026, 8, 5))
		self.assertEqual(state["status"], "Overdue")
		self.assertEqual(state["overdue_count"], 1)


class TestToolMaintenanceHierarchy(unittest.TestCase):
	"""Run against a connected site; every fixture is rolled back to a savepoint."""
	def setUp(self):
		if not getattr(frappe.local, "db", None):
			self.skipTest("A connected Frappe site is required.")
		if not frappe.db.exists("Item Group", "Tool"):
			self.skipTest("The Tool Item Group is required.")
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.sql("SAVEPOINT tool_maintenance_hierarchy_test")
		self.addCleanup(self._rollback)
		# QR attachments use the filesystem, which a database rollback cannot undo.
		qr_patch = patch("amf.amf.utils.custom.qr_code_to_document")
		qr_patch.start()
		self.addCleanup(qr_patch.stop)

	def _rollback(self):
		frappe.db.sql("ROLLBACK TO SAVEPOINT tool_maintenance_hierarchy_test")
		frappe.set_user(self.previous_user)

	def _group(self, parent="Tool", is_group=0):
		return frappe.get_doc({
			"doctype": "Item Group",
			"item_group_name": "_Tool Maintenance Test {0}".format(uuid4().hex[:10]),
			"parent_item_group": parent,
			"is_group": is_group,
		}).insert()

	def _item(self, group):
		code = "_TM-{0}".format(uuid4().hex[:10])
		return frappe.get_doc({
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": group,
			"stock_uom": frappe.db.get_value("Item", {"item_group": "Tool"}, "stock_uom") or "Nos",
			"is_stock_item": 0,
		}).insert()

	def _plan(self, item):
		return frappe.get_doc({
			"doctype": "Tool Maintenance Plan",
			"naming_series": "TMP-.YYYY.-.#####",
			"item_code": item.name,
			"maintenance_type": "Inspection",
			"activity": "Hierarchy regression inspection",
			"status": "Active",
			"next_due_date": add_days(nowdate(), 7),
			"warning_days": 30,
			"frequency_value": 1,
			"frequency_unit": "Months",
		}).insert()

	def _log(self, item, plan=None):
		return frappe.get_doc({
			"doctype": "Tool Maintenance Log",
			"naming_series": "TML-.YYYY.-.#####",
			"item_code": item.name,
			"maintenance_plan": plan.name if plan else None,
			"intervention_type": "Inspection",
			"intervention": "Hierarchy regression inspection",
			"intervention_date": nowdate(),
		}).insert()

	def test_new_nested_subgroups_work_in_dashboard_details_and_selectors(self):
		parent = self._group(is_group=1)
		child = self._group(parent.name)
		item = self._item(child.name)
		self.assertIn(child.name, get_tool_item_groups())
		self.assertTrue(is_tool_item_group(child.name))
		self.assertEqual(item.tool_maintenance_status, "No Plan")
		self.assertEqual(get_dashboard(search=item.name)["summary"]["tools"], 1)
		self.assertEqual(get_tool_detail(item.name)["item"]["item_code"], item.name)
		self.assertEqual(tool_item_query("Item", item.name, "name", 0, 20)[0][0], item.name)
		matched, reason = _resolve_item(item.name, item.item_name, [item], {item.name: item})
		self.assertEqual(matched.name, item.name)
		self.assertIsNone(reason)
		item.disabled = 1
		item.save()
		self.assertEqual(get_dashboard(search=item.name)["summary"]["tools"], 0)
		self.assertEqual(get_dashboard(search=item.name, include_disabled=1)["summary"]["tools"], 1)
		self.assertFalse(tool_item_query("Item", item.name, "name", 0, 20))

	def test_subgroup_plan_and_log_updates_refresh_item_dates(self):
		item = self._item(self._group().name)
		plan = self._plan(item)
		item.reload()
		self.assertEqual(item.tool_open_maintenance_plans, 1)
		self.assertEqual(item.tool_maintenance_status, "Due Soon")
		log = self._log(item, plan)
		item.reload()
		self.assertEqual(item.tool_last_maintenance_date, date.fromisoformat(nowdate()))
		self.assertEqual(item.tool_next_maintenance_date, calculate_next_due_date(nowdate(), 1, "Months"))
		log.intervention_date = add_days(nowdate(), -2)
		log.save()
		item.reload()
		self.assertEqual(item.tool_next_maintenance_date, calculate_next_due_date(log.intervention_date, 1, "Months"))
		item.item_group = self._group().name
		item.save()
		self.assertEqual(item.tool_open_maintenance_plans, 1)
		self.assertEqual(get_tool_detail(item.name)["logs"][0].name, log.name)
		item.item_group = self._group(parent="All Item Groups").name
		with self.assertRaises(frappe.ValidationError):
			item.save()

	def test_reparenting_updates_all_descendant_items_without_resaving_them(self):
		parent = self._group(parent="All Item Groups", is_group=1)
		child = self._group(parent.name)
		item = self._item(child.name)
		self.assertFalse(is_tool_item_group(child.name))
		self.assertFalse(item.tool_maintenance_status)
		parent.reload()
		parent.parent_item_group = "Tool"
		parent.save()
		item.reload()
		self.assertTrue(is_tool_item_group(child.name))
		self.assertEqual(item.tool_maintenance_status, "No Plan")
		self.assertEqual(get_dashboard(search=item.name)["summary"]["tools"], 1)
		parent.parent_item_group = "All Item Groups"
		parent.save()
		item.reload()
		self.assertFalse(item.tool_maintenance_status)
		self.assertEqual(get_dashboard(search=item.name)["summary"]["tools"], 0)
		with self.assertRaises(frappe.ValidationError):
			self._plan(item)
		with self.assertRaises(frappe.ValidationError):
			self._log(item)

	def test_maintained_subtree_can_move_within_tool_but_cannot_leave_it(self):
		parent = self._group(is_group=1)
		child = self._group(parent.name)
		item = self._item(child.name)
		self._log(item)
		destination = self._group(is_group=1)
		parent.reload()
		parent.parent_item_group = destination.name
		parent.save()
		self.assertTrue(is_tool_item_group(child.name))
		parent.parent_item_group = "All Item Groups"
		with self.assertRaises(frappe.ValidationError):
			parent.save()
		self.assertTrue(is_tool_item_group(child.name))

	def test_unrelated_group_edits_do_not_touch_item_maintenance(self):
		group = self._group(parent="All Item Groups")
		self._item(group.name)
		with patch("amf.amf.utils.tool_maintenance.sync_item_maintenance_summary") as sync:
			group.save()
			sync.assert_not_called()
