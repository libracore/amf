"""Opt-in concurrency regression tests using disposable copies of MIC tables.

These tests commit only isolated test-table data, never operational MICs or
stock. Run in a separate Frappe process with AMF_INVENTORY_CONCURRENCY_TESTS=1.
"""
import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import frappe
from amf.amf.utils import monthly_inventory as inventory


@unittest.skipUnless(os.environ.get("AMF_INVENTORY_CONCURRENCY_TESTS") == "1", "Opt-in concurrency suite")
class TestMonthlyInventoryConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = frappe.local.site
        cls.sites_path = os.path.dirname(frappe.get_site_path())
        suffix = uuid4().hex[:12]
        cls.parent_table = "__amf_mic_lock_" + suffix + "_parent"
        cls.child_table = "__amf_mic_lock_" + suffix + "_child"
        cls.connection = frappe.db.get_connection()
        with cls.connection.cursor() as cursor:
            cursor.execute("CREATE TABLE `{0}` LIKE `tabMonthly Inventory Check`".format(cls.parent_table))
            cursor.execute("CREATE TABLE `{0}` LIKE `tabMonthly Inventory Check Row`".format(cls.child_table))
        cls.connection.commit()
        cls.company = frappe.defaults.get_global_default("company")
        cls.root = inventory.production_root(cls.company).name
        cls.warehouse = inventory.warehouses(cls.company)[0].name
        cls.item = frappe.db.sql("""SELECT name, stock_uom FROM tabItem
            WHERE disabled=0 AND is_stock_item=1 AND has_variants=0
            ORDER BY name LIMIT 1""", as_dict=True)[0]

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()
        try:
            with cls.connection.cursor() as cursor:
                cursor.execute("DROP TABLE IF EXISTS `{0}`".format(cls.child_table))
                cursor.execute("DROP TABLE IF EXISTS `{0}`".format(cls.parent_table))
        finally:
            cls.connection.close()

    def setUp(self):
        frappe.db.rollback()
        self.stamp = datetime(2026, 10, 23, 12)
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM `{0}`".format(self.child_table))
            cursor.execute("DELETE FROM `{0}`".format(self.parent_table))
            for label in ("A", "B"):
                name = "MIC-LOCK-" + label
                doc = frappe.get_doc({"doctype": inventory.CHECK, "name": name,
                    "owner": "Administrator", "modified_by": "Administrator",
                    "creation": self.stamp, "modified": self.stamp, "docstatus": 0,
                    "company": self.company, "warehouse_root": self.root,
                    "period": "2026-10-01", "assigned_to": "Administrator",
                    "due_date": "2026-10-15", "status": "In Progress",
                    "selected_items": json.dumps([self.item.name]), "selection_log": "{}",
                    "reference_count": 1, "total_rows": 1, "checked_rows": 0,
                    "rows": [{"name": "MIC-LOCK-ROW-" + label, "parent": name,
                        "parenttype": inventory.CHECK, "parentfield": "rows", "idx": 1,
                        "owner": "Administrator", "creation": self.stamp, "modified": self.stamp,
                        "modified_by": "Administrator", "item_code": self.item.name,
                        "warehouse": self.warehouse, "stock_uom": self.item.stock_uom,
                        "current_qty": 0, "current_rate": 0, "counted_qty": 0,
                        "counted_rate": 0, "counted": 0, "row_status": "Pending",
                        "snapshot_on": self.stamp, "ledger_token": "isolated-fixture"}]})
                self._insert(cursor, self.parent_table, doc.get_valid_dict())
                self._insert(cursor, self.child_table, doc.rows[0].get_valid_dict())
        self.connection.commit()
        frappe.db.rollback()

    @staticmethod
    def _insert(cursor, table, values):
        keys = list(values)
        cursor.execute("INSERT INTO `{0}` ({1}) VALUES ({2})".format(table,
            ",".join("`" + key + "`" for key in keys), ",".join(["%s"] * len(keys))),
            [values[key] for key in keys])

    def _redirect_queries(self):
        original = frappe.db.sql

        def isolated_sql(query, *args, **kwargs):
            query = query.replace("`tabMonthly Inventory Check`", "`" + self.parent_table + "`")
            query = query.replace("`tabMonthly Inventory Check Row`", "`" + self.child_table + "`")
            return original(query, *args, **kwargs)

        frappe.db.sql = isolated_sql
        return original

    def _save_worker(self, label, barrier, legacy=False):
        frappe.init(site=self.site, sites_path=self.sites_path)
        frappe.connect()
        frappe.set_user("Administrator")
        try:
            self._redirect_queries()
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout=5")
            name = "MIC-LOCK-" + label
            # Each writer owns its document and one child before both validate.
            # The old full-table child lock then creates a deterministic cycle.
            frappe.db.sql("SELECT name FROM `tabMonthly Inventory Check` WHERE name=%s FOR UPDATE", name)
            frappe.db.sql("SELECT name FROM `tabMonthly Inventory Check Row` WHERE name=%s FOR UPDATE", "MIC-LOCK-ROW-" + label)
            barrier.wait(timeout=10)
            if legacy:
                frappe.db.sql("""SELECT * FROM `tabMonthly Inventory Check Row` IGNORE INDEX (parent)
                    WHERE parent=%s AND parenttype=%s ORDER BY idx FOR UPDATE""", (name, inventory.CHECK))
            doc = inventory.load_locked_check(name)
            doc.notes = "Concurrent save " + label
            doc.rows[0].reason = "Saved by " + label
            doc.flags.ignore_version = True
            doc.notify_update = lambda: None
            doc.save()
            frappe.db.commit()
            return "saved"
        except Exception as error:
            frappe.db.rollback()
            return error
        finally:
            frappe.destroy()

    def _pair(self, legacy=False):
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self._save_worker, label, barrier, legacy) for label in ("A", "B")]
            return [future.result(timeout=25) for future in futures]

    def test_previous_table_scan_reproduces_deadlock_in_isolated_tables(self):
        results = self._pair(legacy=True)
        self.assertTrue(any(isinstance(r, Exception) and r.args and r.args[0] == 1213
                            for r in results), results)

    def test_two_documents_save_concurrently_without_cross_document_locks(self):
        self.assertEqual(self._pair(), ["saved", "saved"])
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT notes FROM `{0}` ORDER BY name".format(self.parent_table))
            self.assertEqual([r[0] for r in cursor.fetchall()], ["Concurrent save A", "Concurrent save B"])
            cursor.execute("SELECT reason FROM `{0}` ORDER BY name".format(self.child_table))
            self.assertEqual([r[0] for r in cursor.fetchall()], ["Saved by A", "Saved by B"])

    def test_newer_parent_cannot_be_paired_with_old_snapshot_children(self):
        original = self._redirect_queries()
        try:
            # Establish this transaction's repeatable-read snapshot.
            frappe.db.sql("SELECT modified FROM `tabMonthly Inventory Check` WHERE name=%s", "MIC-LOCK-A")
            with self.connection.cursor() as cursor:
                cursor.execute("UPDATE `{0}` SET modified=%s WHERE name=%s".format(self.parent_table),
                               (self.stamp + timedelta(seconds=1), "MIC-LOCK-A"))
                cursor.execute("UPDATE `{0}` SET reason='newer count' WHERE parent=%s".format(self.child_table), "MIC-LOCK-A")
            self.connection.commit()
            with self.assertRaises(frappe.TimestampMismatchError):
                inventory.load_locked_check("MIC-LOCK-A")
        finally:
            frappe.db.rollback()
            frappe.db.sql = original
