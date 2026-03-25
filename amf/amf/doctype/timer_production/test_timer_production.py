# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and Contributors
# See license.txt
from __future__ import unicode_literals

import unittest
from amf.amf.doctype.timer_production.timer_production import (
	build_timer_production_assembly_cost_row,
	calculate_timer_production_cost_per_part,
	calculate_timer_production_time_per_part_minutes,
	calculate_timer_production_total_cost,
)


class TestTimerProduction(unittest.TestCase):
	def test_calculate_timer_production_total_cost_converts_seconds_to_hours(self):
		self.assertEqual(
			calculate_timer_production_total_cost(total_duration=5400),
			97.5,
		)

	def test_calculate_timer_production_cost_per_part_uses_produced_quantity(self):
		self.assertEqual(
			calculate_timer_production_cost_per_part(total_cost=97.5, quantity=15),
			6.5,
		)

	def test_calculate_timer_production_time_per_part_minutes_converts_seconds(self):
		self.assertEqual(
			calculate_timer_production_time_per_part_minutes(total_duration=5400, quantity=15),
			6.0,
		)

	def test_build_timer_production_assembly_cost_row_maps_item_and_costs(self):
		row = build_timer_production_assembly_cost_row({
			'item_code': '300041',
			'quantity': '15',
			'total_duration': 5400,
		})

		self.assertEqual(row['item_code'], '300041')
		self.assertEqual(row['total_cost'], 97.5)
		self.assertEqual(row['time_per_part_minutes'], 6.0)
		self.assertEqual(row['cost_per_part'], 6.5)
