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

	def _make_amount_row(self, **overrides):
		values = {
			"name": "ROW-001",
			"idx": 1,
			"item_code": "ITEM-001",
			"s_warehouse": None,
			"t_warehouse": None,
			"qty": 1.0,
			"transfer_qty": 1.0,
			"conversion_factor": 1.0,
			"basic_rate": 0.0,
			"basic_amount": 0.0,
			"additional_cost": 0.0,
			"amount": 0.0,
			"valuation_rate": 0.0,
			"serial_no": "",
			"batch_no": None,
		}
		values.update(overrides)
		row = SimpleNamespace(**values)
		row.precision = lambda fieldname: {
			"amount": 2,
			"basic_amount": 2,
			"basic_rate": 6,
			"valuation_rate": 6,
			"qty": 6,
			"transfer_qty": 6,
		}.get(fieldname, 6)
		return row

	def _make_value_stock_entry(self, rows, additional_costs=None, **overrides):
		entry = SimpleNamespace(
			name="STE-VALUE",
			doctype="Stock Entry",
			docstatus=1,
			purpose="Manufacture",
			work_order=None,
			bom_no="BOM-001",
			fg_completed_qty=1.0,
			posting_date="2024-02-23",
			posting_time="10:00:00",
			production_item="FG-001",
			total_incoming_value=0.0,
			total_outgoing_value=0.0,
			value_difference=0.0,
			total_amount=0.0,
			items=rows,
			additional_costs=additional_costs or [],
		)
		for key, value in overrides.items():
			setattr(entry, key, value)

		def get(fieldname):
			return getattr(entry, fieldname, None)

		def precision(fieldname):
			return {
				"value_difference": 2,
				"total_incoming_value": 2,
				"total_outgoing_value": 2,
				"fg_completed_qty": 6,
			}.get(fieldname, 6)

		def distribute_additional_costs():
			entry.total_additional_costs = sum(stock_entry_utils.flt(row.amount) for row in entry.additional_costs)
			total_basic_amount = sum(
				stock_entry_utils.flt(row.basic_amount)
				for row in entry.items
				if row.t_warehouse
			)
			for row in entry.items:
				if row.t_warehouse and total_basic_amount:
					row.additional_cost = (
						stock_entry_utils.flt(row.basic_amount) / total_basic_amount
					) * entry.total_additional_costs
				else:
					row.additional_cost = 0.0

		def update_valuation_rate():
			for row in entry.items:
				if row.transfer_qty:
					row.amount = stock_entry_utils.flt(
						stock_entry_utils.flt(row.basic_amount) + stock_entry_utils.flt(row.additional_cost),
						row.precision("amount"),
					)
					row.valuation_rate = stock_entry_utils.flt(
						stock_entry_utils.flt(row.basic_rate)
						+ (stock_entry_utils.flt(row.additional_cost) / stock_entry_utils.flt(row.transfer_qty)),
						row.precision("valuation_rate"),
					)

		def set_total_incoming_outgoing_value():
			entry.total_incoming_value = 0.0
			entry.total_outgoing_value = 0.0
			for row in entry.items:
				if row.t_warehouse:
					entry.total_incoming_value += stock_entry_utils.flt(row.amount)
				if row.s_warehouse:
					entry.total_outgoing_value += stock_entry_utils.flt(row.amount)
			entry.value_difference = entry.total_incoming_value - entry.total_outgoing_value

		entry.get = get
		entry.precision = precision
		entry.distribute_additional_costs = distribute_additional_costs
		entry.update_valuation_rate = update_valuation_rate
		entry.set_total_incoming_outgoing_value = set_total_incoming_outgoing_value
		entry.set_total_amount = Mock()
		return entry

	def test_balanced_manufacture_qty_recalculation_offsets_additional_costs(self):
		raw = self._make_amount_row(
			name="RAW",
			idx=1,
			item_code="RAW-001",
			s_warehouse="WIP - AMF21",
			transfer_qty=2,
			basic_rate=50,
		)
		scrap = self._make_amount_row(
			name="SCRAP",
			idx=2,
			item_code="SCRAP-001",
			t_warehouse="Scrap - AMF21",
			basic_rate=10,
		)
		finished_good = self._make_amount_row(
			name="FG",
			idx=3,
			item_code="FG-001",
			t_warehouse="Main Stock - AMF21",
			basic_rate=999,
		)
		stock_entry = self._make_value_stock_entry(
			[raw, scrap, finished_good],
			additional_costs=[SimpleNamespace(amount=5)],
		)

		with patch.object(
			stock_entry_utils.frappe,
			"get_system_settings",
			return_value="Banker's Rounding (legacy)",
		), patch.object(
			stock_entry_utils,
			"_is_scrap_row",
			side_effect=lambda doc, row: row.item_code == "SCRAP-001",
		):
			result = stock_entry_utils._recalculate_stock_entry_amounts_from_existing_rates(
				stock_entry,
				balance_value_difference=True,
			)

		self.assertEqual(result["status"], "balanced")
		self.assertAlmostEqual(stock_entry.total_incoming_value, 100.0, places=2)
		self.assertAlmostEqual(stock_entry.total_outgoing_value, 100.0, places=2)
		self.assertAlmostEqual(stock_entry.value_difference, 0.0, places=2)
		self.assertAlmostEqual(finished_good.basic_amount, 85.0, places=2)

	def test_balanced_manufacture_qty_recalculation_blocks_negative_fg_amount(self):
		raw = self._make_amount_row(
			name="RAW",
			idx=1,
			item_code="RAW-001",
			s_warehouse="WIP - AMF21",
			basic_rate=10,
		)
		scrap = self._make_amount_row(
			name="SCRAP",
			idx=2,
			item_code="SCRAP-001",
			t_warehouse="Scrap - AMF21",
			basic_rate=9,
		)
		finished_good = self._make_amount_row(
			name="FG",
			idx=3,
			item_code="FG-001",
			t_warehouse="Main Stock - AMF21",
			basic_rate=10,
		)
		stock_entry = self._make_value_stock_entry(
			[raw, scrap, finished_good],
			additional_costs=[SimpleNamespace(amount=5)],
		)

		with patch.object(
			stock_entry_utils.frappe,
			"get_system_settings",
			return_value="Banker's Rounding (legacy)",
		), patch.object(
			stock_entry_utils,
			"_is_scrap_row",
			side_effect=lambda doc, row: row.item_code == "SCRAP-001",
		):
			result = stock_entry_utils._recalculate_stock_entry_amounts_from_existing_rates(
				stock_entry,
				balance_value_difference=True,
			)

		self.assertEqual(result["status"], "blocked")
		self.assertIn("negative", result["message"])

	def test_correct_submitted_manufacture_qty_allows_blank_qty_for_balance_only_preview(self):
		raw = self._make_amount_row(
			name="RAW",
			idx=1,
			item_code="RAW-001",
			s_warehouse="WIP - AMF21",
			basic_rate=100,
		)
		finished_good = self._make_amount_row(
			name="FG",
			idx=2,
			item_code="FG-001",
			t_warehouse="Main Stock - AMF21",
			basic_rate=95,
		)
		stock_entry = self._make_value_stock_entry(
			[raw, finished_good],
			total_incoming_value=95,
			total_outgoing_value=100,
			value_difference=-5,
		)
		frappe_module = stock_entry_utils.frappe
		mock_frappe = SimpleNamespace(
			only_for=Mock(),
			db=SimpleNamespace(exists=Mock(return_value=True)),
			get_doc=Mock(return_value=stock_entry),
			utils=frappe_module.utils,
			throw=frappe_module.throw,
		)

		with patch.object(frappe_module, "get_system_settings", return_value="Banker's Rounding (legacy)"), patch.object(
			stock_entry_utils,
			"frappe",
			mock_frappe,
		), patch.object(
			stock_entry_utils,
			"_get_manufacture_production_item",
			return_value="FG-001",
		), patch.object(
			stock_entry_utils,
			"_is_scrap_row",
			return_value=False,
		):
			result = stock_entry_utils.correct_submitted_manufacture_qty(
				"STE-VALUE",
				None,
				dry_run=True,
				update_work_order_qty=False,
			)

		self.assertEqual(result["status"], "dry_run")
		self.assertEqual(result["quantity_will_update"], 0)
		self.assertAlmostEqual(result["new_fg_completed_qty"], 1.0, places=2)
		self.assertAlmostEqual(result["value_difference_after"], 0.0, places=2)

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

	def test_align_serial_no_warehouses_for_cancel_uses_target_warehouses(self):
		stock_entry = self._make_stock_entry(
			items=[
				self._make_row(t_warehouse="Main Stock - AMF21", serial_no="SER-0001\nSER-0002"),
				self._make_row(s_warehouse="Source - AMF21", serial_no="RAW-0001"),
				self._make_row(t_warehouse="Finished Goods - AMF21", serial_no="SER-0003, SER-0004"),
			],
		)
		mock_frappe = SimpleNamespace(db=SimpleNamespace(set_value=Mock()))

		with patch.object(stock_entry_utils, "frappe", mock_frappe):
			warehouse_by_serial = stock_entry_utils._align_serial_no_warehouses_for_cancel(stock_entry)

		self.assertEqual(
			warehouse_by_serial,
			{
				"SER-0001": "Main Stock - AMF21",
				"SER-0002": "Main Stock - AMF21",
				"SER-0003": "Finished Goods - AMF21",
				"SER-0004": "Finished Goods - AMF21",
			},
		)
		self.assertEqual(mock_frappe.db.set_value.call_count, 4)

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
			"_get_stock_entry_serial_numbers",
			return_value=["SER-0001"],
		), patch.object(
			stock_entry_utils,
			"_capture_serial_no_state",
			side_effect=lambda serial_numbers: call_order.append("snapshot") or {
				"SER-0001": {"warehouse": "Stores - AMF21"}
			},
		), patch.object(
			stock_entry_utils,
			"_align_serial_no_warehouses_for_cancel",
			side_effect=lambda doc: call_order.append("align") or {
				"SER-0001": "Main Stock - AMF21"
			},
		), patch.object(
			stock_entry_utils,
			"_prepare_live_repair_environment",
			return_value=([], 0),
		), patch.object(
			stock_entry_utils,
			"_restore_live_repair_environment",
		), patch.object(
			stock_entry_utils,
			"_restore_serial_no_state",
			side_effect=lambda serial_state: call_order.append("restore"),
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

		self.assertEqual(call_order, ["snapshot", "align", "cancel", "submit:False", "restore"])
		submit_duplicate.assert_called_once_with(duplicate, bypass_work_order_update=False)
		self.assertEqual(live_result["status"], "cancelled_original")
		self.assertEqual(live_result["duplicate_name"], "STE-REPAIRED")
		self.assertEqual(live_result["temporarily_aligned_serial_count"], 1)
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
