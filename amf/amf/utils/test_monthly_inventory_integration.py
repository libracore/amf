"""Opt-in v12 database tests. All records and stock/GL entries are rolled back.

Initialize/connect Frappe first, set AMF_INVENTORY_DB_TESTS=1, then run this
module with unittest. Never run concurrently with another inventory test suite.
"""
import os
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import frappe
from amf.amf.utils import monthly_inventory as inventory


@unittest.skipUnless(os.environ.get("AMF_INVENTORY_DB_TESTS") == "1", "Opt-in database suite")
class TestMonthlyInventoryIntegration(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.sql("SAVEPOINT monthly_inventory_test")
        self.addCleanup(self.rollback)
        # v12 delete_doc enqueues a synchronous cleanup job under in_test; that
        # job commits. Keep cleanup jobs inside this test's rollback boundary.
        self.jobs = patch.object(frappe, "enqueue")
        self.jobs.start()
        self.addCleanup(self.jobs.stop)
        self.commits = patch.object(frappe.db, "commit", side_effect=AssertionError("Unexpected commit during inventory test"))
        self.commits.start()
        self.addCleanup(self.commits.stop)
        self.names = patch.object(inventory, "check_name", return_value="MIC-TEST-" + uuid4().hex)
        self.names.start()
        self.addCleanup(self.names.stop)
        self.company = frappe.defaults.get_global_default("company")
        self.assertTrue(self.company)
        self.warehouse = frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "Inventory test " + uuid4().hex[:10],
            "company": self.company, "is_group": 0,
            "parent_warehouse": inventory.production_root(self.company).name,
            "account": frappe.db.get_value("Company", self.company, "default_inventory_account")}).insert()
        references = frappe.db.sql("""SELECT name FROM tabItem
            WHERE disabled=0 AND is_stock_item=1 AND has_variants=0
            AND has_batch_no=0 AND has_serial_no=0
            AND item_group!='Product'
            AND (end_of_life IS NULL OR end_of_life >= %s)
            AND NOT EXISTS (SELECT 1 FROM `tabMonthly Inventory Check Row` r
                JOIN `tabMonthly Inventory Check` c ON c.name=r.parent
                WHERE r.item_code=tabItem.name AND c.company=%s AND c.status!='Passed')
            ORDER BY name LIMIT 10""", (frappe.utils.nowdate(), self.company))
        self.assertEqual(len(references), 10)
        settings = frappe.get_single(inventory.SETTINGS)
        settings.company, settings.enabled = self.company, 0
        settings.assigned_to = inventory.DEFAULT_ASSIGNEE
        settings.minimum_items, settings.maximum_items = 10, 10
        self.references = [code for (code,) in references]
        settings.set("item_groups", [{"item_group": group.name,
            "enabled": inventory.default_group_enabled(group.name)} for group in inventory.get_inventory_item_groups()])
        settings.set("excluded_items", [])
        settings.save()
        # Keep posting fixtures deterministic while exercising real group-based
        # eligibility; randomness is covered in the unit suite.
        def select(candidates):
            self.assertTrue(set(self.references).issubset(candidates))
            return self.references
        self.selection = patch.object(inventory, "choose_references", side_effect=select)
        self.selection.start()
        self.addCleanup(self.selection.stop)
        self.mail = patch.object(frappe, "sendmail")
        self.sendmail = self.mail.start()
        self.addCleanup(self.mail.stop)
        self.actual_warehouses = inventory.warehouses
        self.scope = patch.object(inventory, "warehouses", return_value=[frappe._dict(name=self.warehouse.name)])
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.name = inventory.generate_current_month()

    def rollback(self):
        frappe.set_user("Administrator")
        frappe.db.sql("ROLLBACK TO SAVEPOINT monthly_inventory_test")
        frappe.clear_document_cache(inventory.SETTINGS, inventory.SETTINGS)

    def confirm(self, difference=False):
        doc = frappe.get_doc(inventory.CHECK, self.name)
        for row in doc.rows:
            row.counted = 1
        if difference:
            doc.rows[0].counted_qty, doc.rows[0].counted_rate = 2, 10
            doc.rows[0].reason = "Integration test physical count"
        doc.save()
        return doc

    def test_generation_idempotent_and_assignment_writable(self):
        self.assertEqual(inventory.generate_current_month(), self.name)
        self.assertEqual(self.sendmail.call_count, 1)
        self.assertEqual(frappe.db.count("ToDo", {"reference_type": inventory.CHECK, "reference_name": self.name}), 1)
        doc = frappe.get_doc(inventory.CHECK, self.name)
        self.assertEqual(len(doc.rows), 10)
        frappe.set_user(inventory.DEFAULT_ASSIGNEE)
        self.assertTrue(frappe.has_permission(inventory.CHECK, "write", doc=doc))
        doc.rows[0].counted = 1
        doc.save()
        self.assertEqual(doc.rows[0].checked_by, inventory.DEFAULT_ASSIGNEE)

    def test_item_group_defaults_exclusions_and_disabled_parents(self):
        settings = frappe.get_single(inventory.SETTINGS)
        groups = inventory.get_inventory_item_groups()
        self.assertEqual(len(settings.item_groups), len(groups))
        self.assertEqual([r.item_group for r in settings.item_groups if not r.enabled], ["Product"])
        candidates = set(inventory.get_eligible_references(settings))
        product_items = {r[0] for r in frappe.db.sql("SELECT name FROM tabItem WHERE item_group='Product'")}
        self.assertTrue(candidates.isdisjoint(product_items))
        excluded = self.references[0]
        settings.append("excluded_items", {"item_code": excluded, "reason": "Exclude from cycle count"})
        settings.save()
        self.assertEqual(set(inventory.get_eligible_references(settings)), candidates - {excluded})
        for group in settings.item_groups:
            if group.item_group == "Part":
                group.enabled = 0
        settings.save()
        part_items = {r[0] for r in frappe.db.sql("""SELECT i.name FROM tabItem i
            JOIN `tabItem Group` g ON g.name=i.item_group
            JOIN `tabItem Group` p ON p.name='Part'
            WHERE g.lft>=p.lft AND g.rgt<=p.rgt""")}
        self.assertTrue(set(inventory.get_eligible_references(settings)).isdisjoint(part_items))
        # Synchronization preserves both disabled choices and manual exclusions.
        inventory.synchronize_group_rows(settings, groups)
        settings.save()
        settings.reload()
        self.assertFalse(next(r.enabled for r in settings.item_groups if r.item_group == "Part"))
        self.assertEqual([r.item_code for r in settings.excluded_items], [excluded])
        for group in settings.item_groups:
            if group.item_group == "Product":
                group.enabled = 1
        settings.save()
        self.assertTrue(set(inventory.get_eligible_references(settings)).intersection(product_items))
        self.assertNotIn(excluded, inventory.get_eligible_references(settings))

    def test_disabled_warehouses_are_excluded_and_scope_changes_require_refresh(self):
        # Query real warehouse flags, isolating this policy test from historical
        # stock balances. Ledger posting is covered by the other integration tests.
        with patch.object(inventory, "warehouses", self.actual_warehouses), patch.object(
                inventory, "stock_state", return_value={"qty": 0, "rate": 0, "token": "warehouse-scope-fixture"}):
            inventory.refresh_stock(self.name)
            doc = frappe.get_doc(inventory.CHECK, self.name)
            inventory.ensure_scope(doc)
            self.assertIn(self.warehouse.name, {row.warehouse for row in doc.rows})

            disabled = {r.name for r in frappe.get_all("Warehouse", filters={
                "company": self.company, "disabled": 1}, fields=["name"])}
            self.assertTrue({r.warehouse for r in doc.rows}.isdisjoint(disabled))
            self.warehouse.disabled = 1
            self.warehouse.save()
            self.assertNotIn(self.warehouse.name, {w.name for w in inventory.warehouses(self.company)})
            with self.assertRaisesRegex(frappe.ValidationError, "warehouse scope changed"):
                inventory.ensure_scope(doc)
            inventory.refresh_stock(self.name)
            doc.reload()
            inventory.ensure_scope(doc)
            self.assertNotIn(self.warehouse.name, {row.warehouse for row in doc.rows})
            self.warehouse.disabled = 0
            self.warehouse.save()
            with self.assertRaisesRegex(frappe.ValidationError, "warehouse scope changed"):
                inventory.ensure_scope(doc)
            inventory.refresh_stock(self.name)
            doc.reload()
            inventory.ensure_scope(doc)
            self.assertIn(self.warehouse.name, {row.warehouse for row in doc.rows})

    def test_production_scope_excludes_other_branches(self):
        root = inventory.production_root(self.company)
        parent = frappe.db.get_value("Warehouse", root.name, "parent_warehouse")
        outside = frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "Inventory test outside " + uuid4().hex[:8],
            "company": self.company, "parent_warehouse": parent, "is_group": 0,
            "account": frappe.db.get_value("Company", self.company, "default_inventory_account")}).insert()
        selected = {row.name for row in self.actual_warehouses(self.company)}
        self.assertIn(self.warehouse.name, selected)
        self.assertNotIn(outside.name, selected)
        self.assertNotIn(root.name, selected)
        root = inventory.production_root(self.company)
        for name in selected:
            warehouse = frappe.db.get_value("Warehouse", name, ["lft", "rgt", "disabled", "is_group"], as_dict=True)
            self.assertTrue(root.lft < warehouse.lft < warehouse.rgt < root.rgt)
            self.assertFalse(warehouse.disabled or warehouse.is_group)

    def test_old_batch_is_excluded_even_when_enabled(self):
        old_batch = frappe.db.get_value("Warehouse", {"company": self.company,
            "warehouse_name": "OLD BATCH"}, ["name", "disabled"], as_dict=True)
        if not old_batch:
            self.skipTest("This site has no OLD BATCH warehouse")
        self.assertFalse(old_batch.disabled)
        self.assertNotIn(old_batch.name, {row.name for row in self.actual_warehouses(self.company)})
        with patch.object(inventory, "warehouses", self.actual_warehouses), patch.object(
                inventory, "stock_state", return_value={"qty": 0, "rate": 0, "token": "warehouse-exclusion-fixture"}):
            inventory.refresh_stock(self.name)
            doc = frappe.get_doc(inventory.CHECK, self.name)
            self.assertNotIn(old_batch.name, {row.warehouse for row in doc.rows})
            inventory.ensure_scope(doc)

    def test_actual_random_generation_selects_exactly_ten_eligible_references(self):
        settings = frappe.get_single(inventory.SETTINGS)
        settings.append("excluded_items", {"item_code": self.references[0]})
        settings.save()
        self.selection.stop()
        with patch.object(inventory, "check_name", return_value="MIC-TEST-RANDOM-" + uuid4().hex), patch.object(
                inventory, "stock_state", return_value={"qty": 0, "rate": 0, "token": "selection-fixture"}):
            name = inventory.generate_current_month()
        doc = frappe.get_doc(inventory.CHECK, name)
        selected = json.loads(doc.selected_items)
        self.assertEqual(len(selected), 10)
        self.assertEqual(len(set(selected)), 10)
        self.assertEqual(len(doc.rows), 10)
        self.assertTrue(set(selected).issubset(inventory.get_eligible_references(settings)))
        self.assertTrue(set(selected).isdisjoint(self.references))

    def test_refresh_prefills_actual_quantity_and_latest_warehouse_valuation(self):
        doc = frappe.get_doc(inventory.CHECK, self.name)
        code = doc.rows[0].item_code
        for qty, rate in ((7, 12.75), (5, 22.5)):
            reco = frappe.get_doc({"doctype": "Stock Reconciliation", "company": self.company,
                "purpose": "Stock Reconciliation", "posting_date": frappe.utils.nowdate(),
                "posting_time": frappe.utils.nowtime(), "set_posting_time": 1,
                "items": [{"item_code": code, "warehouse": self.warehouse.name,
                           "qty": qty, "valuation_rate": rate}]}).insert()
            reco.submit()
            inventory.refresh_stock(self.name)
            doc.reload()
            line = next(row for row in doc.rows if row.item_code == code)
            self.assertEqual((line.current_qty, line.current_rate), (qty, rate))
            self.assertEqual((line.counted_qty, line.counted_rate), (qty, rate))
            self.assertFalse(line.counted)
            self.assertEqual(line.current_qty, frappe.db.get_value("Bin", {
                "item_code": code, "warehouse": self.warehouse.name}, "actual_qty"))

    def test_no_difference_check_passes_and_closes_assignment(self):
        self.confirm()
        inventory.complete_check(self.name)
        doc = frappe.get_doc(inventory.CHECK, self.name)
        self.assertEqual(doc.status, "Passed")
        self.assertTrue(doc.completed_on)
        self.assertEqual(frappe.db.get_value("ToDo", {"reference_type": inventory.CHECK,
            "reference_name": self.name}, "status"), "Closed")
        with self.assertRaises(frappe.ValidationError):
            doc.notes = "Try editing passed audit"
            doc.save()

    def test_real_reconciliation_ledger_gl_verification_and_cancellation(self):
        self.confirm(difference=True)
        voucher = inventory.create_reconciliation(self.name)
        self.assertEqual(inventory.create_reconciliation(self.name), voucher)
        reco = frappe.get_doc("Stock Reconciliation", voucher)
        self.assertEqual(reco.docstatus, 0)
        self.assertEqual(reco.monthly_inventory_check, self.name)
        self.assertEqual(len(reco.items), 1)
        with self.assertRaises(frappe.ValidationError):
            inventory.complete_check(self.name)
        reco.submit()
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_type": "Stock Reconciliation", "voucher_no": voucher}), 1)
        inventory.complete_check(self.name)
        self.assertEqual(frappe.db.get_value(inventory.CHECK, self.name, "status"), "Passed")
        reco.cancel()
        check = frappe.get_doc(inventory.CHECK, self.name)
        self.assertNotEqual(check.status, "Passed")
        self.assertFalse(check.rows[0].counted)
        self.assertFalse(check.completed_on)
        self.assertEqual(frappe.db.get_value("ToDo", {"reference_type": inventory.CHECK,
            "reference_name": self.name}, "status"), "Open")

    def test_draft_prevents_count_changes_and_can_be_deleted(self):
        doc = self.confirm(difference=True)
        voucher = inventory.create_reconciliation(self.name)
        doc.reload()
        doc.rows[0].counted_qty = 3
        with self.assertRaises(frappe.ValidationError):
            doc.save()
        frappe.delete_doc("Stock Reconciliation", voucher)
        doc.reload()
        self.assertFalse(doc.reconciliation)
        inventory.refresh_stock(self.name)
        doc.reload()
        self.assertTrue(all(not row.counted for row in doc.rows))

    def test_reconciliation_form_submission_serializes_the_http_response(self):
        self.confirm(difference=True)
        voucher = inventory.create_reconciliation(self.name)
        # Cover the real Desk endpoint and response encoder. doc.submit() alone
        # misses datetime.time left by before_submit after field coercion.
        from amf.amf.utils.delivery_note_save import savedocs
        from frappe.utils.response import as_json
        old_response = frappe.local.response
        self.addCleanup(setattr, frappe.local, "response", old_response)
        frappe.local.response = frappe._dict(docs=[])
        frappe.set_user(inventory.DEFAULT_ASSIGNEE)
        reco = frappe.get_doc("Stock Reconciliation", voucher)
        savedocs(reco.as_json(), "Submit")
        response = as_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        payload = json.loads(response.get_data(as_text=True))
        saved = next(doc for doc in payload["docs"] if doc["doctype"] == "Stock Reconciliation")
        self.assertEqual(saved["name"], voucher)
        self.assertEqual(saved["docstatus"], 1)
        self.assertIsInstance(saved["posting_time"], str)
        self.assertEqual(frappe.db.get_value("Stock Reconciliation", voucher, "docstatus"), 1)

    def test_form_json_roundtrip_and_manual_correction(self):
        doc = self.confirm(difference=True)
        source = doc.rows[0]
        # A normal, batch/serial-aware voucher can be linked after it is posted.
        # Use an ordinary item here to exercise real ledger/accounting posting
        # without manufacturing a batch or serial identity in the live site.
        reco = frappe.get_doc({"doctype": "Stock Reconciliation", "company": self.company,
            "purpose": "Stock Reconciliation", "posting_date": frappe.utils.nowdate(),
            "posting_time": frappe.utils.nowtime(), "set_posting_time": 1,
            "items": [{"item_code": source.item_code, "warehouse": source.warehouse,
                       "qty": source.counted_qty, "valuation_rate": source.counted_rate}]}).insert()
        reco.submit()
        data = json.loads(frappe.as_json(doc.as_dict()))
        data["rows"][0]["correction_type"] = "Stock Reconciliation"
        data["rows"][0]["correction_document"] = reco.name
        from_form = frappe.get_doc(data)
        from_form.save()
        self.assertEqual(str(from_form.rows[0].checked_on), str(source.checked_on))
        inventory.complete_check(self.name)
        self.assertEqual(frappe.db.get_value(inventory.CHECK, self.name, "status"), "Passed")
