from __future__ import unicode_literals

import unittest

from amf.amf.report.bom_cost_breakdown.average_costing import (
	_add_value, _record, build_sample_groups, summary_rows, trimmed_statistics,
)


def sample(source, quantity, per_unit):
	return dict(source=source, quantity=quantity, amount=quantity * per_unit, per_unit=per_unit)


class TestAverageCosting(unittest.TestCase):
	def test_iqr_excludes_extreme_unit_cost(self):
		result = trimmed_statistics([
			sample("WO-1", 1, 10), sample("WO-2", 1, 11),
			sample("WO-3", 1, 12), sample("WO-4", 1, 100),
		])
		self.assertEqual([row["source"] for row in result["excluded"]], ["WO-4"])
		self.assertEqual(result["average"], 11.0)

	def test_average_is_weighted_by_finished_units(self):
		result = trimmed_statistics([sample("WO-1", 2, 10), sample("WO-2", 10, 20)])
		self.assertAlmostEqual(result["average"], 220 / 12)
		self.assertEqual(result["excluded"], [])

	def test_zero_iqr_excludes_distinct_cost_and_small_samples_do_not_trim(self):
		many = trimmed_statistics([sample("WO-{0}".format(i), 1, value)
			for i, value in enumerate((10, 10, 10, 10, 100))])
		self.assertEqual([row["source"] for row in many["excluded"]], ["WO-4"])
		few = trimmed_statistics([sample("WO-{0}".format(i), 1, value)
			for i, value in enumerate((10, 10, 100))])
		self.assertEqual(few["excluded"], [])

	def test_full_total_requires_all_five_cost_categories(self):
		record = _record("WO-1", "ITEM-1", "COMPANY", "CHF", "Actual", 10)
		_add_value(record, "Materials", 100)
		_add_value(record, "Assembly", 20)
		groups = build_sample_groups({("Actual", "WO-1"): record})
		self.assertIn(("ITEM-1", "COMPANY", "CHF", "Actual", "Materials"), groups)
		self.assertNotIn(("ITEM-1", "COMPANY", "CHF", "Actual", "Full Total"), groups)

	def test_unavailable_component_is_not_treated_as_zero(self):
		record = _record("WO-1", "ITEM-1", "COMPANY", "CHF", "Actual", 10)
		_add_value(record, "Materials", 100)
		_add_value(record, "Materials", None)
		groups = build_sample_groups({("Actual", "WO-1"): record})
		self.assertEqual(groups, {})

	def test_category_coverage_includes_missing_work_orders(self):
		key = ("ITEM-1", "COMPANY", "CHF", "Actual")
		statistics = {key + ("Assembly",): trimmed_statistics([sample("WO-1", 2, 2.411598)])}
		counts = {key: {"WO-1", "WO-2", "WO-3", "WO-4", "WO-5", "WO-6"}}
		rows = summary_rows(statistics, counts)
		self.assertEqual(rows[0]["assembly"], 2.411598)
		self.assertIn("Assembly 1/1/6", rows[0]["coverage"])
