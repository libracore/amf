import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from amf.amf.utils import stock_entry as stock_entry_utils


class TestStockEntryRepair(unittest.TestCase):
	def _make_row(self, **overrides):
		values = {
			"item_code": "ITEM-001",
			"s_warehouse": None,
			"t_warehouse": None,
			"batch_no": None,
			"serial_no": "",
			"auto_batch_no_generation": 0,
		}
		values.update(overrides)
		return SimpleNamespace(**values)

	def _make_stock_entry(self, **overrides):
		values = {
			"name": "STE-TEST",
			"docstatus": 1,
			"purpose": "Manufacture",
			"value_difference": 120.0,
			"naming_series": "STE-",
			"posting_date": "2024-02-23",
			"posting_time": "10:00:00",
			"remarks": None,
			"items": [],
		}
		values.update(overrides)
		return SimpleNamespace(**values)

	def test_non_serialized_repair_still_skips_serialized_entries(self):
		original = self._make_stock_entry(
			items=[self._make_row(serial_no="SER-0001")],
		)

		with patch.object(stock_entry_utils.frappe, "get_doc", return_value=original):
			result = stock_entry_utils._repair_manufacture_stock_entry(
				original.name,
				dry_run=1,
				cancel_original=1,
			)

		self.assertEqual(result["status"], "skipped")
		self.assertIn("repair_serialized_manufacture_stock_entries", result["reason"])

	def test_serialized_repair_dry_run_returns_candidate(self):
		original = self._make_stock_entry(
			items=[self._make_row(serial_no="SER-0001")],
			value_difference=75.0,
		)
		duplicate = self._make_stock_entry(
			name=None,
			items=[self._make_row(serial_no="SER-0001")],
			value_difference=0.0,
		)

		with patch.object(stock_entry_utils.frappe, "get_doc", return_value=original), patch.object(
			stock_entry_utils,
			"_prepare_repair_duplicate",
			return_value=duplicate,
		):
			result = stock_entry_utils._repair_serialized_manufacture_stock_entry(
				original.name,
				dry_run=1,
				cancel_original=1,
			)

		self.assertEqual(result["status"], "dry_run")
		self.assertEqual(result["repair_strategy"], "serialized_cancel_first")
		self.assertAlmostEqual(result["repaired_value_difference"], 0.0, places=2)

	def test_serialized_live_path_cancels_original_before_submitting_duplicate(self):
		call_order = []
		original = self._make_stock_entry(
			items=[self._make_row(serial_no="SER-0001")],
		)
		original.cancel = Mock(side_effect=lambda: call_order.append("cancel"))
		duplicate = self._make_stock_entry(
			name="STE-REPAIRED",
			items=[self._make_row(serial_no="SER-0001")],
		)
		result = {"status": "ready", "repair_strategy": "serialized_cancel_first"}
		mock_frappe = SimpleNamespace(db=SimpleNamespace(commit=Mock()))

		with patch.object(
			stock_entry_utils,
			"_prepare_live_repair_environment",
			return_value=([], 0),
		), patch.object(
			stock_entry_utils,
			"_restore_live_repair_environment",
		), patch.object(
			stock_entry_utils,
			"_submit_repair_duplicate",
			side_effect=lambda doc, bypass_work_order_update=True: call_order.append(
				"submit:{0}".format(bypass_work_order_update)
			),
		) as submit_duplicate, patch.object(
			stock_entry_utils,
			"frappe",
			mock_frappe,
		):
			live_result = stock_entry_utils._run_live_repair_cancel_first(
				original,
				duplicate,
				result,
			)

		self.assertEqual(call_order, ["cancel", "submit:False"])
		submit_duplicate.assert_called_once_with(duplicate, bypass_work_order_update=False)
		self.assertEqual(live_result["status"], "cancelled_original")
		self.assertEqual(live_result["duplicate_name"], "STE-REPAIRED")
		mock_frappe.db.commit.assert_called_once_with()

	def test_problematic_manufacture_wrapper_defaults_to_dry_run_without_results(self):
		mock_rows = [SimpleNamespace(name="STE-0001"), SimpleNamespace(name="STE-0002")]

		with patch.object(stock_entry_utils.frappe, "get_all", return_value=mock_rows) as get_all, patch.object(
			stock_entry_utils,
			"repair_manufacture_stock_entries",
			return_value=[{"stock_entry": "STE-0001", "status": "dry_run"}],
		) as repair_entries:
			result = stock_entry_utils.repair_problematic_manufacture_stock_entries()

		filters = get_all.call_args.kwargs["filters"]
		self.assertIn(["Stock Entry", "posting_date", ">=", "2024-01-01"], filters)
		self.assertEqual(result["dry_run"], 1)
		self.assertEqual(result["to_date"], None)
		self.assertEqual(result["results"], [])
		repair_entries.assert_called_once_with(
			["STE-0001", "STE-0002"],
			dry_run=True,
			cancel_original=True,
		)

	def test_problematic_serialized_wrapper_orders_by_posting_date_and_defaults_to_dry_run(self):
		mock_rows = [SimpleNamespace(name="STE-1001")]
		mock_frappe = SimpleNamespace(
			db=SimpleNamespace(sql=Mock(return_value=mock_rows)),
			utils=stock_entry_utils.frappe.utils,
		)

		with patch.object(
			stock_entry_utils,
			"frappe",
			mock_frappe,
		), patch.object(
			stock_entry_utils,
			"repair_serialized_manufacture_stock_entries",
			return_value=[{"stock_entry": "STE-1001", "status": "dry_run"}],
		) as repair_entries:
			result = stock_entry_utils.repair_problematic_serialized_manufacture_stock_entries()

		query = mock_frappe.db.sql.call_args.args[0]
		self.assertIn("order by se.posting_date asc, se.name asc", query.lower())
		self.assertEqual(result["dry_run"], 1)
		self.assertEqual(result["to_date"], None)
		self.assertEqual(result["results"], [])
		repair_entries.assert_called_once_with(
			["STE-1001"],
			dry_run=True,
			cancel_original=True,
		)
