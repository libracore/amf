# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import date, timedelta
import unittest

from amf.amf.utils.inventory_planning_engine import (
	build_demand_profile,
	build_lead_profile,
	build_recommendation,
	calculate_inventory_policy,
	project_inventory,
	remaining_work_order_demand,
	winsorize_demand,
)


class TestInventoryPlanningCalculations(unittest.TestCase):
	def test_zero_filled_stable_demand(self):
		start = date(2025, 1, 1)
		end = start + timedelta(days=364)
		demand = {
			start + timedelta(days=offset): 1
			for offset in range(365)
		}

		profile = build_demand_profile(demand, start, end)

		self.assertAlmostEqual(profile["forecast_daily"], 1.0, places=6)
		self.assertAlmostEqual(profile["daily_std"], 0.0, places=6)
		self.assertEqual(profile["pattern"], "stable")
		self.assertEqual(profile["confidence"], "high")

	def test_recent_behavior_receives_more_weight(self):
		start = date(2025, 1, 1)
		end = start + timedelta(days=179)
		demand = {}
		for offset in range(180):
			demand[start + timedelta(days=offset)] = 1 if offset < 90 else 2

		profile = build_demand_profile(demand, start, end)

		self.assertGreater(profile["forecast_daily"], 1.5)
		self.assertEqual(profile["trend"], "rising")

	def test_outlier_is_capped_only_with_enough_evidence(self):
		values = [0] * 20 + [10] * 10 + [1000]
		adjusted, cap, capped_days = winsorize_demand(values)

		self.assertIsNotNone(cap)
		self.assertEqual(capped_days, 1)
		self.assertLess(adjusted[-1], 1000)

	def test_composite_safety_stock_formula(self):
		policy = calculate_inventory_policy(
			{"forecast_daily": 2, "daily_std": 1},
			{"average_days": 10, "std_days": 2},
			1.645,
			30,
		)

		self.assertEqual(policy["safety_stock"], 9)
		self.assertEqual(policy["reorder_level"], 29)
		self.assertEqual(policy["order_up_to_level"], 89)

	def test_firm_demand_replaces_baseline_instead_of_double_counting(self):
		start = date(2026, 7, 1)
		projection = project_inventory(
			opening_qty=20,
			safety_stock=5,
			forecast_daily=1,
			start_date=start,
			horizon_days=10,
			events=[{
				"date": start + timedelta(days=4),
				"qty": 6,
				"direction": "demand",
				"confidence": "firm",
			}],
		)

		self.assertAlmostEqual(projection["firm_demand_qty"], 6)
		self.assertAlmostEqual(projection["forecast_residual_qty"], 4)
		self.assertAlmostEqual(projection["ending_projected_qty"], 10)

	def test_soft_supply_never_hides_firm_shortage(self):
		start = date(2026, 7, 1)
		projection = project_inventory(
			opening_qty=3,
			safety_stock=2,
			forecast_daily=1,
			start_date=start,
			horizon_days=5,
			events=[{
				"date": start + timedelta(days=1),
				"qty": 20,
				"direction": "supply",
				"confidence": "soft",
			}],
		)

		self.assertIsNotNone(projection["shortage_date"])
		self.assertLess(projection["ending_projected_qty"], 0)
		self.assertGreater(projection["ending_with_soft_qty"], 0)

	def test_transferred_work_order_material_remains_committed(self):
		self.assertEqual(remaining_work_order_demand(100, 25), 75)
		self.assertEqual(remaining_work_order_demand(100, 120), 0)

	def test_low_sample_lead_time_keeps_conservative_variability(self):
		profile = build_lead_profile(
			[{"days": 10, "weight": 1, "source": "PO → PREC"}],
			fallback_days=20,
			source_type="purchase",
		)

		self.assertEqual(profile["average_days"], 10)
		self.assertEqual(profile["std_days"], 5)
		self.assertEqual(profile["confidence"], "low")

	def test_recommendation_respects_minimum_order_quantity(self):
		start = date(2026, 7, 1)
		projection = project_inventory(
			opening_qty=10,
			safety_stock=8,
			forecast_daily=1,
			start_date=start,
			horizon_days=30,
			events=[],
		)
		recommendation = build_recommendation(
			projection=projection,
			lead_time_days=5,
			review_period_days=10,
			safety_stock=8,
			min_order_qty=25,
			procurement_type="Purchase",
			today=start,
		)

		self.assertEqual(recommendation["recommended_qty"], 25)
		self.assertTrue(recommendation["expedite"])


if __name__ == "__main__":
	unittest.main()
