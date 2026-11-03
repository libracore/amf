# -*- coding: utf-8 -*-
"""Stock-coverage regressions using installed V12 code and mocked persistence.

Run from frappe-bench (no site initialization or database writes):
    env/bin/python -m unittest amf.amf.utils.test_work_order_creation -v
"""

from __future__ import unicode_literals

import contextlib
import datetime
import io
import unittest
from unittest.mock import Mock, call, patch

import frappe
from amf.amf.utils import work_order_creation as planning


class TestMagnetStockCoverage(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.conf = {}
        self.db_patch = patch.object(frappe, "db", self.db)
        self.conf_patch = patch.object(frappe, "conf", self.conf)
        self.db_patch.start()
        self.conf_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.conf_patch.stop)

    def tearDown(self):
        self.db.commit.assert_not_called()

    def stock_rows(self, balances):
        return [
            frappe._dict(item_code=code, actual_qty=qty)
            for code, qty in balances.items()
        ]

    def test_exact_counterpart_preserves_numeric_and_alphanumeric_suffixes(self):
        for item, counterpart in (
            ("100040", "110040"),
            ("200040", "210040"),
            ("100ABC", "110ABC"),
            ("20AB34", "21AB34"),
        ):
            with self.subTest(item=item):
                self.assertEqual(planning._get_magnet_sub_assembly_item_code(item), counterpart)

    def test_other_families_and_invalid_codes_do_not_expand(self):
        for item in (None, "", "110040", "210040", "300040", "10004", "1000400",
                     "10AB_4", "10ab34", "/10040", "100040-P"):
            with self.subTest(item=item):
                self.assertIsNone(planning._get_magnet_sub_assembly_item_code(item))

    def test_config_switch_accepts_v12_set_config_string_and_integer_values(self):
        for value in (0, "0"):
            with self.subTest(value=value):
                self.conf["machining_include_magnet_stock"] = value
                self.assertIsNone(planning._get_magnet_sub_assembly_item_code("100040"))
        for value in (1, "1"):
            with self.subTest(value=value):
                self.conf["machining_include_magnet_stock"] = value
                self.assertEqual(planning._get_magnet_sub_assembly_item_code("100040"), "110040")

    def test_bulk_coverage_sums_only_the_exact_counterpart_once(self):
        self.db.sql.return_value = self.stock_rows({
            "100040": 2, "110040": 8, "200040": 3, "210040": 4,
            "110041": 100, "210041": 100, "300040": 5,
        })
        self.assertEqual(
            planning._get_stock_balance_for_items(["100040", "200040", "300040"]),
            {"100040": 10, "200040": 7, "300040": 5},
        )
        self.db.sql.assert_called_once()
        query, params = self.db.sql.call_args[0]
        self.assertIn("SUM(actual_qty)", query)
        self.assertIn("warehouse IN %(warehouses)s", query)
        self.assertEqual(set(params["item_codes"]),
                         {"100040", "110040", "200040", "210040", "300040"})
        self.assertEqual(params["warehouses"], planning.MACHINING_STOCK_WAREHOUSES)

    def test_empty_item_list_does_not_query_database(self):
        self.assertEqual(planning._get_stock_balance_for_items([]), {})
        self.db.sql.assert_not_called()

    def test_missing_counterpart_or_all_bins_means_zero_additional_stock(self):
        self.db.sql.return_value = self.stock_rows({"100040": 2})
        self.assertEqual(planning._get_stock_balance_for_items(["100040"]), {"100040": 2})
        self.db.sql.return_value = []
        self.assertEqual(planning._get_stock_balance_for_items(["100040"]), {"100040": 0})

    def test_negative_counterpart_does_not_increase_production_shortage(self):
        self.db.sql.return_value = self.stock_rows({"100040": 2, "110040": -3})
        self.assertEqual(planning.get_stock_balance("100040"), 2)

    def test_negative_base_stock_retains_its_existing_effect(self):
        self.db.sql.return_value = self.stock_rows({"100040": -3, "110040": 2})
        self.assertEqual(planning.get_stock_balance("100040"), -1)

    def test_counterpart_does_not_expand_back_to_machining_stock(self):
        self.db.sql.return_value = self.stock_rows({"110040": 2})
        self.assertEqual(planning.get_stock_balance("110040"), 2)
        self.assertEqual(self.db.sql.call_args[0][1]["item_codes"], ("110040",))

    def test_custom_warehouse_scope_is_preserved_for_both_items(self):
        self.db.sql.return_value = []
        planning.get_stock_balance("100040", warehouse=("Assemblies - AMF21",))
        params = self.db.sql.call_args[0][1]
        self.assertEqual(params["warehouses"], ("Assemblies - AMF21",))
        self.assertEqual(set(params["item_codes"]), {"100040", "110040"})

    def test_switch_restores_base_only_bulk_and_reorder_stock(self):
        self.conf["machining_include_magnet_stock"] = "0"
        self.db.sql.return_value = self.stock_rows({"100040": 2, "110040": 8})
        self.assertEqual(planning.get_stock_balance("100040"), 2)
        self.assertEqual(self.db.sql.call_args[0][1]["item_codes"], ("100040",))

    def run_sales_order_planner(self, item="100040", quantities=(10,), managed=None,
                                supply=None, dry_run=1):
        sources = [frappe._dict(
            source_item_code=item, source_qty=qty, shipping_date="2026-11-20",
            company="Advanced Microfluidics SA", sales_order="SO-{0}".format(index),
        ) for index, qty in enumerate(quantities)]
        key = (item, "Advanced Microfluidics SA")
        with patch.object(planning, "nowdate", return_value="2026-11-03"), \
                patch.object(planning, "_get_sales_order_bom_sources", return_value=sources), \
                patch.object(planning, "_get_open_work_orders_by_item",
                             return_value={key: supply or []}) as open_orders, \
                patch.object(planning, "_get_managed_draft_machining_work_orders_by_key",
                             return_value={key: managed or []}), \
                patch.object(planning, "_get_default_boms_for_items",
                             return_value={item: "BOM-" + item}), \
                patch.object(frappe, "delete_doc") as delete_doc, \
                patch.object(frappe, "new_doc") as new_doc, \
                patch.object(planning, "_create_or_update_draft_machining_work_order",
                             return_value=(frappe._dict(name="TEST-WO"), "create", [])) as write:
            result = planning.plan_machining_work_orders_from_sales_orders(
                dry_run=dry_run, commit=0,
            )
            open_orders.assert_called_once_with([item])
            delete_doc.assert_not_called()
            new_doc.assert_not_called()
            if dry_run or not result["created_count"]:
                write.assert_not_called()
            else:
                self.assertEqual(write.call_args[1]["row"]["work_order_qty"],
                                 result["planned"][0]["qty"])
            return result

    def test_planner_full_coverage_suppresses_creation_for_both_families(self):
        for item, counterpart in (("100040", "110040"), ("200040", "210040")):
            with self.subTest(item=item):
                self.db.sql.return_value = self.stock_rows({item: 0, counterpart: 10})
                result = self.run_sales_order_planner(item=item, dry_run=0)
                self.assertEqual(result["created_count"], 0)
                self.assertEqual(result["planned"][0]["shortage_qty"], 0)

    def test_planner_partial_coverage_buffers_only_remaining_shortage(self):
        self.db.sql.return_value = self.stock_rows({"100040": 2, "110040": 3})
        result = self.run_sales_order_planner(dry_run=0)
        row = result["planned"][0]
        self.assertEqual((row["gross_required_qty"], row["covered_qty"],
                          row["shortage_qty"], row["qty"]), (10, 5, 5, 6))

    def test_planner_without_counterpart_stock_keeps_original_shortage(self):
        self.db.sql.return_value = self.stock_rows({"100040": 2})
        row = self.run_sales_order_planner()["planned"][0]
        self.assertEqual((row["covered_qty"], row["shortage_qty"], row["qty"]), (2, 8, 10))

    def test_alphanumeric_counterpart_stock_covers_planner_demand(self):
        self.db.sql.return_value = self.stock_rows({"20AB34": 0, "21AB34": 10})
        result = self.run_sales_order_planner(item="20AB34", dry_run=0)
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["planned"][0]["covered_qty"], 10)

    def test_planner_full_coverage_previews_existing_managed_draft_deletion(self):
        self.db.sql.return_value = self.stock_rows({"100040": 2, "110040": 8})
        result = self.run_sales_order_planner(managed=[frappe._dict(name="EXISTING-WO")])
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["deleted_count"], 1)
        self.assertEqual(result["deleted"][0]["work_order"], "EXISTING-WO")

    def test_planner_aggregates_sales_orders_without_reusing_counterpart_stock(self):
        self.db.sql.return_value = self.stock_rows({"100040": 2, "110040": 7})
        result = self.run_sales_order_planner(quantities=(6, 6))
        self.assertEqual(result["demand_count"], 1)
        row = result["planned"][0]
        self.assertEqual((row["gross_required_qty"], row["covered_qty"],
                          row["shortage_qty"], row["qty"]), (12, 9, 3, 4))

    def test_planner_retains_due_base_work_orders_and_excludes_late_supply(self):
        self.db.sql.return_value = self.stock_rows({"100040": 2, "110040": 3})
        result = self.run_sales_order_planner(supply=[
            {"remaining_qty": 2, "due_date": datetime.date(2026, 11, 12)},
            {"remaining_qty": 100, "due_date": datetime.date(2026, 11, 14)},
        ])
        row = result["planned"][0]
        self.assertEqual((row["covered_qty"], row["shortage_qty"], row["qty"]), (7, 3, 4))

    def test_switch_restores_base_only_sales_order_planning(self):
        self.conf["machining_include_magnet_stock"] = 0
        self.db.sql.return_value = self.stock_rows({"100040": 2, "110040": 8})
        row = self.run_sales_order_planner()["planned"][0]
        self.assertEqual((row["covered_qty"], row["shortage_qty"], row["qty"]), (2, 8, 10))

    def run_reorder_check(self, item, base_qty, magnet_qty):
        self.db.sql.side_effect = lambda query, *args, **kwargs: (
            [frappe._dict(name=item, reorder_level=10)] if "FROM `tabItem`" in query
            else self.stock_rows({item: base_qty,
                                  ("11" if item.startswith("10") else "21") + item[2:]: magnet_qty})
        )
        with patch.object(planning, "process_bom_and_create_work_orders") as create, \
                patch.object(planning, "delete_draft_wo") as delete, \
                contextlib.redirect_stdout(io.StringIO()):
            planning.create_work_orders_based_on_reorder_levels()
            return create, delete

    def test_reorder_full_counterpart_stock_suppresses_creation_for_both_families(self):
        for item in ("100040", "200040"):
            with self.subTest(item=item):
                create, delete = self.run_reorder_check(item, 0, 10)
                create.assert_not_called()
                delete.assert_called_once_with(item)

    def test_reorder_partial_coverage_passes_only_the_shortage_to_creation(self):
        create, delete = self.run_reorder_check("100040", 2, 3)
        create.assert_called_once_with("100040", 5)
        delete.assert_not_called()

    def test_switch_restores_base_only_reorder_creation_decision(self):
        self.conf["machining_include_magnet_stock"] = 0
        create, delete = self.run_reorder_check("100040", 2, 8)
        create.assert_called_once_with("100040", 8)
        delete.assert_not_called()

    def run_legacy_check(self, item="100040", base_qty=2, magnet_qty=8, exists=True):
        work_order = frappe._dict(name="PARENT-WO", sales_order="TEST-SO", bom_no="TEST-BOM",
                                 required_items=[frappe._dict(item_code=item, required_qty=10)])
        self.db.exists.side_effect = lambda doctype, *args: exists if doctype == "Item" else True
        with patch.object(frappe, "get_doc", return_value=work_order), \
                patch.object(frappe, "get_all", return_value=[{"item_code": item, "qty": 1}]), \
                patch.object(planning, "get_stock", side_effect=[
                    [{"actual_qty": base_qty}], [{"actual_qty": magnet_qty}],
                ]) as stock, \
                patch.object(planning, "create_work_orders_for_missing_items") as create, \
                contextlib.redirect_stdout(io.StringIO()):
            result = planning.check_and_create_work_orders(work_order)
            return result, stock, create

    def test_legacy_full_coverage_suppresses_creation_for_both_families(self):
        for item, counterpart in (("100040", "110040"), ("200040", "210040")):
            with self.subTest(item=item):
                result, stock, create = self.run_legacy_check(item=item)
                self.assertEqual(result, {"missing_items": []})
                self.assertEqual(stock.call_args_list, [call(item), call(counterpart)])
                create.assert_not_called()

    def test_legacy_partial_coverage_creates_only_remaining_quantity(self):
        result, stock, create = self.run_legacy_check(magnet_qty=3)
        self.assertEqual(result, {"missing_items": [{"item_code": "100040", "qty": 5}]})
        create.assert_called_once_with(result["missing_items"], "TEST-SO")

    def test_legacy_negative_counterpart_stock_does_not_increase_shortage(self):
        result, stock, create = self.run_legacy_check(magnet_qty=-3)
        self.assertEqual(result["missing_items"], [{"item_code": "100040", "qty": 8}])
        create.assert_called_once_with(result["missing_items"], "TEST-SO")

    def test_legacy_missing_counterpart_item_does_not_call_get_stock_for_it(self):
        result, stock, create = self.run_legacy_check(exists=False)
        self.assertEqual(result["missing_items"], [{"item_code": "100040", "qty": 8}])
        stock.assert_called_once_with("100040")
        create.assert_called_once_with(result["missing_items"], "TEST-SO")

    def test_switch_restores_base_only_legacy_check(self):
        self.conf["machining_include_magnet_stock"] = "0"
        result, stock, create = self.run_legacy_check()
        self.assertEqual(result["missing_items"], [{"item_code": "100040", "qty": 8}])
        stock.assert_called_once_with("100040")
        create.assert_called_once_with(result["missing_items"], "TEST-SO")


if __name__ == "__main__":
    unittest.main()
