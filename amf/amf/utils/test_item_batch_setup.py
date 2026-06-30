from __future__ import unicode_literals

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from amf.amf.utils import item_batch_setup


class FakeDoc(SimpleNamespace):
	def get(self, fieldname):
		return getattr(self, fieldname, None)

	def set(self, fieldname, value):
		setattr(self, fieldname, value)


class TestItemBatchSetup(unittest.TestCase):
	def test_target_item_code_requires_allowed_prefix_and_six_digits(self):
		for item_code in ("100001", "110001", "200001", "210001", "300001"):
			self.assertTrue(item_batch_setup.is_target_item_code(item_code))

		for item_code in ("120001", "310001", "10001", "1000010", "10A001", ""):
			self.assertFalse(item_batch_setup.is_target_item_code(item_code))

	def test_parse_item_codes_splits_and_deduplicates_codes(self):
		self.assertEqual(
			item_batch_setup.parse_item_codes("100001, 110001 100001"),
			["100001", "110001"],
		)

	def test_parse_item_codes_accepts_json_list(self):
		self.assertEqual(
			item_batch_setup.parse_item_codes('["200001", "210001"]'),
			["200001", "210001"],
		)

	def test_apply_batch_tracking_rule_sets_has_batch_for_matching_stock_item(self):
		doc = FakeDoc(item_code="100001", is_stock_item=1, has_batch_no=0)

		item_batch_setup.apply_batch_tracking_rule(doc)

		self.assertEqual(doc.has_batch_no, 1)

	def test_apply_batch_tracking_rule_ignores_non_matching_item(self):
		doc = FakeDoc(item_code="120001", is_stock_item=1, has_batch_no=0)

		item_batch_setup.apply_batch_tracking_rule(doc)

		self.assertEqual(doc.has_batch_no, 0)

	def test_apply_batch_tracking_rule_ignores_non_stock_item(self):
		doc = FakeDoc(item_code="100001", is_stock_item=0, has_batch_no=0)

		item_batch_setup.apply_batch_tracking_rule(doc)

		self.assertEqual(doc.has_batch_no, 0)

	def test_ensure_default_batch_creates_batch_for_matching_item_without_batch(self):
		doc = FakeDoc(name="100001", item_code="100001", is_stock_item=1, disabled=0)

		with patch.object(item_batch_setup, "_get_existing_batch", return_value=None), \
			patch.object(
				item_batch_setup,
				"_create_batch_for_item",
				return_value=SimpleNamespace(name="BATCH-001"),
			) as create_batch:
			result = item_batch_setup.ensure_default_batch_for_item(doc)

		self.assertEqual(result, "BATCH-001")
		create_batch.assert_called_once_with(
			item_name="100001",
			item_code="100001",
			reference_doctype="Item",
			reference_name="100001",
		)

	def test_ensure_default_batch_uses_existing_batch(self):
		doc = FakeDoc(name="100001", item_code="100001", is_stock_item=1, disabled=0)

		with patch.object(item_batch_setup, "_get_existing_batch", return_value="BATCH-001"), \
			patch.object(item_batch_setup, "_create_batch_for_item") as create_batch:
			result = item_batch_setup.ensure_default_batch_for_item(doc)

		self.assertIsNone(result)
		create_batch.assert_not_called()
