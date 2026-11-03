# -*- coding: utf-8 -*-
"""Manual machining assignment tests; no site, network or real messages needed."""

from __future__ import unicode_literals

import json
import unittest
from unittest.mock import Mock, patch

import frappe
from amf import hooks
from amf.amf.utils import manual_work_order_assignment as alerts


class TestManualMachiningWorkOrderAssignment(unittest.TestCase):
    def setUp(self):
        self.doc = frappe._dict(
            doctype="Work Order", name="TEST-MANUAL-WO", production_item="100040",
            qty=10, owner="planner@example.invalid", flags=frappe._dict(), reload=Mock(),
        )
        self.db = Mock()
        self.db.exists.side_effect = lambda doctype, filters: doctype == "User"
        self.form = frappe._dict(cmd=alerts.DESK_SAVE_COMMAND, doc=json.dumps({
            "doctype": "Work Order", "production_item": self.doc.production_item,
        }))
        self.flags = frappe._dict()
        self.conf = frappe._dict()
        self.session = frappe._dict(user="planner@example.invalid")
        for name, value in (("db", self.db), ("form_dict", self.form), ("flags", self.flags),
                            ("conf", self.conf), ("session", self.session)):
            context = patch.object(frappe, name, value)
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(alerts.assign_to, "add")
        self.assign = context.start()
        self.addCleanup(context.stop)

    def tearDown(self):
        self.db.commit.assert_not_called()

    def run_hook(self):
        alerts.assign_manual_machining_work_order(self.doc, "after_insert")

    def select_item(self, code):
        self.doc.production_item = code
        self.form.doc = json.dumps({"doctype": "Work Order", "production_item": code})

    def test_first_manual_save_assigns_martin_and_requests_native_email(self):
        self.run_hook()
        self.assign.assert_called_once()
        args = self.assign.call_args[0][0]
        self.assertEqual(args["assign_to"], "martin.barraud@amf.ch")
        self.assertIsInstance(args["assign_to"], str)  # V12 expects one user, not a list.
        self.assertEqual((args["doctype"], args["name"], args["notify"]),
                         ("Work Order", self.doc.name, 1))
        for detail in (self.doc.name, "100040", "10", self.doc.owner):
            self.assertIn(detail, args["description"])
        self.doc.reload.assert_called_once_with()

    def test_both_families_and_alphanumeric_suffixes_are_included(self):
        for code in ("100040", "200040", "100ABC", "20AB34"):
            with self.subTest(code=code):
                self.assign.reset_mock()
                self.select_item(code)
                self.run_hook()
                self.assign.assert_called_once()

    def test_other_families_and_non_exact_codes_are_excluded(self):
        for code in (None, "", "110040", "210040", "300040", "10004", "1000400",
                     "10ab34", "10AB_4", "100040\n", "100040-P"):
            with self.subTest(code=code):
                self.select_item(code)
                self.run_hook()
        self.assign.assert_not_called()
        self.db.exists.assert_not_called()

    def test_other_document_types_are_excluded(self):
        self.doc.doctype = "Sales Order"
        self.run_hook()
        self.assign.assert_not_called()

    def test_supported_manual_create_actions_are_included(self):
        for command in alerts.MANUAL_CREATION_COMMANDS:
            with self.subTest(command=command):
                self.assign.reset_mock()
                self.form.cmd = command
                self.run_hook()
                self.assign.assert_called_once()

    def test_manual_production_plan_work_order_action_is_included(self):
        for command in alerts.DOCUMENT_METHOD_COMMANDS:
            with self.subTest(command=command):
                self.assign.reset_mock()
                self.form.update({"cmd": command, "method": "make_work_order",
                                  "docs": json.dumps({"doctype": "Production Plan"})})
                self.run_hook()
                self.assign.assert_called_once()

    def test_unrelated_document_method_actions_are_excluded(self):
        for doctype, method in (("Production Plan", "save"), ("Sales Order", "make_work_order")):
            with self.subTest(doctype=doctype, method=method):
                self.form.update({"cmd": "runserverobj", "method": method, "docs": {"doctype": doctype}})
                self.run_hook()
        self.assign.assert_not_called()

    def test_scheduler_and_unrelated_api_commands_are_excluded(self):
        for command in (None, "", "frappe.client.insert", "frappe.client.save",
                        "amf.amf.utils.work_order_creation.plan_machining_work_orders_from_sales_orders",
                        "amf.amf.utils.work_order_creation.check_and_create_work_orders",
                        "amf.amf.utils.sales_order_utils.create_work_orders_for_sales_order"):
            with self.subTest(command=command):
                self.form.cmd = command
                self.run_hook()
        self.assign.assert_not_called()
        self.db.exists.assert_not_called()

    def test_nested_insert_while_saving_a_different_document_is_excluded(self):
        for requested in ({"doctype": "Sales Order", "production_item": "100040"},
                          {"doctype": "Work Order", "production_item": "200040"}):
            self.form.doc = json.dumps(requested)
            self.run_hook()
        self.assign.assert_not_called()

    def test_missing_or_invalid_request_payload_is_excluded(self):
        for payload in (None, "", "invalid JSON", "null", "[]", "42", []):
            with self.subTest(payload=payload):
                self.form.doc = payload
                self.run_hook()
        self.assign.assert_not_called()

    def test_desk_save_accepts_a_parsed_request_document(self):
        self.form.doc = {"doctype": "Work Order", "production_item": "100040"}
        self.run_hook()
        self.assign.assert_called_once()

    def test_manual_duplicate_of_planner_order_is_still_manual(self):
        self.doc.auto_gen = 1
        self.run_hook()
        self.assign.assert_called_once()

    def test_global_and_document_import_install_and_patch_flags_suppress_alerts(self):
        for flags in (self.flags, self.doc.flags):
            for flag in ("in_import", "in_patch", "in_install", "in_migrate"):
                with self.subTest(flag=flag):
                    flags[flag] = True
                    self.run_hook()
                    flags.pop(flag)
        self.assign.assert_not_called()
        self.db.exists.assert_not_called()

    def test_guest_and_missing_users_are_excluded(self):
        for user in ("Guest", None, ""):
            self.session.user = user
            self.run_hook()
        self.assign.assert_not_called()

    def test_switch_disables_assignment_for_integer_and_string_zero(self):
        for value in (0, "0"):
            self.conf.manual_machining_work_order_alerts_enabled = value
            self.run_hook()
        self.assign.assert_not_called()
        self.db.exists.assert_not_called()

    def test_existing_assignment_is_not_recreated_or_reopened(self):
        self.db.exists.return_value = True
        self.db.exists.side_effect = None
        self.run_hook()
        self.assign.assert_not_called()
        self.db.exists.assert_called_once_with("ToDo", {
            "reference_type": "Work Order", "reference_name": self.doc.name,
            "owner": "martin.barraud@amf.ch",
        })

    def test_invalid_recipient_fails_before_creating_an_assignment(self):
        self.db.exists.side_effect = lambda doctype, filters: False
        with patch.object(frappe, "throw", side_effect=frappe.ValidationError("Invalid assignee")):
            with self.assertRaises(frappe.ValidationError):
                self.run_hook()
        self.assign.assert_not_called()

    def test_description_escapes_user_supplied_html(self):
        self.doc.owner = '<creator@example.invalid>'
        self.run_hook()
        description = self.assign.call_args[0][0]["description"]
        self.assertIn("&lt;creator@example.invalid&gt;", description)
        self.assertNotIn("<creator", description)

    def test_hook_runs_after_qr_creation_and_only_on_insert(self):
        work_order_hooks = hooks.doc_events["Work Order"]
        self.assertEqual(work_order_hooks["after_insert"], [
            "amf.amf.utils.on_work_order_submit.generate_wo_qr",
            "amf.amf.utils.manual_work_order_assignment.assign_manual_machining_work_order",
        ])
        self.assertNotIn("manual_work_order_assignment", str(work_order_hooks["on_update"]))


if __name__ == "__main__":
    unittest.main()
