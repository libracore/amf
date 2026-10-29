import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from amf.amf.doctype.item_creation import item_creation as controller
from amf.amf.utils import item_creation_plan as plans
from amf.amf.utils import item_creation_workflow as workflow
from amf.amf.utils.test_item_creation_plan import MemoryCatalogue, catalogue, materialize, source


class TestItemCreationRvmMini(unittest.TestCase):
    def setUp(self):
        self.context = patch.object(frappe, "db", SimpleNamespace(
            get_value=Mock(return_value=frappe._dict(company="AMF", is_group=0, disabled=0))))
        self.context.start()
        self.addCleanup(self.context.stop)

    def request(self, **changes):
        return source(rvm_check=1, product_variants=[dict(selected=1, body="5D1000", syringe="", **changes)])

    def test_mini_uses_its_own_prefix_reference_weight_and_rvm_materials(self):
        for overrides, code, reference in (({}, "4D0ABC", "P202O300ABC"),
                ({"product_code": "4D0XYZ", "product_reference": "P202O300ABC-R1"}, "4D0XYZ", "P202O300ABC-R1")):
            with self.subTest(overrides=overrides):
                plan = plans.build_plan(self.request(**overrides), catalogue=catalogue())
                self.assertTrue(plan["ready"], plan["errors"])
                product = plan["actions"][-1]
                self.assertEqual(product["item"]["item_code"], code)
                self.assertEqual(product["item"]["reference_code"], reference)
                self.assertEqual(product["item"]["item_name"], "P202-O/V-D-1-6-050-C-P")
                self.assertEqual(product["item"]["weight_per_unit"], .1)
                self.assertEqual(product["item"]["weight_uom"], "Kg")
                self.assertEqual({row["item_code"]: row["qty"] for row in product["materials"]},
                                 {"5D1000": 1, "300ABC": 1, "SCREW": 2, "CAP": 1})
                self.assertEqual(product["scraps"], [])

    def test_chooser_includes_mini_under_rvm_without_a_syringe(self):
        doc, data = self.request(), catalogue()
        with patch.object(workflow, "_source_for_preview", return_value=doc), \
                patch.object(frappe, "get_all", return_value=[frappe._dict(row) for row in data.tables["Item"]]):
            rows = workflow.get_compatible_variants({})
        self.assertTrue({"511000", "521000", "5D1000", "5D1001", "5D1002"}.issubset({row["body"] for row in rows}))
        mini = next(row for row in rows if row["body"] == "5D1000")
        self.assertEqual(mini["configuration"], "P202-O (RVM mini)")
        self.assertEqual(mini["syringe"], "")
        self.assertEqual(mini["compatibility_note"], "")

    def test_existing_matching_mini_item_and_bom_are_reused(self):
        doc, data = self.request(), catalogue()
        materialize(plans.build_plan(doc, catalogue=data), data)
        doc.update(dict(product_only=1, head_check="No", head_item="300ABC", plug_check="No", seat_check="No"))
        plan = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual(len(plan["actions"]), 1)
        self.assertEqual(plan["actions"][0]["item"]["item_code"], "4D0ABC")
        self.assertEqual(plan["actions"][0]["item_action"], "reuse")
        self.assertEqual(plan["actions"][0]["bom_action"], "reuse")

    def test_mini_body_must_be_enabled_and_keep_its_catalogue_identity(self):
        for change in ({"disabled": 1}, {"item_group": "Part"}, {"reference_code": "P201-O"}):
            with self.subTest(change=change):
                data = catalogue()
                next(row for row in data.tables["Item"] if row["name"] == "5D1000").update(change)
                self.assertFalse(plans.build_plan(self.request(), catalogue=data)["ready"])

    def test_mini_does_not_enable_prototypes_syringes_or_hv_heads(self):
        variants = [dict(selected=1, body="5D1000", syringe="703000"),
                    dict(selected=1, body="5D100A", syringe="")]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertFalse(plans.build_plan(source(rvm_check=1, product_variants=[variant]), catalogue=catalogue())["ready"])
        self.assertFalse(plans.build_plan(self.request(product_code="4D1ABC"), catalogue=catalogue())["ready"])
        doc = self.request()
        doc.head_name += "-HV"
        self.assertFalse(plans.build_plan(doc, catalogue=catalogue())["ready"])
        doc = self.request()
        doc.rvm_check = 0
        self.assertFalse(plans.build_plan(doc, catalogue=catalogue())["ready"])

    def test_rvm_preview_adapter_includes_mini(self):
        plan = plans.build_plan(self.request(), catalogue=catalogue())
        with patch.object(workflow, "get_creation_plan", return_value=plan):
            rows = controller.get_data_for_preview({}, "rvm")
        self.assertEqual([row["item_code"] for row in rows], ["4D0ABC"])


if __name__ == "__main__":
    unittest.main()
