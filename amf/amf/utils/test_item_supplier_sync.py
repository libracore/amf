# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest

from amf.amf.utils.item_supplier_sync import find_missing_supplier_pairs


class TestItemSupplierSync(unittest.TestCase):
	def test_missing_pairs_are_distinct_sorted_and_preserve_existing(self):
		required = [
			("ITEM-2", "Supplier B"),
			("ITEM-1", "Supplier A"),
			("ITEM-1", "Supplier A"),
			("ITEM-1", "Supplier C"),
		]
		existing = [("ITEM-1", "Supplier A")]

		self.assertEqual(
			find_missing_supplier_pairs(required, existing),
			[("ITEM-1", "Supplier C"), ("ITEM-2", "Supplier B")],
		)


if __name__ == "__main__":
	unittest.main()
