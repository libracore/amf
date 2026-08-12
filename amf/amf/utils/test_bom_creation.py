from __future__ import unicode_literals

from collections import defaultdict
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import frappe

from amf.amf.utils import bom_creation


def _row(parent, idx, item_code, bom_no=None):
    return frappe._dict(
        parent=parent,
        name="{0}-ROW-{1}".format(parent, idx),
        idx=idx,
        item_code=item_code,
        bom_no=bom_no,
    )


class TestRecursiveBomVersionUpdate(unittest.TestCase):
    def test_default_boms_are_ordered_children_before_parents(self):
        defaults = {
            "ASSEMBLY-A": "BOM-A",
            "ASSEMBLY-B": "BOM-B",
            "ASSEMBLY-C": "BOM-C",
            "ASSEMBLY-D": "BOM-D",
        }
        rows = defaultdict(list)
        rows["BOM-A"].append(_row("BOM-A", 1, "ASSEMBLY-B", "BOM-B"))
        rows["BOM-B"].append(_row("BOM-B", 1, "ASSEMBLY-C", "BOM-C"))

        order = bom_creation._get_bottom_up_bom_order(defaults, rows)

        self.assertLess(order.index("BOM-C"), order.index("BOM-B"))
        self.assertLess(order.index("BOM-B"), order.index("BOM-A"))
        self.assertEqual(set(order), {"BOM-A", "BOM-B", "BOM-C", "BOM-D"})

    def test_direct_change_is_propagated_to_every_ancestor(self):
        defaults = {
            "ASSEMBLY-A": "BOM-A",
            "ASSEMBLY-B": "BOM-B",
            "ASSEMBLY-C": "BOM-C",
        }
        rows = defaultdict(list)
        rows["BOM-A"].append(_row("BOM-A", 1, "ASSEMBLY-B", "BOM-B"))
        rows["BOM-B"].append(_row("BOM-B", 1, "ASSEMBLY-C", "BOM-C-OLD"))
        order = ["BOM-C", "BOM-B", "BOM-A"]

        changed = bom_creation._get_boms_requiring_new_versions(
            order,
            defaults,
            rows,
        )

        self.assertEqual(changed, {"BOM-A", "BOM-B"})

    def test_stale_bom_link_is_cleared_when_item_has_no_default(self):
        defaults = {"ASSEMBLY-A": "BOM-A"}
        rows = defaultdict(list)
        rows["BOM-A"].append(_row("BOM-A", 1, "RAW-MATERIAL", "BOM-STALE"))

        changed = bom_creation._get_boms_requiring_new_versions(
            ["BOM-A"],
            defaults,
            rows,
        )
        plan = bom_creation._build_dry_run_version_plan(
            ["BOM-A"],
            changed,
            defaults,
            {"BOM-A": "ASSEMBLY-A"},
            rows,
        )

        self.assertEqual(changed, {"BOM-A"})
        self.assertEqual(plan[0]["row_changes"][0]["to_bom"], "")

    def test_default_bom_cycle_is_rejected(self):
        defaults = {"ASSEMBLY-A": "BOM-A", "ASSEMBLY-B": "BOM-B"}
        rows = defaultdict(list)
        rows["BOM-A"].append(_row("BOM-A", 1, "ASSEMBLY-B", "BOM-B"))
        rows["BOM-B"].append(_row("BOM-B", 1, "ASSEMBLY-A", "BOM-A"))

        with patch.object(
            bom_creation.frappe,
            "throw",
            side_effect=frappe.ValidationError,
        ), self.assertRaises(frappe.ValidationError):
            bom_creation._get_bottom_up_bom_order(defaults, rows)

    def test_new_version_reprices_changed_row_and_reapplies_resolved_link(self):
        copied_row = SimpleNamespace(
            idx=1,
            item_code="CHILD",
            bom_no="BOM-CHILD-OLD",
            rate=25,
            base_rate=25,
            amount=25,
            base_amount=25,
        )
        source = SimpleNamespace(item="PARENT", total_cost=25)
        new_bom = SimpleNamespace(
            item="PARENT",
            name="BOM-PARENT-002",
            items=[copied_row],
            flags=SimpleNamespace(ignore_permissions=False),
            total_cost=40,
            docstatus=1,
            is_active=1,
            is_default=0,
        )

        def insert(ignore_permissions=False):
            self.assertTrue(ignore_permissions)
            self.assertEqual(copied_row.bom_no, "BOM-CHILD-NEW")
            self.assertEqual(copied_row.rate, 0)
            # Simulate the project before-save hook changing the link.
            copied_row.bom_no = "BOM-FROM-HOOK"

        def submit():
            self.assertEqual(copied_row.bom_no, "BOM-CHILD-NEW")

        new_bom.insert = insert
        new_bom.submit = submit
        state = frappe._dict(
            item="PARENT",
            is_active=1,
            is_default=1,
            docstatus=1,
        )

        with patch.object(bom_creation, "_get_bom_state", return_value=state), \
                patch.object(bom_creation.frappe, "get_doc", return_value=source), \
                patch.object(bom_creation.frappe, "copy_doc", return_value=new_bom), \
                patch.object(bom_creation, "set_default_bom") as set_default:
            result = bom_creation._create_new_bom_version(
                "BOM-PARENT-001",
                {"CHILD": "BOM-CHILD-NEW"},
            )

        set_default.assert_called_once_with("PARENT", "BOM-PARENT-002")
        self.assertEqual(result["total_cost_before"], 25.0)
        self.assertEqual(result["total_cost_after"], 40.0)
        self.assertEqual(result["row_changes"][0]["to_bom"], "BOM-CHILD-NEW")


if __name__ == "__main__":
    unittest.main()
