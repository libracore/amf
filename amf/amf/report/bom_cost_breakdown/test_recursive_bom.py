from __future__ import unicode_literals

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from amf.amf.report.bom_cost_breakdown.recursive_bom import BOMCostWalker, RecursiveBOMCostIndex


def row(name, item_code, amount, child=None, qty=1, stock_qty=1):
	return SimpleNamespace(name=name, item_code=item_code, base_amount=amount,
		base_rate=amount / qty if qty else 0, qty=qty, stock_qty=stock_qty,
		uom="Nos", bom_no=child)


def bom(name, item_code, total, items, operations=None, scrap=None, quantity=1):
	return SimpleNamespace(name=name, item=item_code, company="AMF", quantity=quantity,
		base_total_cost=total, total_cost=total, uom="Nos", docstatus=1,
		items=items, operations=operations or [], scrap_items=scrap or [])


class TestRecursiveBOM(unittest.TestCase):
	def build(self, root, children):
		with patch("amf.amf.report.bom_cost_breakdown.recursive_bom.check_read"):
			return BOMCostWalker(root, loader=lambda doctype, name: children[name],
				currency="CHF", default_bom_lookup=lambda item_code: None).build()

	def test_child_material_operation_and_scrap_match_parent_booked_cost(self):
		operation = SimpleNamespace(name="OP-1", operation="General Assembly",
			time_in_mins=60, base_hour_rate=10, base_operating_cost=10)
		scrap = SimpleNamespace(name="SCR-1", item_code="SCR", stock_qty=1,
			stock_uom="Nos", base_rate=2, base_amount=2)
		child = bom("BOM-CHILD", "CHILD", 28, [row("I-1", "RAW", 20)],
			operations=[operation], scrap=[scrap], quantity=2)
		root = bom("BOM-ROOT", "ROOT", 20,
			[row("I-2", "CHILD", 14, child="BOM-CHILD"), row("I-3", "OTHER", 6)])
		rows = self.build(root, {child.name: child})
		self.assertEqual(rows[-3]["root_amount"], 20)
		self.assertEqual(rows[-1]["root_amount"], 0)
		self.assertFalse(any(r["line_type"] == "Child valuation difference" for r in rows))
		self.assertEqual(sum(r["root_amount"] for r in rows if r["included"] == "Yes"), 20)

	def test_changed_child_cost_is_exposed_as_valuation_difference(self):
		child = bom("BOM-CHILD", "CHILD", 10, [row("I-1", "RAW", 10)])
		root = bom("BOM-ROOT", "ROOT", 15, [row("I-2", "CHILD", 15, child="BOM-CHILD")])
		rows = self.build(root, {child.name: child})
		difference = next(r for r in rows if r["line_type"] == "Child valuation difference")
		self.assertEqual(difference["root_amount"], 5)
		self.assertEqual(rows[-3]["root_amount"], rows[-2]["root_amount"])
		self.assertEqual(len([r for r in rows if r["line_type"] == "Category subtotal" and
			r["category"] == "Reconciliation"]), 1)

	def test_mismatched_child_item_keeps_parent_cost_without_false_expansion(self):
		child = bom("BOM-WRONG", "OTHER", 10, [row("I-1", "RAW", 10)])
		root = bom("BOM-ROOT", "ROOT", 15, [row("I-2", "CHILD", 15, child="BOM-WRONG")])
		rows = self.build(root, {child.name: child})
		self.assertTrue(any(r["status"] == "Child BOM item mismatch" for r in rows))
		self.assertFalse(any(r["bom"] == "BOM-WRONG" for r in rows))
		self.assertEqual(rows[-3]["root_amount"], 15)
		materials = next(r for r in rows if r["line_type"] == "Category subtotal" and r["category"] == "Materials")
		self.assertIsNone(materials["root_amount"])
		self.assertEqual(materials["status"], "Unavailable")

	def test_unpriced_material_does_not_become_zero_subtotal(self):
		root = bom("BOM-ROOT", "ROOT", 0, [row("I-1", "RAW", 0)])
		rows = self.build(root, {})
		materials = next(r for r in rows if r["line_type"] == "Category subtotal" and r["category"] == "Materials")
		self.assertIsNone(materials["root_amount"])
		self.assertEqual(rows[-2]["root_amount"], 0)

	def test_missing_stored_amount_is_not_reported_as_zero(self):
		item = row("I-1", "RAW", 0)
		item.base_amount = None
		item.base_rate = 10
		rows = self.build(bom("BOM-ROOT", "ROOT", 10, [item]), {})
		material = next(r for r in rows if r["line_type"] == "Material")
		self.assertIsNone(material["source_amount"])
		self.assertIsNone(material["root_amount"])
		self.assertEqual(material["status"], "Stored amount unavailable")
		self.assertEqual(rows[-2]["root_amount"], 10)

	def test_header_difference_is_visible_and_total_still_reconciles(self):
		root = bom("BOM-ROOT", "ROOT", 11, [row("I-1", "RAW", 10)])
		rows = self.build(root, {})
		self.assertEqual(next(r for r in rows if r["line_type"] == "BOM header difference")["root_amount"], 1)
		self.assertEqual(rows[-1]["root_amount"], 0)

	def test_bulk_index_matches_recursive_category_totals(self):
		operation = SimpleNamespace(parent="BOM-CHILD", name="OP-1", operation="General Assembly",
			time_in_mins=60, base_hour_rate=10, base_operating_cost=10)
		scrap = SimpleNamespace(parent="BOM-CHILD", name="SCR-1", item_code="SCR", stock_qty=1,
			stock_uom="Nos", base_rate=2, base_amount=2)
		child_item = row("I-1", "RAW", 20)
		child_item.parent = "BOM-CHILD"
		parent_item = row("I-2", "CHILD", 15, child="BOM-CHILD")
		parent_item.parent = "BOM-ROOT"
		child = bom("BOM-CHILD", "CHILD", 28, [child_item], [operation], [scrap], quantity=2)
		root = bom("BOM-ROOT", "ROOT", 15, [parent_item])
		index = RecursiveBOMCostIndex([root, child], [child_item, parent_item], [operation], [scrap])
		result = index.decompose(root.name)
		walked = self.build(root, {child.name: child})
		for category, amount in result["amounts"].items():
			walked_amount = sum(r["root_amount"] for r in walked if r["included"] == "Yes" and r["category"] == category)
			self.assertAlmostEqual(float(amount), walked_amount)
		self.assertEqual(sum(result["amounts"].values()), 15)

	def test_repeated_child_link_is_charged_for_each_parent_row(self):
		child_item = row("I-1", "RAW", 10)
		child_item.parent = "BOM-CHILD"
		parent_items = [row("I-2", "CHILD", 10, child="BOM-CHILD"),
			row("I-3", "CHILD", 10, child="BOM-CHILD")]
		for item in parent_items:
			item.parent = "BOM-ROOT"
		child = bom("BOM-CHILD", "CHILD", 10, [child_item])
		root = bom("BOM-ROOT", "ROOT", 20, parent_items)
		index = RecursiveBOMCostIndex([root, child], [child_item] + parent_items, [], [])
		self.assertEqual(index.decompose(root.name)["amounts"]["Materials"], 20)
		rows = self.build(root, {child.name: child})
		self.assertEqual(sum(r["root_amount"] for r in rows if r["included"] == "Yes"), 20)

	def test_cycle_is_retained_as_unresolved_parent_cost(self):
		cyclic_item = row("I-1", "ROOT", 10, child="BOM-ROOT")
		cyclic_item.parent = "BOM-ROOT"
		root = bom("BOM-ROOT", "ROOT", 10, [cyclic_item])
		index = RecursiveBOMCostIndex([root], [cyclic_item], [], [])
		self.assertIn("Materials", index.decompose(root.name)["invalid"])
		rows = self.build(root, {})
		self.assertTrue(any(r["status"] == "BOM cycle" for r in rows))
		self.assertEqual(rows[-3]["root_amount"], 10)
