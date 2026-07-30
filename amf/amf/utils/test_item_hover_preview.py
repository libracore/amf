# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from unittest.mock import patch

import frappe

from amf.amf.utils import item_hover_preview
from amf.amf.utils.item_hover_preview import _build_item_hover_data


class TestItemHoverPreview(unittest.TestCase):
	def test_stock_summary_accounts_for_every_reservation_type(self):
		item = frappe._dict({
			"name": "ITEM-001",
			"item_name": "Test Item",
			"item_group": "Products",
			"stock_uom": "Nos",
			"default_bom": "BOM-ITEM-001-001",
			"is_stock_item": 1,
			"disabled": 0,
		})
		stock = frappe._dict({
			"actual_qty": 20,
			"ordered_qty": 5,
			"indented_qty": 3,
			"planned_qty": 2,
			"reserved_qty": 4,
			"reserved_qty_for_production": 2,
			"reserved_qty_for_sub_contract": 1,
			"projected_qty": 23,
		})

		data = _build_item_hover_data(item, stock)

		self.assertEqual(data["actual_qty"], 20)
		self.assertEqual(data["on_hand_qty"], 20)
		self.assertEqual(data["on_hand_warehouse"], "Main Stock - AMF21")
		self.assertEqual(data["reserved_qty"], 7)
		self.assertEqual(data["available_qty"], 13)
		self.assertEqual(data["incoming_qty"], 10)
		self.assertEqual(data["projected_qty"], 23)
		self.assertEqual(data["default_bom"], "BOM-ITEM-001-001")

	def test_missing_bins_return_zero_quantities(self):
		item = frappe._dict({
			"name": "SERVICE-001",
			"item_name": "Service",
			"stock_uom": "Hour",
			"is_stock_item": 0,
		})

		data = _build_item_hover_data(item)

		self.assertFalse(data["is_stock_item"])
		self.assertEqual(data["actual_qty"], 0)
		self.assertEqual(data["on_hand_qty"], 0)
		self.assertEqual(data["available_qty"], 0)
		self.assertEqual(data["projected_qty"], 0)

	def test_stock_access_state_is_explicit(self):
		item = frappe._dict({
			"name": "ITEM-002",
			"item_name": "Restricted Item",
			"is_stock_item": 1,
		})

		data = _build_item_hover_data(item, stock_access=False)

		self.assertFalse(data["stock_access"])

	def test_non_stock_item_skips_warehouse_and_bin_queries(self):
		item = frappe._dict({
			"name": "SERVICE-002",
			"item_name": "Consulting",
			"stock_uom": "Hour",
			"is_stock_item": 0,
			"disabled": 0,
		})

		with patch.object(
			item_hover_preview.frappe, "get_list", return_value=[item]
		), patch.object(
			item_hover_preview, "_can_access_stock_warehouse"
		) as can_access_stock_warehouse, patch.object(
			item_hover_preview, "_get_stock_totals"
		) as get_stock_totals:
			data = item_hover_preview.get_item_hover_data("SERVICE-002")

		self.assertFalse(data["is_stock_item"])
		can_access_stock_warehouse.assert_not_called()
		get_stock_totals.assert_not_called()


if __name__ == "__main__":
	unittest.main()
