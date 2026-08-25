# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from amf import hooks
from amf.amf.utils import custom_item


class FakeSellingDocument(frappe._dict):
	def __init__(self, before_save=None, **values):
		super(FakeSellingDocument, self).__init__(values)
		self._before_save = before_save

	def get_doc_before_save(self):
		return self._before_save

	def set(self, fieldname, value):
		self[fieldname] = value


class TestCustomItem(unittest.TestCase):
	def test_custom_valve_head_marks_related_products(self):
		doc = frappe._dict(name="300123", item_group="Valve Head", custom_item=1)

		with patch.object(
			custom_item,
			"_get_related_unchecked_products",
			return_value=["450123", "460123"],
		), patch.object(
			custom_item,
			"_mark_items_custom",
			return_value=["450123", "460123"],
		) as mark_items:
			updated = custom_item.sync_products_from_custom_valve_head(doc)

		self.assertEqual(updated, ["450123", "460123"])
		mark_items.assert_called_once_with(["450123", "460123"])

	def test_unchecked_valve_head_does_not_clear_products(self):
		doc = frappe._dict(name="300123", item_group="Valve Head", custom_item=0)

		with patch.object(custom_item, "_mark_items_custom") as mark_items:
			updated = custom_item.sync_products_from_custom_valve_head(doc)

		self.assertEqual(updated, [])
		mark_items.assert_not_called()

	def test_submitted_default_product_bom_marks_product(self):
		doc = frappe._dict(
			name="BOM-450123-001",
			item="450123",
			docstatus=1,
			is_active=1,
			is_default=1,
		)

		with patch.object(
			custom_item, "_get_item_group", return_value="Product"
		), patch.object(
			custom_item, "_bom_contains_custom_valve_head", return_value=True
		), patch.object(
			custom_item, "_mark_items_custom", return_value=["450123"]
		) as mark_items:
			updated = custom_item.sync_product_from_bom(doc)

		self.assertEqual(updated, ["450123"])
		mark_items.assert_called_once_with(["450123"])

	def test_draft_or_non_default_bom_is_ignored(self):
		for docstatus, is_default in ((0, 1), (1, 0)):
			doc = frappe._dict(
				name="BOM-450123-001",
				item="450123",
				docstatus=docstatus,
				is_active=1,
				is_default=is_default,
			)
			with patch.object(custom_item, "_mark_items_custom") as mark_items:
				self.assertEqual(custom_item.sync_product_from_bom(doc), [])
				mark_items.assert_not_called()

	def test_save_warning_lists_unique_custom_items_and_sets_flag(self):
		doc = FakeSellingDocument(
			items=[
				frappe._dict(item_code="CUSTOM-1"),
				frappe._dict(item_code="STANDARD-1"),
				frappe._dict(item_code="CUSTOM-1"),
			],
		)
		custom_rows = [SimpleNamespace(name="CUSTOM-1", item_name="Special <Head>")]

		with patch.object(frappe, "get_all", return_value=custom_rows), patch.object(
			frappe, "msgprint"
		) as msgprint:
			warned = custom_item.warn_custom_items_on_save(doc)

		self.assertEqual(warned, ["CUSTOM-1"])
		self.assertEqual(doc.custom_item_warning_shown, 1)
		msgprint.assert_called_once()
		message = msgprint.call_args[0][0]
		self.assertIn("CUSTOM-1", message)
		self.assertIn("Special &lt;Head&gt;", message)
		self.assertNotIn("STANDARD-1", message)
		self.assertEqual(msgprint.call_args[1]["indicator"], "orange")

	def test_save_warning_is_suppressed_when_flag_is_set_and_items_are_unchanged(self):
		previous = FakeSellingDocument(items=[frappe._dict(item_code="CUSTOM-1")])
		doc = FakeSellingDocument(
			before_save=previous,
			items=[frappe._dict(item_code="CUSTOM-1")],
			custom_item_warning_shown=1,
		)
		custom_rows = [SimpleNamespace(name="CUSTOM-1", item_name="Special Head")]

		with patch.object(frappe, "get_all", return_value=custom_rows), patch.object(
			frappe, "msgprint"
		) as msgprint:
			warned = custom_item.warn_custom_items_on_save(doc)

		self.assertEqual(warned, [])
		msgprint.assert_not_called()

	def test_save_warning_repeats_when_custom_item_set_changes(self):
		previous = FakeSellingDocument(items=[frappe._dict(item_code="CUSTOM-1")])
		doc = FakeSellingDocument(
			before_save=previous,
			items=[frappe._dict(item_code="CUSTOM-2")],
			custom_item_warning_shown=1,
		)
		custom_rows = [SimpleNamespace(name="CUSTOM-2", item_name="Another Head")]

		with patch.object(
			frappe,
			"get_all",
			side_effect=[custom_rows, [SimpleNamespace(name="CUSTOM-1", item_name="Special Head")]],
		), patch.object(frappe, "msgprint") as msgprint:
			warned = custom_item.warn_custom_items_on_save(doc)

		self.assertEqual(warned, ["CUSTOM-2"])
		msgprint.assert_called_once()

	def test_no_custom_items_rearms_warning_flag(self):
		doc = FakeSellingDocument(
			items=[frappe._dict(item_code="STANDARD-1")],
			custom_item_warning_shown=1,
		)

		with patch.object(frappe, "get_all", return_value=[]), patch.object(
			frappe, "msgprint"
		) as msgprint:
			warned = custom_item.warn_custom_items_on_save(doc)

		self.assertEqual(warned, [])
		self.assertEqual(doc.custom_item_warning_shown, 0)
		msgprint.assert_not_called()

	def test_quotation_and_sales_order_save_hooks_are_registered(self):
		self.assertEqual(
			hooks.doc_events["Quotation"]["before_save"],
			"amf.amf.utils.custom_item.warn_custom_items_on_save",
		)
		self.assertEqual(
			hooks.doc_events["Sales Order"]["before_save"],
			"amf.amf.utils.custom_item.warn_custom_items_on_save",
		)
		self.assertEqual(
			hooks.doc_events["Sales Order"]["on_submit"],
			"amf.master_crm.customer_marketing.sync_customer_marketing_from_sales_order",
		)


if __name__ == "__main__":
	unittest.main()
