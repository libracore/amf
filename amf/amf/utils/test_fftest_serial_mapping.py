import unittest

from frappe import ValidationError, _dict

from amf.www.fftest_master_debug import (
    _build_p202_finished_serial,
    _needs_material_transfer,
    _parse_debug_batch_list,
    _validate_p202_finished_serial,
    _work_order_has_capacity,
)


class TestFFTestSerialMapping(unittest.TestCase):
    def test_short_supplier_serial_is_zero_padded(self):
        self.assertEqual(
            _build_p202_finished_serial("0070"),
            "P202-O00000070",
        )

    def test_long_supplier_serial_is_zero_padded(self):
        self.assertEqual(
            _build_p202_finished_serial("2639020"),
            "P202-O02639020",
        )

    def test_finished_serial_format_is_validated(self):
        self.assertEqual(
            _validate_p202_finished_serial("P202-O02639020"),
            "P202-O02639020",
        )
        for invalid_serial in (
            "P202-O2639020",
            "P202-O0000000A",
            "P201-O02639020",
        ):
            with self.subTest(serial_no=invalid_serial):
                with self.assertRaises(ValidationError):
                    _validate_p202_finished_serial(invalid_serial)

    def test_source_serial_must_fit_eight_numeric_digits(self):
        for invalid_serial in ("", "12A4", "123456789"):
            with self.subTest(serial_no=invalid_serial):
                with self.assertRaises(ValidationError):
                    _build_p202_finished_serial(invalid_serial)

    def test_debug_batch_list_accepts_json_or_list(self):
        expected = [{"batch_no": "BATCH-1", "quantity": "1"}]
        self.assertEqual(_parse_debug_batch_list(expected), expected)
        self.assertEqual(
            _parse_debug_batch_list('[{"batch_no":"BATCH-1","quantity":"1"}]'),
            expected,
        )

    def test_debug_batch_list_rejects_invalid_json(self):
        with self.assertRaises(ValidationError):
            _parse_debug_batch_list("not-json")

    def test_debug_batch_list_rejects_non_array_json(self):
        with self.assertRaises(ValidationError):
            _parse_debug_batch_list('{"batch_no":"BATCH-1"}')

    def test_work_order_capacity_requires_an_active_remaining_unit(self):
        available = _dict(
            status="In Process",
            qty=2,
            produced_qty=1,
            material_transferred_for_manufacturing=1,
        )
        self.assertTrue(_work_order_has_capacity(available))

        available.produced_qty = 2
        self.assertFalse(_work_order_has_capacity(available))
        available.produced_qty = 1
        available.status = "Completed"
        self.assertFalse(_work_order_has_capacity(available))

    def test_transfer_is_based_on_next_unit_not_full_work_order(self):
        work_order = _dict(
            qty=4,
            produced_qty=1,
            material_transferred_for_manufacturing=1,
            wip_step=0,
            wip_warehouse="Work In Progress - AMF21",
        )
        self.assertTrue(_needs_material_transfer(work_order))

        work_order.material_transferred_for_manufacturing = 2
        self.assertFalse(_needs_material_transfer(work_order))

    def test_wip_step_manufactures_from_main_stock_without_transfer(self):
        work_order = _dict(
            qty=1,
            produced_qty=0,
            material_transferred_for_manufacturing=0,
            wip_step=1,
            wip_warehouse="Work In Progress - AMF21",
        )
        self.assertFalse(_needs_material_transfer(work_order))


if __name__ == "__main__":
    unittest.main()
