from __future__ import unicode_literals

import unittest
from types import SimpleNamespace

import frappe

from amf.amf.report.bom_cost_breakdown.bom_cost_breakdown import (
	actual_good_qty,
	finalize,
	operation_category,
	planned_rows,
)


class TestBOMCostBreakdown(unittest.TestCase):
	def test_planning_scrap_is_allocated_over_accepted_parts(self):
		wo = frappe._dict(name="OF-1", production_item="PART", produced_qty=26, scrap_qty="2")
		plan = frappe._dict(name="P-1", item_code="PART", quantite_validee=24, quantite_scrap=2)
		self.assertEqual(actual_good_qty(wo, [plan]),
			(24.0, 2.0, "Planning accepted + scrap = Work Order produced_qty"))

	def test_unreconciled_planning_quantity_cannot_be_used_as_denominator(self):
		wo = frappe._dict(name="OF-1", production_item="PART", produced_qty=26, scrap_qty=None)
		plan = frappe._dict(name="P-1", item_code="PART", quantite_validee=20, quantite_scrap=2)
		self.assertIsNone(actual_good_qty(wo, [plan])[0])

	def test_work_order_scrap_is_used_without_planning(self):
		wo = frappe._dict(name="OF-1", production_item="PART", produced_qty=10, scrap_qty="2")
		self.assertEqual(actual_good_qty(wo, [])[:2], (8.0, 2.0))

	def test_missing_quality_cost_keeps_full_total_unavailable(self):
		rows = []
		for category in ("Materials", "Machining", "Assembly", "Final Testing"):
			rows.append(dict(basis="Planned", category=category, component="Detail",
				amount=10.0, status="Available", per_unit=None))
		finalize(rows, "Planned", 2, "CHF")
		known = next(r for r in rows if r["component"] == "Known cost subtotal")
		full = next(r for r in rows if r["component"] == "Full cost per finished unit")
		self.assertEqual(known["per_unit"], 20.0)
		self.assertIsNone(full["per_unit"])
		self.assertEqual(full["status"], "Unavailable")

	def test_no_priced_cost_does_not_show_zero_subtotal(self):
		rows = []
		finalize(rows, "Actual", None, "CHF")
		known = next(r for r in rows if r["component"] == "Known cost subtotal")
		self.assertIsNone(known["amount"])

	def test_zero_bom_operation_rate_is_unavailable(self):
		bom = SimpleNamespace(name="BOM-1", items=[], scrap_items=[], inspection_required=0, base_total_cost=0,
			operations=[SimpleNamespace(name="OP-1", operation="Bench Testing",
				time_in_mins=30, base_hour_rate=0, base_operating_cost=0)])
		rows = []
		planned_rows(rows, bom)
		self.assertEqual(rows[0]["category"], "Final Testing")
		self.assertIsNone(rows[0]["amount"])

	def test_classification_keeps_unknown_work_visible(self):
		self.assertEqual(operation_category("CNC Machining"), "Machining")
		self.assertEqual(operation_category("Contrôle Visuel"), "Quality Control")
		self.assertEqual(operation_category("Bench Testing"), "Final Testing")
		self.assertEqual(operation_category("Resin Coating"), "Other Operations")
