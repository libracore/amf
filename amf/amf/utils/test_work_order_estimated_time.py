# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest

from amf.amf.utils.work_order_estimated_time import (
    calculate_estimated_manufacturing_days,
    calculate_estimated_manufacturing_time,
    get_estimated_time_values,
    is_estimated_time_item_code,
)


class TestWorkOrderEstimatedTime(unittest.TestCase):
    def test_item_code_must_be_six_digits_and_start_with_10_or_20(self):
        self.assertTrue(is_estimated_time_item_code("101234"))
        self.assertTrue(is_estimated_time_item_code("201234"))
        self.assertFalse(is_estimated_time_item_code("301234"))
        self.assertFalse(is_estimated_time_item_code("10123"))
        self.assertFalse(is_estimated_time_item_code("10AB34"))

    def test_estimated_time_converts_cycle_minutes_to_hours(self):
        self.assertEqual(
            calculate_estimated_manufacturing_time(
                preparation_hours=1.5,
                cycle_minutes=12,
                quantity=10,
            ),
            3.5,
        )

    def test_estimated_time_converts_hours_to_8_hours_25_minutes_workdays(self):
        self.assertEqual(calculate_estimated_manufacturing_days(3.5), 0.42)

    def test_non_matching_item_codes_get_zero_values(self):
        self.assertEqual(
            get_estimated_time_values("301234", 10),
            {
                "temps_de_fabrication_estime": 0,
                "temps_de_fabrication_estime_jours": 0.0,
            },
        )
