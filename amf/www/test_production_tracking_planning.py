"""Integration checks for the independent planning copy; all writes roll back.

Run with an initialized Frappe site (or bench run-tests --module ...).
No fixtures, schema changes, or committed Work Order changes are required.
"""
import unittest
from unittest.mock import patch

import frappe
from frappe.utils import cstr, getdate

from amf.www import production_tracking_planning as api


class TestProductionTrackingPlanning(unittest.TestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")
        self.data = api.get_machining_planning()
        self.row = next((r for r in self.data["rows"] if r.get("docstatus") == 0), None)

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.previous_user)

    def save(self, changes, modified=None, name=None):
        if not self.row:
            self.skipTest("No draft machining Work Order available")
        return api.save_machining_work_order(name or self.row["name"], changes,
                                            modified or self.row["_modified"])

    def test_exact_report_rows_and_columns(self):
        expected_columns = []
        for name in api.REPORT_NAMES:
            columns, rows = frappe.get_doc("Report", name).get_data(limit=0)
            for column in columns:
                if column.fieldname not in expected_columns:
                    expected_columns.append(column.fieldname)
            actual = {r["name"] for r in self.data["rows"] if name in r["_reports"]}
            self.assertEqual(actual, {r[0] for r in rows})
            self.assertEqual(self.data["counts"][name], len(rows))
        self.assertEqual([c["fieldname"] for c in self.data["columns"]], expected_columns)
        self.assertEqual(len(self.data["rows"]), len({r["name"] for r in self.data["rows"]}))

    def test_global_date_order_and_undated_last(self):
        key = lambda r: (not bool(r.get(api.EXPECTED_DATE)), cstr(r.get(api.EXPECTED_DATE)), r["name"])
        self.assertEqual(self.data["rows"], sorted(self.data["rows"], key=key))

    def test_fetch_is_not_limited_to_500(self):
        reports = api._reports()
        config = reports[0][1]
        original_filters = list(config["filters"])
        with patch.object(frappe, "get_list", return_value=[{}] * 501) as query:
            self.assertEqual(len(api._report_rows(config, self.data["columns"])), 501)
            self.assertEqual(query.call_args.kwargs["limit_page_length"], 0)
        self.assertEqual(config["filters"], original_filters)

    def test_save_planning_fields(self):
        result = self.save({"machine": "PLANNING-ROLLBACK-TEST", "raw_material": "ROLLBACK-TEST"})
        doc = frappe.get_doc("Work Order", result["name"])
        self.assertEqual(doc.machine, "PLANNING-ROLLBACK-TEST")
        self.assertEqual(doc.raw_material, "ROLLBACK-TEST")
        self.assertNotEqual(result["modified"], self.row["_modified"])

    def test_expected_date_save_reorders_rows(self):
        self.save({api.EXPECTED_DATE: "2099-12-31"})
        dated = [r for r in api.get_machining_planning()["rows"] if r.get(api.EXPECTED_DATE)]
        self.assertEqual(dated[-1]["name"], self.row["name"])
        self.assertEqual(getdate(dated[-1][api.EXPECTED_DATE]), getdate("2099-12-31"))

    def test_quantity_save_recalculates_estimate(self):
        from amf.amf.utils.work_order_estimated_time import get_estimated_time_values
        self.save({"qty": self.row["qty"] + 1})
        doc = frappe.get_doc("Work Order", self.row["name"])
        expected = get_estimated_time_values(doc.production_item, doc.qty)
        self.assertEqual(doc.qty, self.row["qty"] + 1)
        self.assertEqual(doc.temps_de_fabrication_estime_jours, expected["temps_de_fabrication_estime_jours"])

    def test_qc_save_removes_row_from_reports(self):
        self.save({"progress": "QC"})
        self.assertNotIn(self.row["name"], {r["name"] for r in api.get_machining_planning()["rows"]})

    def test_stale_save_rejected(self):
        with self.assertRaises(frappe.TimestampMismatchError):
            self.save({"machine": "STALE"}, modified="2000-01-01 00:00:00")

    def test_protected_and_unreported_fields_rejected(self):
        for fieldname in ("name", "docstatus", "item_name", "rd_code", "temps_de_fabrication_estime_jours", "company"):
            with self.subTest(fieldname=fieldname), self.assertRaises(frappe.PermissionError):
                self.save({fieldname: "forbidden"})

    def test_invalid_values_rejected(self):
        for changes in ({"priority": "1.5"}, {"qty": "NaN"}, {"qty": "Infinity"},
                        {"progress": "Invalid"}, {api.EXPECTED_DATE: "bad date"}, {"qty": 0}):
            with self.subTest(changes=changes), self.assertRaises(frappe.ValidationError):
                self.save(changes)

    def test_out_of_report_save_rejected(self):
        self.save({"progress": "QC"})
        modified = frappe.db.get_value("Work Order", self.row["name"], "modified")
        with self.assertRaises(frappe.ValidationError):
            self.save({"machine": "OUTSIDE"}, modified=modified)

    def test_guest_and_missing_read_permission_denied(self):
        frappe.set_user("Guest")
        for method in (api.get_machining_planning, api.get_work_orders, api.get_shipments, api.get_note):
            with self.subTest(method=method.__name__), self.assertRaises(frappe.PermissionError):
                method()
        frappe.set_user("Administrator")
        with patch.object(frappe, "has_permission", return_value=False), self.assertRaises(frappe.PermissionError):
            api.get_machining_planning()

    def test_read_only_user_gets_no_editable_cells(self):
        original_permission = frappe.has_permission
        def has_permission(doctype, permission="read", *args, **kwargs):
            if doctype == "Work Order" and permission == "write":
                return False
            return original_permission(doctype, permission, *args, **kwargs)
        with patch.object(frappe, "has_permission", side_effect=has_permission):
            data = api.get_machining_planning()
            self.assertTrue(all(not row["_editable_fields"] for row in data["rows"]))

    def test_duplicated_overview_methods(self):
        orders = api.get_work_orders()
        self.assertIn("ongoing", orders)
        self.assertIn("upcoming", orders)
        for order in orders["ongoing"] + orders["upcoming"]:
            self.assertIn("timer_info", order)
            self.assertIn(order.operation_type, ("Assemblage", "Usinage"))
        for shipment in api.get_shipments():
            self.assertIn(shipment.shipment_status, ("green", "white", "orange"))

    def test_note_save_and_stale_conflict(self):
        note = api.get_note()
        if not note["can_write"]:
            self.skipTest("No writable draft production note")
        saved = api.save_note("PLANNING NOTE ROLLBACK TEST", modified=note["modified"])
        self.assertEqual(api.get_note()["text"], "PLANNING NOTE ROLLBACK TEST")
        self.assertTrue(saved["modified"])
        with self.assertRaises(frappe.TimestampMismatchError):
            api.save_note("STALE", modified="2000-01-01 00:00:00")

    def test_submitted_fields_respect_allow_on_submit(self):
        if not self.row:
            self.skipTest("No machining row")
        row = frappe._dict(self.row, docstatus=1, modified=self.row["_modified"])
        editable = api._serialize_row(row, self.data["columns"])["_editable_fields"]
        self.assertEqual(set(editable), {"priority", "progress"})

    def test_disabled_or_unauthorized_report_denied(self):
        report = frappe.get_doc("Report", api.REPORT_NAMES[0])
        with patch.object(type(report), "is_permitted", return_value=False), self.assertRaises(frappe.PermissionError):
            api.get_machining_planning()
        report.disabled = 1
        original_get_doc = frappe.get_doc
        def get_doc(*args, **kwargs):
            return report if args == ("Report", api.REPORT_NAMES[0]) else original_get_doc(*args, **kwargs)
        with patch.object(frappe, "get_doc", side_effect=get_doc), self.assertRaises(frappe.ValidationError):
            api.get_machining_planning()
