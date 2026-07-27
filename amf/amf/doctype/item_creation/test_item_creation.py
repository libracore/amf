# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and Contributors
# See license.txt
from __future__ import unicode_literals

import unittest

from amf.amf.doctype.item_creation.item_creation import (
    build_bom_managed_item_code,
    get_bom_managed_family_codes,
    get_next_available_bom_managed_suffix,
    get_sub_assembly_item_code_for_component,
    suggest_bom_managed_item_code,
)


class FakeDB(object):
    def __init__(self, items=None, existing_codes=None):
        self.items = items or {}
        self.existing_codes = set(existing_codes or [])

    def get_value(self, doctype, name, fields, as_dict=False):
        if doctype != "Item":
            return None
        row = self.items.get(name)
        if not row:
            return None
        if isinstance(fields, (list, tuple)):
            return {field: row.get(field) for field in fields}
        return row.get(fields)

    def exists(self, doctype, name):
        return doctype == "Item" and name in self.existing_codes

    def sql(self, query, values=None, as_dict=False):
        values = values or {}
        item_group = values.get("item_group")
        tag_raw_mat = values.get("tag_raw_mat")
        sub_assembly_prefix = values.get("sub_assembly_prefix")
        rows = []
        for item_code, row in self.items.items():
            if row.get("item_group") != item_group:
                continue
            if row.get("disabled"):
                continue
            if tag_raw_mat and row.get("tag_raw_mat") != tag_raw_mat:
                continue
            sub_assembly_item_code = sub_assembly_prefix + item_code[2:]
            if sub_assembly_item_code in self.existing_codes:
                continue
            rows.append({
                "item_code": item_code,
                "item_name": row.get("item_name"),
                "tag_raw_mat": row.get("tag_raw_mat"),
                "reference_code": row.get("reference_code"),
                "sub_assembly_item_code": sub_assembly_item_code,
            })
        return rows


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

    def test_sub_assembly_code_reuses_component_suffix(self):
        self.assertEqual(
            get_sub_assembly_item_code_for_component("Valve Seat", "200123"),
            "210123",
        )
        self.assertEqual(
            get_sub_assembly_item_code_for_component("Plug", "100123"),
            "110123",
        )

    def test_sub_assembly_suggestion_can_reuse_existing_component(self):
        fake_db = FakeDB(
            items={
                "200123": {
                    "item_code": "200123",
                    "item_name": "SEAT-D-1-8-100-C",
                    "item_group": "Valve Seat",
                    "tag_raw_mat": "PEEK",
                    "reference_code": "RVM.1234-C",
                    "disabled": 0,
                },
            },
            existing_codes={"200123"},
        )
        from amf.amf.doctype.item_creation import item_creation

        original_db = item_creation.frappe.db
        item_creation.frappe.db = fake_db
        try:
            suggestion = suggest_bom_managed_item_code(
                "Valve Seat",
                has_bom=1,
                tag_raw_mat="PEEK",
                reuse_component_item="200123",
            )
        finally:
            item_creation.frappe.db = original_db

        self.assertEqual(suggestion["item_code"], "210123")
        self.assertEqual(suggestion["family_suffix"], "0123")
        self.assertEqual(suggestion["reuse_component_item"], "200123")
        self.assertEqual(suggestion["tag_raw_mat"], "PEEK")

    def test_existing_sub_assembly_blocks_component_reuse(self):
        fake_db = FakeDB(
            items={
                "200123": {
                    "item_code": "200123",
                    "item_name": "SEAT-D-1-8-100-C",
                    "item_group": "Valve Seat",
                    "tag_raw_mat": "PEEK",
                    "reference_code": "RVM.1234-C",
                    "disabled": 0,
                },
            },
            existing_codes={"200123", "210123"},
        )
        from amf.amf.doctype.item_creation import item_creation

        original_db = item_creation.frappe.db
        item_creation.frappe.db = fake_db
        try:
            with self.assertRaises(Exception):
                suggest_bom_managed_item_code(
                    "Valve Seat",
                    has_bom=1,
                    tag_raw_mat="PEEK",
                    reuse_component_item="200123",
                )
        finally:
            item_creation.frappe.db = original_db
