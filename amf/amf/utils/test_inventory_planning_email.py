# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest

from amf.amf.utils.inventory_planning_email import (
	actionable_report_items,
	build_report_summary,
	build_weekly_safety_stock_email,
	group_report_items,
)


class TestInventoryPlanningEmail(unittest.TestCase):
	def setUp(self):
		self.items = [
			_report_item("RAW-1", "Raw Material", 100, 120),
			_report_item("SEAT-1", "Valve Seat", 40, 45),
			_report_item("BODY-1", "Body", 30, 35),
			_report_item("PART-LOW", "Part", 4, 8),
			_report_item("CABLE-1", "Cables", 7, 9),
			_report_item("BOARD-1", "Electronic boards", 6, 8),
			_report_item("ASSEMBLY-1", "Assembly", 5, 7),
			_report_item("PLUG-1", "Plug", 12, 15),
			_report_item("HEAD-1", "Valve Head", 11, 13),
			_report_item("PART-HIGH", "Part", 9, 11),
			_report_item("PART-BREACH", "Part", 0, 5, shortage_date=None),
			_report_item("PRODUCT-1", "Product", 500, 500),
			_report_item("PLUNGER-1", "Plungers", 400, 400),
			_report_item("IGNORE", "Part", 50, 0),
		]

	def test_prioritizes_requested_groups_then_sorts_shortage_descending(self):
		rows = actionable_report_items(self.items)

		self.assertEqual(
			[row["item_code"] for row in rows],
			[
				"PART-HIGH",
				"PART-LOW",
				"PART-BREACH",
				"CABLE-1",
				"BOARD-1",
				"ASSEMBLY-1",
				"PLUG-1",
				"SEAT-1",
				"HEAD-1",
				"BODY-1",
				"RAW-1",
			],
		)

	def test_groups_follow_requested_priority_then_alphabetical(self):
		grouped = group_report_items(self.items)

		self.assertEqual(
			list(grouped.keys()),
			[
				"Part", "Cables", "Electronic boards", "Assembly", "Plug",
				"Valve Seat", "Valve Head", "Body", "Raw Material",
			],
		)

	def test_product_and_plunger_groups_are_excluded(self):
		rows = actionable_report_items(self.items)

		self.assertNotIn("PRODUCT-1", [row["item_code"] for row in rows])
		self.assertNotIn("PLUNGER-1", [row["item_code"] for row in rows])

	def test_summary_uses_only_actionable_rows(self):
		summary = build_report_summary(self.items)

		self.assertEqual(summary["item_count"], 11)
		self.assertEqual(summary["critical_count"], 10)
		self.assertEqual(summary["shortage_qty"], 224)
		self.assertEqual(summary["recommended_qty"], 276)

	def test_email_escapes_item_content_and_includes_projection_columns(self):
		items = [_report_item("A<1", "Part", 5, 8, item_name="Seat & plug")]
		html = build_weekly_safety_stock_email(
			items,
			company="AMF & Co",
			generated_at="2026-08-10 09:00:00",
			report_url="https://erp.example.test/desk#inventory-planning",
			item_url_builder=lambda code: "https://erp.example.test/item/" + code,
		)

		self.assertIn("AMF &amp; Co", html)
		self.assertIn("A&lt;1", html)
		self.assertIn("Seat &amp; plug", html)
		self.assertIn("Min. projected", html)
		self.assertIn("Safety / ROP", html)
		self.assertIn("Potential replenish", html)
		self.assertIn("2026-08-18", html)
		self.assertNotIn("Items to replenish", html)
		self.assertNotIn(">Action<", html)
		self.assertIn("Open Inventory Planning", html)


def _report_item(
	item_code,
	item_group,
	shortage_qty,
	recommended_qty,
	shortage_date="2026-08-20",
	item_name=None,
):
	return {
		"item_code": item_code,
		"item_name": item_name or item_code,
		"item_group": item_group,
		"actual_qty": 10,
		"minimum_projected_qty": -shortage_qty,
		"shortage_qty": shortage_qty,
		"recommended_qty": recommended_qty,
		"safety_stock": 5,
		"reorder_level": 10,
		"shortage_date": shortage_date,
		"safety_breach_date": "2026-08-15",
		"potential_replenish_date": "2026-08-18",
		"potential_replenish_overdue": False,
		"risk": "critical" if shortage_date else "watch",
		"expedite": bool(shortage_date),
		"action": "Expedite purchase" if shortage_date else "Create Purchase Order",
	}


if __name__ == "__main__":
	unittest.main()
