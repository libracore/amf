# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and Contributors
# See license.txt
from __future__ import unicode_literals

import unittest

from amf.amf.doctype.item_creation.item_creation import (
    build_bom_managed_item_code,
    get_bom_managed_family_codes,
    get_next_available_bom_managed_suffix,
)


class TestItemCreation(unittest.TestCase):
    def test_build_bom_managed_item_code_for_each_family(self):
        self.assertEqual(build_bom_managed_item_code("Plug", "0042", item_type="Component"), "100042")
        self.assertEqual(build_bom_managed_item_code("Plug", "0042", item_type="Sub-Assembly"), "110042")
        self.assertEqual(build_bom_managed_item_code("Valve Seat", "0042", item_type="Component"), "200042")
        self.assertEqual(build_bom_managed_item_code("Valve Seat", "0042", item_type="Sub-Assembly"), "210042")
        self.assertEqual(build_bom_managed_item_code("Valve Head", "0042", item_type="Component"), "300042")
        self.assertEqual(build_bom_managed_item_code("Valve Head", "0042", item_type="Sub-Assembly"), "300042")

    def test_family_codes_share_the_same_suffix(self):
        self.assertEqual(
            get_bom_managed_family_codes("1234"),
            {
                "plug_component": "101234",
                "plug_sub_assembly": "111234",
                "seat_component": "201234",
                "seat_sub_assembly": "211234",
                "head": "301234",
            },
        )

    def test_next_available_suffix_starts_at_0001(self):
        self.assertEqual(get_next_available_bom_managed_suffix([]), "0001")

    def test_next_available_suffix_fills_the_first_full_gap(self):
        existing_codes = [
            "100001",
            "110001",
            "200001",
            "210001",
            "300001",
            "100003",
            "110003",
            "200003",
            "210003",
            "300003",
        ]
        self.assertEqual(get_next_available_bom_managed_suffix(existing_codes), "0002")

    def test_partially_used_suffix_is_never_reused(self):
        existing_codes = [
            "100001",
            "110001",
            "200001",
            "210001",
            "300001",
            "100002",
        ]
        self.assertEqual(get_next_available_bom_managed_suffix(existing_codes), "0003")
