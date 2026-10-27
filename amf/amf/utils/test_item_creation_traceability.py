import copy
import re
import unittest
from unittest.mock import Mock, patch

import frappe

from amf.amf.utils import item_creation_traceability as trace
from amf.amf.utils import item_creation_workflow as workflow
from amf.amf.utils import item_creation_plan as plans
from amf.amf.utils.test_item_creation_plan import source


class TestItemCreationTraceability(unittest.TestCase):
    def setUp(self):
        self.flags_patch = patch.object(frappe, "flags", frappe._dict(mute_messages=True))
        self.flags_patch.start()
        self.addCleanup(self.flags_patch.stop)
        self.db = Mock()
        self.db.sql.return_value = []
        self.db_patch = patch.object(frappe, "db", self.db, create=True)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def test_execution_links_retain_each_revision_and_cannot_be_written_twice(self):
        doc = source(docstatus=1, execution_results=[])
        inserted = []
        def append(field, values):
            row = frappe._dict(values)
            row.db_insert = lambda: inserted.append(row.copy())
            doc[field].append(row)
            return row
        doc.append = append
        result = dict(completed_at="2026-10-27 12:00:00", records=[dict(item_code="300ABC", item_action="reuse",
            bom="BOM-NEW", bom_action="replace", replaced_bom="BOM-OLD")])
        trace.store_results(doc, result)
        self.assertEqual(inserted[0]["replaced_bom"], "BOM-OLD")
        self.assertEqual(inserted[0]["docstatus"], 1)
        with self.assertRaisesRegex(frappe.ValidationError, "already exist"):
            trace.store_results(doc, result)
        self.db.commit.assert_not_called()

    def test_result_rows_and_parent_edits_are_protected(self):
        from amf.amf.doctype.item_creation_result.item_creation_result import ItemCreationResult
        for operation in (lambda: ItemCreationResult.validate(None), lambda: ItemCreationResult.on_trash(None)):
            with self.assertRaises(frappe.ValidationError):
                operation()
        old = source(execution_results=[dict(name="LINK", idx=1, item_code="300ABC", bom="BOM-OLD")])
        doc = copy.deepcopy(old)
        doc.get_doc_before_save = lambda: old
        doc.execution_results[0]["bom"] = "BOM-FORGED"
        with self.assertRaisesRegex(frappe.ValidationError, "result links"):
            workflow.protect_review_fields(doc)

    def test_amendment_reason_is_reviewed_without_changing_ordinary_hashes(self):
        ordinary = source()
        self.assertNotIn("amended_from", plans.inputs(ordinary))
        amended = source(amended_from="CANCELLED", amendment_reason="Correct quantity")
        original = plans.input_hash(amended)
        amended.amendment_reason = "Different engineering decision"
        self.assertNotEqual(original, plans.input_hash(amended))
        self.assertEqual(plans.input_hash(ordinary), plans.input_hash(source()))

    def test_amendment_requires_cancelled_source_and_no_active_sibling(self):
        predecessor = source(docstatus=1, check_permission=Mock())
        with patch.object(frappe, "get_doc", return_value=predecessor):
            with self.assertRaisesRegex(frappe.ValidationError, "cancelled"):
                trace._amendment_source(source(amended_from="ORIGINAL"))
            predecessor.docstatus = 2
            self.db.sql.side_effect = [[], [("OTHER-AMENDMENT",)]]
            with self.assertRaisesRegex(frappe.ValidationError, "active amendment"):
                trace._amendment_source(source(amended_from="ORIGINAL"))

    def test_amendment_cannot_switch_head_or_change_predecessor(self):
        doc = source(amended_from="ORIGINAL", amendment_reason="Correct quantity", get_doc_before_save=lambda: None)
        with patch.object(trace, "_amendment_source", return_value=source(head_code="300ABC")):
            with self.assertRaisesRegex(frappe.ValidationError, "original head family"):
                trace.validate_amendment(doc)
            doc.head_check, doc.head_item = "No", "300ABC"
            trace.validate_amendment(doc)
            doc.amendment_reason = "  "
            with self.assertRaisesRegex(frappe.ValidationError, "reason"):
                trace.validate_amendment(doc)
        doc.get_doc_before_save = lambda: source(amended_from="OTHER")
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed"):
            trace.validate_amendment(doc)

    def test_cancellation_needs_reason_and_rejects_changed_inputs(self):
        self.db.sql.return_value = [(1,)]
        old = source(docstatus=1, review_status="Created", execution_results=[])
        doc = copy.deepcopy(old)
        doc.get_doc_before_save = lambda: old
        with self.assertRaisesRegex(frappe.ValidationError, "cancellation reason"):
            trace.before_cancel(doc)
        doc.cancellation_reason = "Review quantity"
        doc.screw_quantity = 4
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed"):
            trace.before_cancel(doc)

    def test_second_cancellation_cannot_overwrite_the_first_reason(self):
        self.db.sql.return_value = [(2,)]
        with self.assertRaisesRegex(frappe.ValidationError, "currently submitted"):
            trace.before_cancel(source(cancellation_reason="Overwrite the first reason"))

    def test_history_search_applies_request_permissions_after_exact_revision_search(self):
        rows = [frappe._dict(parent="VISIBLE", item_code="300ABC", bom="BOM-NEW", replaced_bom="BOM-OLD"),
                frappe._dict(parent="PRIVATE", item_code="300ABC", bom="BOM-NEW", replaced_bom="BOM-OLD")]
        parents = [frappe._dict(name="VISIBLE", docstatus=2, amended_from="ORIGINAL", head_code="300ABC")]
        with patch.object(frappe, "has_permission", return_value=True), \
                patch.object(frappe, "get_doc", return_value=Mock()), \
                patch.object(frappe, "get_all", return_value=rows) as get_all, \
                patch.object(frappe, "get_list", return_value=parents):
            result = trace.result_history(dict(bom="BOM-OLD", status="Cancelled"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["request"], "VISIBLE")
        self.assertEqual(result[0]["status"], "Cancelled")
        self.assertEqual(get_all.call_args.kwargs["or_filters"], {"bom": "BOM-OLD", "replaced_bom": "BOM-OLD"})

    def test_history_search_is_denied_without_read_permission(self):
        with patch.object(frappe, "has_permission", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                trace.result_history()

    def test_syringe_query_allows_digit_or_letter_in_third_position(self):
        from amf.amf.doctype.item_creation.item_creation import syringe_item_query
        with patch.object(frappe, "has_permission", return_value=True), \
                patch("frappe.desk.reportview.get_match_cond", return_value=""):
            syringe_item_query("Item", "' OR 1=1", "untrusted", -5, 1000)
        query, values = self.db.sql.call_args.args
        self.assertNotIn("' OR 1=1", query)
        self.assertEqual(values["start"], 0)
        self.assertEqual(values["page_len"], 100)
        for code in ("700000", "709000", "70E000", "70F123", "70z123"):
            self.assertIsNotNone(re.fullmatch(values["pattern"], code), code)
        for code in ("70_000", "70-000", "70.000", "70E0000", "70E00", "/70E000", "71E000"):
            self.assertIsNone(re.fullmatch(values["pattern"], code), code)


if __name__ == "__main__":
    unittest.main()
