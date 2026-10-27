"""Run with env/bin/python -m unittest amf.amf.utils.test_monthly_inventory."""
import random
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import frappe
from amf.amf.utils import monthly_inventory as inventory


def row(**values):
    result = frappe._dict(name="R1", item_code="ITEM", warehouse="WH", stock_uom="Nos",
        counted=1, counted_qty=5.0, counted_rate=10.0, current_qty=5.0, current_rate=10.0,
        reason="", row_status="Matched", resolved=0, tracked_item=0,
        checked_on=datetime(2026, 10, 1, 8), checked_by="counter@example.com",
        ledger_token="baseline", correction_type=None, correction_document=None)
    result.update(values)
    return result


class Doc(frappe._dict):
    def __getattribute__(self, key):
        if key == "items" and key in self:
            return self[key]
        return super().__getattribute__(key)

    def is_new(self):
        return False

    def check_permission(self, *args):
        pass

    def save(self, **kwargs):
        pass

    def add_comment(self, *args):
        pass


def document(**values):
    result = Doc(name="MIC", company="AMF", assigned_to="counter@example.com",
                 status="In Progress", reconciliation=None, rows=[row()])
    result.update(values)
    return result


class Settings(SimpleNamespace):
    def append(self, field, values):
        getattr(self, field).append(frappe._dict(values))

    def get_doc_before_save(self):
        return getattr(self, "previous", None)


def settings(**values):
    defaults = dict(enabled=0, company="AMF", sample_size=10, minimum_items=10, maximum_items=10,
        due_day=15, assigned_to="counter@example.com", item_groups=[], excluded_items=[])
    defaults.update(values)
    return Settings(**defaults)


GROUPS = [frappe._dict(name=name, parent_item_group=parent) for name, parent in (
    ("All Item Groups", ""), ("Product", "All Item Groups"), ("Product Child", "Product"),
    ("Part", "All Item Groups"), ("Fasteners", "Part"), ("New Group", "All Item Groups"))]


class TestMonthlyInventory(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(inventory, "_", side_effect=lambda text: text),
                        patch.object(frappe, "local", frappe._dict()),
                        patch.object(frappe, "get_system_settings", return_value="Banker's Rounding"),
                        patch.object(inventory, "nowdate", return_value="2026-10-23"),
                        patch.object(inventory, "production_root", return_value=frappe._dict(name="Production - AMF21", lft=2, rgt=20)),
                        patch.object(frappe, "session", frappe._dict(user="counter@example.com")),
                        patch.object(frappe, "db", MagicMock())]
        for mock in self.patches:
            mock.start()
        self.addCleanup(lambda: [mock.stop() for mock in reversed(self.patches)])
        frappe.db.get_value.return_value = 0

    @staticmethod
    def throw(message, *args, **kwargs):
        raise frappe.ValidationError(message)

    def test_sample_is_exactly_ten_unique_and_reproducible_under_injected_rng(self):
        candidates = ["I{0}".format(i) for i in range(30)]
        for seed in range(80):
            chosen = inventory.choose_references(candidates, rng=random.Random(seed))
            self.assertEqual(len(chosen), 10)
            self.assertEqual(len(chosen), len(set(chosen)))
            self.assertEqual(chosen, inventory.choose_references(candidates, rng=random.Random(seed)))

    def test_pool_of_ten_selects_all_references_once(self):
        candidates = ["I{0}".format(i) for i in range(10)]
        self.assertEqual(set(inventory.choose_references(candidates)), set(candidates))

    def test_random_samples_vary_and_are_not_limited_to_first_ten(self):
        candidates = ["I{0}".format(i) for i in range(12)]
        samples = {tuple(inventory.choose_references(candidates, rng=random.Random(i))) for i in range(20)}
        self.assertGreater(len(samples), 15)

    def test_all_candidates_can_be_selected(self):
        candidates, seen = list(range(37)), set()
        for seed in range(80):
            chosen = inventory.choose_references(candidates, rng=random.Random(seed))
            seen.update(chosen)
        self.assertEqual(seen, set(candidates))

    def test_fewer_than_ten_distinct_candidates_fails_instead_of_shrinking_sample(self):
        for size in range(10):
            with self.assertRaises(ValueError):
                inventory.choose_references(list(range(size)) * 2)
        self.assertEqual(len(inventory.choose_references(list(range(10)) * 2)), 10)

    def test_zero_stock_does_not_create_a_meaningless_rate_only_adjustment(self):
        self.assertFalse(inventory.differs(row(current_qty=0, counted_qty=0, counted_rate=100)))
        self.assertTrue(inventory.differs(row(counted_rate=100)))
        self.assertTrue(inventory.differs(row(counted_qty=0)))
        self.assertFalse(inventory.differs(row(counted_qty=5.00000001)))

    def test_invalid_numeric_inputs_are_rejected(self):
        with patch.object(frappe, "throw", side_effect=self.throw):
            for value in (None, "", "bad", -1, float("inf"), float("nan")):
                with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
                    inventory.number(value, "Quantity")
            with self.assertRaises(frappe.ValidationError):
                inventory.number(1e308, "Quantity")
        self.assertEqual(inventory.number(0, "Quantity"), 0)

    def test_ordinary_users_cannot_see_other_assignees_checks(self):
        with patch.object(inventory, "is_manager", return_value=False):
            self.assertFalse(inventory.has_permission(document(), user="other@example.com"))
            self.assertIsNone(inventory.has_permission(document(), user="counter@example.com"))

    def test_snapshot_forgery_and_row_deletion_are_rejected(self):
        old = document()
        changed = document(rows=[row(current_qty=100)])
        with patch.object(inventory, "load_locked_check", return_value=old), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "snapshots"):
                inventory.validate_check(changed)
            with self.assertRaisesRegex(frappe.ValidationError, "added or removed"):
                inventory.validate_check(document(rows=[]))

    def test_status_and_completion_cannot_be_forged(self):
        with patch.object(inventory, "load_locked_check", return_value=document()), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "managed by the system"):
                inventory.validate_check(document(status="Passed"))

    def test_count_confirmation_checks_freshness_and_records_actor(self):
        old, changed = document(rows=[row(counted=0)]), document()
        stamp = datetime(2026, 10, 2, 10)
        with patch.object(inventory, "load_locked_check", return_value=old), patch.object(inventory, "stock_state", return_value={"token": "baseline"}) as balance, patch.object(inventory, "now_datetime", return_value=stamp):
            inventory.validate_check(changed)
            balance.assert_called_once_with("ITEM", "WH")
        self.assertEqual(changed.rows[0].checked_on, stamp)
        self.assertEqual(changed.rows[0].checked_by, "counter@example.com")
        self.assertEqual(changed.checked_rows, 1)

    def test_net_zero_movements_still_invalidate_a_count(self):
        with patch.object(inventory, "load_locked_check", return_value=document(rows=[row(counted=0)])), patch.object(inventory, "stock_state", return_value={"token": "movement"}), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "Stock moved"):
                inventory.validate_check(document())

    def test_linking_a_submitted_correction_preserves_original_count_timestamp(self):
        old = document(rows=[row(counted_qty=4, reason="Missing")])
        changed = document(rows=[row(counted_qty=4, reason="Missing", correction_type="Stock Entry", correction_document="SE-1")])
        with patch.object(inventory, "load_locked_check", return_value=old), patch.object(inventory, "stock_state") as balance:
            inventory.validate_check(changed)
            balance.assert_not_called()
        self.assertEqual(changed.rows[0].checked_on, old.rows[0].checked_on)

    def test_fractional_count_for_whole_number_uom_is_rejected(self):
        frappe.db.get_value.return_value = 1
        with inventory.transition("MIC"), patch.object(inventory, "load_locked_check", return_value=document()), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "whole-number"):
                inventory.validate_check(document(rows=[row(counted_qty=4.5)]))

    def test_difference_requires_reason_and_nonzero_quantity_requires_rate(self):
        with inventory.transition("MIC"), patch.object(inventory, "load_locked_check", return_value=document()), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "Explain"):
                inventory.validate_check(document(rows=[row(counted_qty=4)]))
            with self.assertRaisesRegex(frappe.ValidationError, "positive valuation"):
                inventory.validate_check(document(rows=[row(counted_rate=0)]))

    def test_existing_zero_valued_stock_can_be_confirmed_without_correction(self):
        with inventory.transition("MIC"), patch.object(inventory, "load_locked_check", return_value=document()):
            doc = document(rows=[row(current_rate=0, counted_rate=0)])
            inventory.validate_check(doc)
        self.assertEqual(doc.rows[0].row_status, "Matched")

    def test_zero_rows_require_confirmation(self):
        with patch.object(inventory, "ensure_scope"), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "Confirm every"):
                inventory.require_all_counted(document(rows=[row(counted=0, current_qty=0)]))

    def test_future_postings_block_snapshot(self):
        frappe.db.sql.return_value = [frappe._dict(future_entries=1)]
        with patch.object(inventory, "now_datetime", return_value=datetime(2026, 10, 1)), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "Future-dated"):
                inventory.stock_state("ITEM", "WH")

    def test_correction_must_be_submitted_and_same_company(self):
        for status, company in [(0, "AMF"), (2, "AMF"), (1, "OTHER")]:
            frappe.db.get_value.return_value = frappe._dict(docstatus=status, company=company)
            with patch.object(frappe, "throw", side_effect=self.throw):
                with self.assertRaisesRegex(frappe.ValidationError, "submitted"):
                    inventory.verify_correction(row(correction_type="Stock Entry", correction_document="SE"), "AMF")

    def test_submitted_correction_requires_exclusive_movement_and_exact_balance(self):
        source = row(counted_qty=4, correction_type="Stock Entry", correction_document="SE")
        frappe.db.get_value.return_value = frappe._dict(docstatus=1, company="AMF")
        frappe.db.sql.return_value = [["SLE"]]
        with patch.object(inventory, "stock_state", side_effect=[{"token": "baseline"}, {"qty": 4, "rate": 10, "token": "after"}]):
            inventory.verify_correction(source, "AMF")
        self.assertEqual(source.resolved, 1)
        self.assertEqual(source.ledger_token, "after")
        with patch.object(inventory, "stock_state", return_value={"token": "unrelated-movement"}), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "Other stock movements"):
                inventory.verify_correction(row(correction_type="Stock Entry", correction_document="SE"), "AMF")

    def test_submitted_correction_with_wrong_rate_is_rejected(self):
        frappe.db.get_value.return_value = frappe._dict(docstatus=1, company="AMF")
        frappe.db.sql.return_value = [["SLE"]]
        with patch.object(inventory, "stock_state", side_effect=[{"token": "baseline"}, {"qty": 4, "rate": 11}]), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "does not match"):
                inventory.verify_correction(row(counted_qty=4, correction_type="Stock Entry", correction_document="SE"), "AMF")

    def test_reconciliation_cannot_be_detached_or_tampered(self):
        reco = Doc(name="SR", company="AMF", monthly_inventory_check="MIC", purpose="Stock Reconciliation", items=[row(qty=9, valuation_rate=10)])
        check = document(reconciliation="SR", rows=[row(counted_qty=4)])
        frappe.db.get_value.return_value = "MIC"
        with patch.object(inventory, "lock_check", return_value=check), patch.object(inventory, "require_all_counted"), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "must match"):
                inventory.guard_reconciliation(reco)
            reco.monthly_inventory_check = None
            with self.assertRaisesRegex(frappe.ValidationError, "cannot be removed"):
                inventory.guard_reconciliation(reco)

    def test_cancelled_correction_reopens_passed_check(self):
        check = document(status="Passed", rows=[row(resolved=1, correction_type="Stock Entry", correction_document="SE")])
        frappe.db.sql.return_value = [["MIC"]]
        with patch.object(inventory, "lock_check", return_value=check), patch.object(frappe, "get_all", return_value=[]):
            inventory.on_correction_cancel(Doc(doctype="Stock Entry", name="SE"))
        self.assertEqual(check.status, "In Progress")
        self.assertEqual(check.rows[0].counted, 0)
        self.assertEqual(check.rows[0].resolved, 0)
        self.assertIsNone(check.completed_on)

    def test_scheduler_is_a_noop_until_enabled(self):
        frappe.db.get_single_value.return_value = 0
        with patch.object(inventory, "generate_check") as generate:
            inventory.run_monthly_inventory()
            generate.assert_not_called()

    def test_all_group_defaults_enabled_except_product_and_product_descendants_excluded(self):
        doc = settings()
        inventory.synchronize_group_rows(doc, GROUPS)
        self.assertEqual(len(doc.item_groups), len(GROUPS))
        self.assertEqual([r.item_group for r in doc.item_groups if not r.enabled], ["Product"])
        self.assertEqual(set(inventory.effective_item_groups(doc, GROUPS)),
            {"All Item Groups", "Part", "Fasteners", "New Group"})

    def test_disabled_parent_vetoes_enabled_child_and_product_can_be_explicitly_enabled(self):
        doc = settings(item_groups=[frappe._dict(item_group="Part", enabled=0),
                                    frappe._dict(item_group="Product", enabled=1)])
        enabled = set(inventory.effective_item_groups(doc, GROUPS))
        self.assertNotIn("Part", enabled)
        self.assertNotIn("Fasteners", enabled)
        self.assertTrue({"Product", "Product Child"}.issubset(enabled))

    def test_new_groups_are_added_without_resetting_existing_choices_or_exclusions(self):
        doc = settings(item_groups=[frappe._dict(item_group="Part", enabled=0)],
            excluded_items=[frappe._dict(item_code="EXCLUDE")])
        inventory.synchronize_group_rows(doc, GROUPS)
        inventory.synchronize_group_rows(doc, GROUPS)
        self.assertEqual(len(doc.item_groups), len(GROUPS))
        self.assertFalse(next(r.enabled for r in doc.item_groups if r.item_group == "Part"))
        self.assertEqual([r.item_code for r in doc.excluded_items], ["EXCLUDE"])

    def test_removed_group_row_preserves_saved_disabled_choice(self):
        doc = settings(previous=settings(item_groups=[frappe._dict(item_group="Part", enabled=0)]))
        inventory.synchronize_group_rows(doc, GROUPS)
        self.assertFalse(next(r.enabled for r in doc.item_groups if r.item_group == "Part"))

    def test_duplicate_group_and_excluded_reference_are_rejected(self):
        duplicate = settings(item_groups=[frappe._dict(item_group="Part", enabled=1),
                                          frappe._dict(item_group="Part", enabled=0)])
        with patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "Duplicate item group"):
                inventory.synchronize_group_rows(duplicate, GROUPS)
            with patch.object(inventory, "get_inventory_item_groups", return_value=GROUPS):
                with self.assertRaisesRegex(frappe.ValidationError, "Duplicate excluded reference"):
                    inventory.validate_settings(settings(excluded_items=[
                        frappe._dict(item_code="EXCLUDE"), frappe._dict(item_code="EXCLUDE")]))

    def test_disabling_root_leaves_no_eligible_references(self):
        doc = settings(item_groups=[frappe._dict(item_group="All Item Groups", enabled=0)])
        self.assertEqual(inventory.get_eligible_references(doc, GROUPS), [])
        frappe.db.sql.assert_not_called()

    def test_enabling_schedule_requires_at_least_ten_eligible_references(self):
        with patch.object(inventory, "get_inventory_item_groups", return_value=GROUPS), patch.object(
                inventory, "get_eligible_references", return_value=list(range(9))), patch.object(
                inventory, "validate_assignee"), patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "at least 10 active stock references"):
                inventory.validate_settings(settings(enabled=1))

    def test_legacy_sample_limits_cannot_override_exact_ten(self):
        doc = settings(minimum_items=5, maximum_items=6)
        with patch.object(inventory, "get_inventory_item_groups", return_value=GROUPS):
            inventory.validate_settings(doc)
        self.assertEqual((doc.sample_size, doc.minimum_items, doc.maximum_items), (10, 10, 10))
        self.assertEqual(doc.warehouse_root, "Production - AMF21")

    def test_locked_parent_uses_nonlocking_children_from_matching_snapshot(self):
        stamp = datetime(2026, 10, 23, 14)
        frappe.db.sql.side_effect = [[frappe._dict(name="MIC", modified=stamp)], [(stamp,)], [row()]]
        with patch.object(frappe, "get_doc", side_effect=lambda data: data):
            result = inventory.load_locked_check("MIC")
        self.assertEqual(result["rows"][0].name, "R1")
        self.assertIn("FOR UPDATE", frappe.db.sql.call_args_list[0][0][0])
        self.assertNotIn("FOR UPDATE", frappe.db.sql.call_args_list[2][0][0])
        self.assertNotIn("LOCK IN SHARE MODE", frappe.db.sql.call_args_list[2][0][0])

    def test_old_snapshot_cannot_be_combined_with_newer_locked_parent(self):
        frappe.db.sql.side_effect = [[frappe._dict(name="MIC", modified=datetime(2026, 10, 23, 15))],
                                    [(datetime(2026, 10, 23, 14),)]]
        with patch.object(frappe, "throw", side_effect=self.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "changed during the request"):
                inventory.load_locked_check("MIC")
        self.assertEqual(frappe.db.sql.call_count, 2)

    def test_stock_locks_follow_ledger_then_bin_order(self):
        inventory.lock_stock_rows([row()])
        queries = [call[0][0] for call in frappe.db.sql.call_args_list]
        self.assertIn("Stock Ledger Entry", queries[0])
        self.assertIn("tabBin", queries[1])


class TestMonthlyInventorySetup(unittest.TestCase):
    def setUp(self):
        patches = [patch.object(inventory, "_", side_effect=lambda text: text),
            patch.object(frappe, "local", frappe._dict(valid_columns={})),
            patch.object(frappe, "db", MagicMock()),
            patch.object(frappe, "clear_cache"),
            patch.object(frappe.defaults, "get_global_default", return_value=None),
            patch.object(inventory, "get_inventory_item_groups", return_value=GROUPS),
            patch("frappe.custom.doctype.custom_field.custom_field.create_custom_fields")]
        for mock in patches:
            mock.start()
        self.addCleanup(lambda: [mock.stop() for mock in reversed(patches)])
        frappe.db.sql.return_value = []
        frappe.db.get_value.return_value = None

    def setup_document(self, **values):
        doc = settings(**values)
        doc.warehouse_root = values.get("warehouse_root")
        doc.flags = frappe._dict()
        doc.get = lambda field: getattr(doc, field, None)
        doc.save = MagicMock()
        return doc

    def test_optional_scope_allows_missing_master_data_but_runtime_remains_strict(self):
        self.assertIsNone(inventory.production_root("AMF", required=False))
        with patch.object(frappe, "throw", side_effect=TestMonthlyInventory.throw):
            with self.assertRaisesRegex(frappe.ValidationError, "enabled Production warehouse group"):
                inventory.production_root("AMF")

    def test_lifecycle_setup_is_registered_for_installation_not_every_migration(self):
        from amf import hooks
        self.assertEqual(hooks.after_install.count("amf.amf.utils.monthly_inventory.setup_monthly_inventory"), 1)
        self.assertIn("amf.amf.utils.project_id.after_install", hooks.after_install)
        self.assertNotIn("amf.amf.utils.monthly_inventory.setup_monthly_inventory", hooks.after_migrate)

    def test_new_site_setup_does_not_require_company_or_default_assignee(self):
        doc = self.setup_document(company=None, assigned_to=None)
        frappe.db.get_singles_dict.return_value = {}
        with patch.object(frappe, "get_single", return_value=doc):
            inventory.setup_monthly_inventory()
        self.assertEqual(len(doc.item_groups), len(GROUPS))
        self.assertEqual([row.item_group for row in doc.item_groups if not row.enabled], ["Product"])
        self.assertEqual(doc.enabled, 0)
        self.assertIsNone(doc.assigned_to)
        self.assertFalse(any(call.args[2] == "assigned_to" for call in frappe.db.set_value.call_args_list))
        doc.save.assert_called_once_with(ignore_permissions=True)
        self.assertTrue(doc.flags.ignore_validate and doc.flags.ignore_links and doc.flags.ignore_mandatory)

    def test_migration_preserves_configuration_when_production_scope_is_unavailable(self):
        doc = self.setup_document(enabled=1, assigned_to="existing@example.com", due_day=22,
            warehouse_root="Existing Scope", item_groups=[frappe._dict(item_group="Part", enabled=0)],
            excluded_items=[frappe._dict(item_code="EXCLUDE")])
        frappe.db.get_singles_dict.return_value = {field: doc.get(field) for field in (
            "enabled", "assigned_to", "company", "sample_size", "minimum_items", "maximum_items", "due_day")}
        with patch.object(frappe, "get_single", return_value=doc):
            inventory.setup_monthly_inventory()
        self.assertEqual((doc.enabled, doc.assigned_to, doc.due_day, doc.warehouse_root),
                         (1, "existing@example.com", 22, "Existing Scope"))
        self.assertFalse(next(row.enabled for row in doc.item_groups if row.item_group == "Part"))
        self.assertEqual(doc.excluded_items[0].item_code, "EXCLUDE")
        frappe.db.set_value.assert_not_called()

    def test_default_assignee_is_filled_only_if_an_enabled_system_user_exists(self):
        doc = self.setup_document(company=None, assigned_to=None)
        frappe.db.get_singles_dict.return_value = {"assigned_to": None}
        frappe.db.get_value.return_value = frappe._dict(enabled=1, user_type="System User")
        with patch.object(frappe, "get_single", return_value=doc):
            inventory.setup_monthly_inventory()
        self.assertTrue(any(call.args[2:4] == ("assigned_to", inventory.DEFAULT_ASSIGNEE)
                            for call in frappe.db.set_value.call_args_list))

    def test_repeated_setup_does_not_resave_unchanged_settings(self):
        doc = self.setup_document(company=None)
        inventory.synchronize_group_rows(doc, GROUPS)
        frappe.db.get_singles_dict.return_value = {field: doc.get(field) for field in (
            "enabled", "assigned_to", "company", "sample_size", "minimum_items", "maximum_items", "due_day")}
        with patch.object(frappe, "get_single", return_value=doc):
            inventory.setup_monthly_inventory()
            inventory.setup_monthly_inventory()
        doc.save.assert_not_called()
        frappe.db.set_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
