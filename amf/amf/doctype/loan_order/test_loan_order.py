# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from amf.amf.doctype.loan_order import loan_order


class AttrDoc(SimpleNamespace):
	def get(self, fieldname, default=None):
		return getattr(self, fieldname, default)

	def set(self, fieldname, value):
		setattr(self, fieldname, value)


class TestLoanOrderBilling(unittest.TestCase):
	def setUp(self):
		self.loan = frappe._dict({"party": "TEST-CUSTOMER"})
		self.product = frappe._dict({
			"name": "LOAN-ITEM-1",
			"idx": 1,
			"item_code": "PRODUCT-1",
			"item_name": "Test Product",
			"description": "Test Product",
			"uom": "Nos",
			"conversion_factor": 1,
			"billing_bom": "BOM-PRODUCT-1",
			"loaned_qty": 2,
			"remaining_qty": 2,
		})
		self.components = [
			frappe._dict({
				"item_code": "VALVE-1",
				"item_name": "Valve Head",
				"description": "Valve Head",
				"qty_per_stock_unit": 1,
				"uom": "Nos",
				"conversion_factor": 1,
			}),
			frappe._dict({
				"item_code": "SYRINGE-1",
				"item_name": "Syringe",
				"description": "Syringe",
				"qty_per_stock_unit": 2,
				"uom": "Nos",
				"conversion_factor": 1,
			}),
		]

	def get_rate(self, item_code, uom, qty, price_list, customer, transaction_date):
		return {"PRODUCT-1": 1000, "VALVE-1": 200, "SYRINGE-1": 50}[item_code]

	@patch.object(loan_order, "get_direct_bom_components")
	@patch.object(loan_order, "get_selling_rate")
	def test_full_purchase_splits_price_without_changing_total(self, get_rate, get_components):
		get_rate.side_effect = self.get_rate
		get_components.return_value = self.components

		lines, missing = loan_order.build_product_billing_lines(
			self.loan,
			self.product,
			loan_order.LOAN_BILLING_PURCHASE,
			"Test Price List",
			"2026-08-11",
		)

		self.assertFalse(missing)
		self.assertEqual([row.item_code for row in lines], ["PRODUCT-1", "VALVE-1", "SYRINGE-1"])
		self.assertEqual(lines[0].price_list_rate, 1000)
		self.assertEqual(lines[0].discount_amount, 300)
		self.assertEqual(lines[0].rate, 700)
		self.assertEqual(lines[1].discount_amount, 0)
		self.assertEqual(lines[2].discount_amount, 0)
		self.assertEqual(lines[1].qty, 2)
		self.assertEqual(lines[2].qty, 4)
		self.assertEqual(sum(row.qty * row.rate for row in lines), 2000)

	@patch.object(loan_order, "get_direct_bom_components")
	@patch.object(loan_order, "get_selling_rate")
	def test_spare_parts_only_excludes_product(self, get_rate, get_components):
		get_rate.side_effect = self.get_rate
		get_components.return_value = self.components

		lines, missing = loan_order.build_product_billing_lines(
			self.loan,
			self.product,
			loan_order.LOAN_BILLING_SPARES,
			"Test Price List",
			"2026-08-11",
		)

		self.assertFalse(missing)
		self.assertEqual([row.item_code for row in lines], ["VALVE-1", "SYRINGE-1"])
		self.assertEqual(sum(row.qty * row.rate for row in lines), 600)

	def test_auto_role_uses_item_master_groups(self):
		row = frappe._dict({"commercial_role": "Auto"})
		self.assertEqual(
			loan_order.get_commercial_role(row, frappe._dict({"item_group": "Product"})),
			loan_order.LOAN_PRODUCT_ROLE,
		)
		self.assertEqual(
			loan_order.get_commercial_role(row, frappe._dict({"item_group": "Valve Head"})),
			loan_order.LOAN_SPARE_ROLE,
		)
		self.assertEqual(
			loan_order.get_commercial_role(row, frappe._dict({"item_group": "Cable"})),
			loan_order.LOAN_OTHER_ROLE,
		)

	def test_bom_components_with_same_item_are_combined(self):
		components = [
			frappe._dict({"item_code": "VALVE-1", "uom": "Nos", "qty_per_stock_unit": 1}),
			frappe._dict({"item_code": "VALVE-1", "uom": "Nos", "qty_per_stock_unit": 2}),
		]
		combined = loan_order.combine_bom_components(components)
		self.assertEqual(len(combined), 1)
		self.assertEqual(combined[0].qty_per_stock_unit, 3)

	def test_repack_valuation_is_value_neutral(self):
		doc = AttrDoc(
			loan_order_settlement_type=loan_order.LOAN_SETTLEMENT_REPACK,
			items=[
				frappe._dict({
					"s_warehouse": "Client Site - AMF21", "t_warehouse": None,
					"basic_amount": 100, "amount": 100,
				}),
				frappe._dict({
					"s_warehouse": None, "t_warehouse": "Client Site - AMF21",
					"transfer_qty": 1, "loan_settlement_valuation_share": 0.7,
				}),
				frappe._dict({
					"s_warehouse": None, "t_warehouse": "Client Site - AMF21",
					"transfer_qty": 2, "loan_settlement_valuation_share": 0.2,
				}),
				frappe._dict({
					"s_warehouse": None, "t_warehouse": "Client Site - AMF21",
					"transfer_qty": 1, "loan_settlement_valuation_share": 0.1,
				}),
			],
		)

		loan_order.prepare_loan_settlement_repack(doc)

		self.assertAlmostEqual(doc.total_outgoing_value, 100)
		self.assertAlmostEqual(doc.total_incoming_value, 100)
		self.assertAlmostEqual(doc.value_difference, 0)
		self.assertEqual([row.basic_amount for row in doc.items[1:]], [70, 20, 10])
		self.assertEqual([row.basic_rate for row in doc.items[1:]], [70, 10, 10])

	@patch.object(loan_order, "build_settlement_delivery_note")
	@patch.object(loan_order, "get_product_spare_selling_value_per_uom")
	@patch.object(loan_order, "get_selling_rate")
	def test_return_uses_declared_value_when_legacy_prices_are_missing(
			self, get_rate, get_spare_value, build_delivery_note):
		get_rate.return_value = None
		get_spare_value.return_value = 300
		build_delivery_note.side_effect = lambda *args, **kwargs: (args, kwargs)
		loan = AttrDoc(
			party="TEST-CUSTOMER",
			items=[
				frappe._dict({
					"name": "ROW-1", "commercial_role": loan_order.LOAN_PRODUCT_ROLE,
					"item_code": "PRODUCT-1", "item_name": "Product", "description": "Product",
					"remaining_qty": 1, "uom": "Nos", "conversion_factor": 1,
					"declared_rate": 40, "return_warehouse": "Stores - AMF21",
				}),
				frappe._dict({
					"name": "ROW-2", "commercial_role": loan_order.LOAN_OTHER_ROLE,
					"item_code": "CABLE-1", "item_name": "Cable", "description": "Cable",
					"remaining_qty": 1, "uom": "Nos", "conversion_factor": 1,
					"declared_rate": 10, "return_warehouse": "Stores - AMF21",
				}),
			],
		)
		repack = AttrDoc(
			name="STE-TEST",
			items=[
				frappe._dict({
					"item_code": "BODY-1", "item_name": "Body", "description": "Body",
					"t_warehouse": "Client Site - AMF21", "loan_order_item": "ROW-1",
					"qty": 1, "uom": "Nos", "conversion_factor": 1,
					"basic_amount": 28, "serial_no": "BODY-SERIAL-1", "batch_no": None,
				}),
			],
		)

		args, kwargs = loan_order.build_remaining_items_return_delivery_note(loan, "CHF", repack)

		rows = args[2]
		self.assertEqual([row.rate for row in rows], [40, 10])
		self.assertEqual([row.item_code for row in rows], ["BODY-1", "CABLE-1"])
		self.assertTrue(kwargs["is_return"])

	@patch.object(frappe.db, "set_value")
	def test_cancelled_delivery_note_releases_exact_loan_order_links(self, set_value):
		loan = AttrDoc(
			name="LOAN-1",
			meta=AttrDoc(has_field=lambda fieldname: True),
			outward_delivery_note="DN-OTHER",
			return_delivery_note="DN-1",
			settlement_delivery_note=None,
			settlement_return_delivery_note="DN-1",
		)
		delivery_note = AttrDoc(doctype="Delivery Note", name="DN-1")

		changed = loan_order.unlink_generated_document_from_loan_order(delivery_note, loan)

		self.assertTrue(changed)
		self.assertEqual(loan.outward_delivery_note, "DN-OTHER")
		self.assertIsNone(loan.return_delivery_note)
		self.assertIsNone(loan.settlement_return_delivery_note)
		set_value.assert_called_once_with(
			"Loan Order",
			"LOAN-1",
			{"return_delivery_note": None, "settlement_return_delivery_note": None},
			update_modified=False,
		)
