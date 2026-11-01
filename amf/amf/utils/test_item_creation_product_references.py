import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from amf.amf.utils import item_creation_plan as plans
from amf.amf.utils import item_creation_workflow as workflow
from amf.amf.utils.test_item_creation_plan import catalogue, item, materialize, source
from amf.amf.utils.test_item_creation_reuse import ReuseCatalogue


class TestProductReferenceOverrides(unittest.TestCase):
    def setUp(self):
        self.context = patch.object(frappe, "db", SimpleNamespace(
            get_value=Mock(return_value=frappe._dict(company="AMF", is_group=0, disabled=0))))
        self.context.start()
        self.addCleanup(self.context.stop)
        data = catalogue()
        materialize(plans.build_plan(source(), catalogue=data), data)
        self.data = ReuseCatalogue(data.tables)
        retired = item("/410ABC", "Product")
        retired.update(reference_code="P200O300ABC", disabled=1)
        self.data.tables["Item"].append(retired)

    def request(self, reference=""):
        return source(product_only=1, head_check="No", head_item="300ABC", plug_check="No", seat_check="No",
            plug_item="110ABC", seat_item="210ABC", rvm_check=1,
            product_variants=[dict(selected=1, body="511000", syringe="", product_reference=reference)])

    def plan(self, doc):
        return plans.build_plan(doc, catalogue=ReuseCatalogue(self.data.tables))

    def test_override_resolves_retired_reference_conflict_without_changing_owner_or_recipe(self):
        before = copy.deepcopy(self.data.tables)
        blocked = self.plan(self.request())
        conflict = next(row["reference_conflict"] for row in blocked["errors"] if row.get("reference_conflict"))
        self.assertEqual(conflict["configuration"], "511000:")
        self.assertEqual(conflict["owners"], ["/410ABC"])
        reviewed = self.plan(self.request("P200O300ABC-R1"))
        self.assertTrue(reviewed["ready"], reviewed["errors"])
        self.assertEqual(reviewed["actions"][0]["item"]["reference_code"], "P200O300ABC-R1")
        self.assertEqual(reviewed["actions"][0]["materials"], blocked["actions"][0]["materials"])
        self.assertEqual(reviewed["actions"][0]["item"]["item_code"], "410001")
        self.assertEqual({key: self.data.tables[key] for key in before}, before)
        self.assertNotEqual(reviewed["input_hash"], blocked["input_hash"])

    def test_blank_restores_generated_reference_and_its_existing_conflict(self):
        doc = self.request("P200O300ABC-R1")
        self.assertTrue(self.plan(doc)["ready"])
        doc.product_variants[0]["product_reference"] = "   "
        plan = self.plan(doc)
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["actions"][0]["item"]["reference_code"], "P200O300ABC")

    def test_existing_product_with_entered_reference_is_reused(self):
        doc = self.request("P200O300ABC-R1")
        materialize(self.plan(doc), self.data)
        repeated = self.plan(doc)
        self.assertTrue(repeated["ready"], repeated["errors"])
        self.assertEqual(repeated["actions"][0]["item_action"], "reuse")
        self.assertEqual(repeated["actions"][0]["bom_action"], "reuse")
        # Entering a different reference for that exact Item code cannot rename it.
        doc.product_variants[0].update(product_code="410001", product_reference="P200O300ABC-R2")
        self.assertTrue(any("different identity" in row["message"] for row in self.plan(doc)["errors"]))

    def test_overrides_still_check_global_unique_owners_case_insensitively(self):
        owner = item("OTHER-ITEM", "Part")
        owner["reference_code"] = "p200o300abc-r1"
        self.data.tables["Item"].append(owner)
        plan = self.plan(self.request("P200O300ABC-R1"))
        self.assertFalse(plan["ready"])
        self.assertTrue(any("OTHER-ITEM" in row["message"] for row in plan["errors"]))

    def test_new_head_reference_overrides_check_other_item_groups_too(self):
        data = catalogue()
        owner = item("OTHER-ITEM", "Part")
        owner["reference_code"] = "P201O300ABC-R1"
        data.tables["Item"].append(owner)
        plan = plans.build_plan(source(rvm_check=1, product_variants=[dict(selected=1, body="521000",
            syringe="", product_reference="P201O300ABC-R1")]), catalogue=data)
        self.assertFalse(plan["ready"])
        self.assertTrue(any("OTHER-ITEM" in row["message"] for row in plan["errors"]))

    def test_two_configurations_cannot_plan_the_same_reference(self):
        doc = self.request("SHARED-300ABC-R1")
        doc.product_variants.append(dict(selected=1, body="521000", syringe="", product_reference="shared-300abc-r1"))
        plan = self.plan(doc)
        self.assertFalse(plan["ready"])
        self.assertTrue(any("another selected configuration" in row["message"] for row in plan["errors"]))

    def test_reference_format_preserves_head_identity_and_v12_field_capacity(self):
        for reference in ("CUSTOM", "P200O300DEF-R1", "300ABC-300ABC", "300ABC-300DEF",
                          "300ABC\nR1", "300ABC" + "X" * 135):
            with self.subTest(reference=reference):
                self.assertFalse(self.plan(self.request(reference))["ready"])
        self.assertTrue(self.plan(self.request("300ABC" + "X" * 134))["ready"])

    def test_reference_change_requires_new_engineering_review(self):
        doc = self.request("P200O300ABC-R1")
        reviewed = self.plan(doc)
        doc.review_status = "Reviewed"
        doc.approved_plan_hash, doc.approved_input_hash = reviewed["fingerprint"], reviewed["input_hash"]
        doc.product_variants[0]["product_reference"] = "P200O300ABC-R2"
        current = self.plan(doc)
        self.assertNotEqual(current["input_hash"], reviewed["input_hash"])
        with patch.object(workflow, "_lock_source"), patch.object(workflow, "build_plan", return_value=current), \
                patch.object(frappe, "flags", frappe._dict(mute_messages=True)):
            with self.assertRaisesRegex(frappe.ValidationError, "stale"):
                workflow.validate_submission(doc)

    def test_reference_conflicts_are_escaped_in_server_validation_messages(self):
        reference = '300ABC-<img src=x onerror="alert(1)">'
        owner = item("OTHER-ITEM", "Part")
        owner["reference_code"] = reference
        self.data.tables["Item"].append(owner)
        plan = self.plan(self.request(reference))
        self.assertFalse(plan["ready"])
        with patch.object(frappe, "throw") as show_error:
            workflow.require_ready(plan)
        message = show_error.call_args[0][0]
        self.assertNotIn("<img", message)
        self.assertIn("&lt;img", message)


if __name__ == "__main__":
    unittest.main()
