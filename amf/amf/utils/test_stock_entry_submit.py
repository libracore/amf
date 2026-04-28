import unittest

import frappe
from frappe.utils import flt, now

from erpnext.manufacturing.doctype.work_order.test_work_order import make_wo_order_test_record
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry as make_work_order_stock_entry
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry as make_basic_stock_entry


class TestStockEntrySubmit(unittest.TestCase):
	def _seed_source_stock(self, work_order, source_warehouse):
		item_codes = sorted({row.item_code for row in work_order.required_items})
		for item_code in item_codes:
			make_basic_stock_entry(
				item_code=item_code,
				target=source_warehouse,
				qty=10,
				basic_rate=100,
			)

	def _submit_material_transfer(self, work_order, qty, source_warehouse):
		transfer = frappe.get_doc(
			make_work_order_stock_entry(work_order.name, "Material Transfer for Manufacture", qty)
		)
		for row in transfer.items:
			if row.s_warehouse:
				row.s_warehouse = source_warehouse
		transfer.insert()
		transfer.submit()

	def _submit_with_stale_fg_rate(self, work_order, multiplier):
		manufacture = frappe.get_doc(
			make_work_order_stock_entry(work_order.name, "Manufacture", 1)
		)
		fg_row = next(
			row for row in manufacture.items if row.item_code == work_order.production_item and row.t_warehouse
		)
		correct_basic_rate = flt(fg_row.basic_rate)
		stale_basic_rate = flt(correct_basic_rate * multiplier)
		fg_row.basic_rate = stale_basic_rate
		fg_row.basic_amount = stale_basic_rate * flt(fg_row.qty)
		fg_row.amount = fg_row.basic_amount
		fg_row.valuation_rate = stale_basic_rate

		manufacture.submit()

		submitted = frappe.get_doc("Stock Entry", manufacture.name)
		submitted_fg_row = next(
			row for row in submitted.items if row.item_code == work_order.production_item and row.t_warehouse
		)
		return submitted, submitted_fg_row, correct_basic_rate, stale_basic_rate

	def test_submit_recalculates_stale_fg_rate_after_wip_transfer(self):
		source_warehouse = "_Test Warehouse 2 - _TC"
		work_order = make_wo_order_test_record(
			do_not_save=True,
			qty=4,
			source_warehouse=source_warehouse,
			planned_start_date=now(),
		)
		work_order.skip_transfer = 0
		work_order.insert()
		work_order.submit()

		self._seed_source_stock(work_order, source_warehouse)
		self._submit_material_transfer(work_order, 4, source_warehouse)

		submitted, fg_row, correct_basic_rate, stale_basic_rate = self._submit_with_stale_fg_rate(
			work_order,
			work_order.qty,
		)

		self.assertAlmostEqual(flt(submitted.value_difference), 0.0, places=2)
		self.assertAlmostEqual(flt(fg_row.basic_rate), correct_basic_rate, places=2)
		self.assertNotAlmostEqual(flt(fg_row.basic_rate), stale_basic_rate, places=2)

	def test_submit_recalculates_stale_fg_rate_for_skip_transfer_work_order(self):
		source_warehouse = "_Test Warehouse 2 - _TC"
		work_order = make_wo_order_test_record(
			qty=4,
			source_warehouse=source_warehouse,
			planned_start_date=now(),
		)

		self._seed_source_stock(work_order, source_warehouse)

		submitted, fg_row, correct_basic_rate, stale_basic_rate = self._submit_with_stale_fg_rate(
			work_order,
			work_order.qty,
		)

		self.assertAlmostEqual(flt(submitted.value_difference), 0.0, places=2)
		self.assertAlmostEqual(flt(fg_row.basic_rate), correct_basic_rate, places=2)
		self.assertNotAlmostEqual(flt(fg_row.basic_rate), stale_basic_rate, places=2)
