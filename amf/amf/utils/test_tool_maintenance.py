# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest
from datetime import date, datetime

import frappe

from amf.amf.utils.tool_maintenance import (
	_names_compatible,
	calculate_next_due_date,
	get_plan_state,
	parse_workbook_date,
)


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
