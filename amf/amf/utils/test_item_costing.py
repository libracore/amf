# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and Contributors
# See license.txt
from __future__ import unicode_literals

import unittest
from unittest.mock import Mock, patch

from amf.amf.utils.item_costing import (
	build_item_batch_costing_rows,
	calculate_item_batch_total_cost,
	get_item_assembly_cost_entries,
)


class TestItemCosting(unittest.TestCase):
	def test_calculate_item_batch_total_cost_keeps_empty_when_both_sources_missing(self):
		self.assertIsNone(calculate_item_batch_total_cost())

	def test_build_item_batch_costing_rows_merges_matching_batches_and_leaves_missing_cells_empty(self):
		rows = build_item_batch_costing_rows(
			machining_entries=[
				{"source_row": "PCT-001", "batch_no": "BATCH-001", "machining_cost": 120},
				{"source_row": "PCT-002", "batch_no": None, "machining_cost": 45},
			],
			assembly_entries=[
				{"source_row": "TPAC-001", "batch_no": "BATCH-001", "assembly_cost": 30},
				{"source_row": "TPAC-002", "batch_no": "BATCH-002", "assembly_cost": 18},
			],
		)

		self.assertEqual(rows[0], {
			"batch_no": "BATCH-001",
			"machining_cost": 120.0,
			"assembly_cost": 30.0,
			"total_cost": 150.0,
		})
		self.assertEqual(rows[1], {
			"batch_no": "BATCH-002",
			"machining_cost": None,
			"assembly_cost": 18.0,
			"total_cost": 18.0,
		})
		self.assertEqual(rows[2], {
			"batch_no": None,
			"machining_cost": 45.0,
			"assembly_cost": None,
			"total_cost": 45.0,
		})

	def test_build_item_batch_costing_rows_sums_same_source_type_for_same_batch(self):
		rows = build_item_batch_costing_rows(
			machining_entries=[
				{"source_row": "PCT-001", "batch_no": "BATCH-001", "machining_cost": 100},
				{"source_row": "PCT-002", "batch_no": "BATCH-001", "machining_cost": 25},
			],
			assembly_entries=[],
		)

		self.assertEqual(rows, [{
			"batch_no": "BATCH-001",
			"machining_cost": 125.0,
			"assembly_cost": None,
			"total_cost": 125.0,
		}])

	def test_get_item_assembly_cost_entries_uses_cost_per_part(self):
		mock_frappe = Mock()
		mock_frappe.db.sql.return_value = []

		with patch("amf.amf.utils.item_costing.frappe", mock_frappe):
			get_item_assembly_cost_entries("ITEM-001")

		query = mock_frappe.db.sql.call_args[0][0]
		self.assertIn("tpac.cost_per_part AS assembly_cost", query)
		self.assertNotIn("tpac.total_cost AS assembly_cost", query)
