from __future__ import unicode_literals

import unittest
from datetime import date, time
from types import SimpleNamespace

from amf.amf.report.bom_cost_breakdown.latest_purchase_bom import LatestPurchaseBOMCalculator


def item(name, code, qty, stock_qty, child=None, uom="Nos", stock_uom="Nos"):
	return SimpleNamespace(name=name, item_code=code, qty=qty, stock_qty=stock_qty,
		uom=uom, stock_uom=stock_uom, base_amount=100, bom_no=child)


def bom(name, code, qty, items, operations=None, scrap_items=None, total=40, uom="Nos"):
	return SimpleNamespace(name=name, item=code, quantity=qty, uom=uom,
		items=items, operations=operations or [], scrap_items=scrap_items or [],
		base_total_cost=total)


def receipt(code, stock_qty, net_amount, stock_uom="Nos"):
	return SimpleNamespace(name="PRI-1", parent="PREC-1", item_code=code,
		stock_qty=stock_qty, base_net_amount=net_amount, stock_uom=stock_uom,
		posting_date=date(2026, 8, 1), posting_time=time(10, 0),
		uom=stock_uom, base_net_rate=net_amount / stock_qty)


def line(rows, name, category=None):
	return next(r for r in rows if r["line_type"] == name and
		(category is None or r["category"] == category))


class TestLatestPurchaseBOM(unittest.TestCase):
	def test_process_costs_apply_at_each_item_and_preserve_purchase_baseline(self):
		child = bom("BOM-CHILD", "CHILD", 1,
			[item("CHILD-RAW", "RAW-C", 3, 3)])
		root = bom("BOM-ROOT", "ROOT", 1,
			[item("ROOT-RAW", "RAW-R", 1, 1), item("ROOT-CHILD", "CHILD", 2, 2)])
		selector = lambda code: (root if code == "ROOT" else child, "Item.default_bom") if code in ("ROOT", "CHILD") else (None, "No active BOM")
		def process(average=None, total=5):
			return dict(average=average, eligible=1 if average is not None else 0,
				retained=1 if average is not None else 0, total_work_orders=total,
				retained_quantity=10, retained_amount=average * 10 if average is not None else None,
				samples=[], valid=average is not None)
		costs = {"ROOT": {"Machining": process(5), "Assembly": process()},
			"CHILD": {"Machining": process(3), "Assembly": process(4)}}
		rows = LatestPurchaseBOMCalculator(root, selector,
			{"RAW-R": receipt("RAW-R", 1, 10), "RAW-C": receipt("RAW-C", 1, 1)},
			"CHF", process_costs=costs).build()
		self.assertEqual(line(rows, "Purchase-repriced BOM value")["root_amount"], 16)
		self.assertEqual(line(rows, "Category subtotal", "Machining")["root_amount"], 11)
		self.assertEqual(line(rows, "Category subtotal", "Assembly")["root_amount"], 8)
		self.assertEqual(line(rows, "Known purchased material + process subtotal")["root_amount"], 35)
		self.assertIsNone(line(rows, "Full manufacturing cost")["root_amount"])
		child_material = next(row for row in rows if row["line_type"] == "Item recursive subtotal"
			and row["item_code"] == "CHILD" and row["category"] == "Materials")
		self.assertEqual(child_material["root_amount"], 6)
		self.assertEqual(child_material["item_unit_cost"], 3)
		self.assertEqual(line(rows, "Process availability", "Assembly")["status"], "Unavailable")

	def test_actual_process_replaces_planned_operation_and_shows_excluded_source(self):
		root = bom("BOM-ROOT", "ROOT", 1, [], operations=[SimpleNamespace(
			name="OP-1", operation="General Assembly", time_in_mins=60,
			base_hour_rate=4, base_operating_cost=4)])
		selector = lambda code: (root, "Item.default_bom")
		costs = {"ROOT": {
			"Machining": dict(average=None, retained=0, eligible=0, total_work_orders=2, samples=[]),
			"Assembly": dict(average=6, retained=1, eligible=2, total_work_orders=2,
				retained_quantity=1, retained_amount=6, lower=0, upper=20,
				samples=[dict(source="WO-1", quantity=1, amount=6, per_unit=6,
					excluded=False, sources_match=True, source_rows=[]),
					dict(source="WO-2", quantity=1, amount=100, per_unit=100,
						excluded=True, sources_match=True, source_rows=[dict(
							source_record="TIMER-2", hours=100 / 65.0, rate=65,
							amount=100, method="seconds / 3600 × rate", source_type="Timer Production")])])}}
		rows = LatestPurchaseBOMCalculator(root, selector, {}, "CHF", process_costs=costs).build()
		self.assertEqual(line(rows, "Purchase-repriced BOM value")["root_amount"], 4)
		self.assertEqual(line(rows, "Known purchased material + process subtotal")["root_amount"], 6)
		self.assertEqual(line(rows, "Recorded BOM operation")["included"], "No")
		self.assertEqual(line(rows, "Recorded BOM operation")["basis"], "Planned")
		self.assertEqual(next(row for row in rows if row["line_type"] == "Work Order observation"
			and row["source_record"] == "WO-2")["sample_decision"], "Excluded by IQR")
		self.assertEqual(line(rows, "Process source detail")["observed_amount"], 100)

	def test_current_child_scales_purchased_leaf_operation_and_scrap(self):
		child = bom("BOM-CHILD", "CHILD", 2, [item("CHILD-RAW", "RAW", 3, 3)],
			operations=[SimpleNamespace(name="OP-1", operation="General Assembly",
				time_in_mins=60, base_hour_rate=4, base_operating_cost=4)])
		root = bom("BOM-ROOT", "ROOT", 2,
			[item("ROOT-CHILD", "CHILD", 4, 4, child="BOM-HISTORICAL")],
			scrap_items=[SimpleNamespace(name="SCR-1", item_code="SCR", stock_qty=1,
				stock_uom="Nos", base_rate=2, base_amount=2)])
		selector = lambda code: (child, "Item.default_bom") if code == "CHILD" else (root, "Item.default_bom") if code == "ROOT" else (None, "No active BOM")
		rows = LatestPurchaseBOMCalculator(root, selector, {"RAW": receipt("RAW", 10, 50)}, "CHF").build()
		self.assertEqual(line(rows, "Category subtotal", "Materials")["root_amount"], 30)
		self.assertEqual(line(rows, "Category subtotal", "Assembly")["root_amount"], 8)
		self.assertEqual(line(rows, "Category subtotal", "Scrap Credit")["root_amount"], -2)
		self.assertEqual(line(rows, "Purchase-repriced BOM value")["root_amount"], 36)
		self.assertEqual(line(rows, "Purchase-repriced BOM value")["per_finished_unit"], 18)
		self.assertEqual(line(rows, "Change from stored BOM")["root_amount"], -4)
		self.assertEqual(line(rows, "Selected subassembly")["child_bom"], "BOM-CHILD")

	def test_missing_purchase_receipt_makes_total_unavailable(self):
		root = bom("BOM-ROOT", "ROOT", 1, [item("RAW-1", "RAW", 1, 1)])
		selector = lambda code: (root, "Item.default_bom") if code == "ROOT" else (None, "No active BOM")
		rows = LatestPurchaseBOMCalculator(root, selector, {}, "CHF").build()
		self.assertIsNone(line(rows, "Purchase-repriced BOM value")["root_amount"])
		self.assertIsNone(line(rows, "Category subtotal", "Materials")["root_amount"])
		self.assertEqual(line(rows, "Purchased material")["status"], "Purchase rate unavailable")

	def test_stale_bom_stock_uom_requires_matching_item_and_bom_row_uom(self):
		root = bom("BOM-ROOT", "ROOT", 1,
			[item("RAW-1", "RAW", 0.02, 0.02, uom="Meter", stock_uom="Nos")])
		selector = lambda code: (root, "Item.default_bom") if code == "ROOT" else (None, "No active BOM")
		pr = {"RAW": receipt("RAW", 100, 600, stock_uom="Meter")}
		rows = LatestPurchaseBOMCalculator(root, selector, pr, "CHF",
			stock_uoms={"RAW": "Meter"}).build()
		self.assertEqual(line(rows, "Purchased material")["status"], "Priced; BOM stock UOM corrected")
		self.assertEqual(line(rows, "Purchase-repriced BOM value")["root_amount"], 0.12)
		rows_without_proof = LatestPurchaseBOMCalculator(root, selector, pr, "CHF").build()
		self.assertEqual(line(rows_without_proof, "Purchased material")["status"], "Stock UOM mismatch")
		self.assertIsNone(line(rows_without_proof, "Purchase-repriced BOM value")["root_amount"])

	def test_cycle_is_unavailable_instead_of_using_stored_parent_amount(self):
		root = bom("BOM-ROOT", "ROOT", 1,
			[item("ROOT-1", "ROOT", 1, 1, child="BOM-ROOT")])
		selector = lambda code: (root, "Item.default_bom")
		rows = LatestPurchaseBOMCalculator(root, selector, {}, "CHF").build()
		self.assertEqual(line(rows, "BOM cycle")["status"], "Cycle")
		self.assertIsNone(line(rows, "Purchase-repriced BOM value")["root_amount"])
