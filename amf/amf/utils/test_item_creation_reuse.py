import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from amf.amf.utils import item_creation_plan as plans
from amf.amf.utils import item_creation_workflow as workflow
from amf.amf.utils.test_item_creation_plan import MemoryCatalogue, catalogue, item, materialize, source


class ReuseCatalogue(MemoryCatalogue):
    def product_code_inventory(self, references=()):
        return self.tables["Item"]

    def reserved_product_codes(self):
        return getattr(self, "retired_codes", set())


class TestItemCreationReuse(unittest.TestCase):
    def setUp(self):
        self.db = SimpleNamespace(get_value=Mock(return_value=frappe._dict(company="AMF", is_group=0, disabled=0)))
        self.context = patch.object(frappe, "db", self.db)
        self.context.start()
        self.addCleanup(self.context.stop)

    def legacy_catalogue(self):
        data = catalogue()
        materialize(plans.build_plan(source(), catalogue=data), data)
        mapping = {"100ABC": "100XYZ", "110ABC": "110XYZ", "200ABC": "200DEF", "210ABC": "210DEF"}
        for rows in data.tables.values():
            for row in rows:
                for field in ("name", "item", "item_code", "parent", "bom_no", "default_bom"):
                    if isinstance(row.get(field), str):
                        for before, after in mapping.items():
                            row[field] = row[field].replace(before, after)
        return ReuseCatalogue(data.tables)

    def request(self, **changes):
        return source(head_check="No", head_item="300ABC", plug_check="No", seat_check="No",
            plug_item="110XYZ", seat_item="210DEF", **changes)

    def test_existing_head_with_independently_numbered_components_is_reused(self):
        data = self.legacy_catalogue()
        plan = plans.build_plan(self.request(), catalogue=data)
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual(plan["actions"][0]["bom_action"], "reuse")
        self.assertTrue(any("independently numbered" in row for row in plan["warnings"]))

    def test_new_head_still_requires_matching_component_suffixes(self):
        plan = plans.build_plan(source(plug_check="No", seat_check="No", plug_item="110XYZ", seat_item="210DEF"),
                                catalogue=self.legacy_catalogue())
        self.assertFalse(plan["ready"])
        self.assertTrue(any("share head suffix" in row["message"] for row in plan["errors"]))

    def test_changing_selected_components_requires_explicit_head_bom_replacement(self):
        doc = self.request()
        doc.plug_item = "110OTHER"
        plan = plans.build_plan(doc, catalogue=self.legacy_catalogue())
        self.assertTrue(any("differs from the existing head BOM" in row["message"] for row in plan["errors"]))

    def test_product_only_plan_contains_only_products_and_preserves_legacy_head(self):
        data = self.legacy_catalogue()
        next(row for row in data.tables["Item"] if row["name"] == "300ABC")["reference_code"] = None
        before = copy.deepcopy(data.tables)
        for replace_boms in (0, 1):
            with self.subTest(replace_boms=replace_boms):
                plan = plans.build_plan(self.request(product_only=1, rvm_check=1, replace_boms=replace_boms,
                    product_variants=[dict(selected=1, body="521000", syringe="")]), catalogue=data)
                self.assertTrue(plan["ready"], plan["errors"])
                self.assertEqual([row["item"]["item_code"] for row in plan["actions"]], ["420ABC"])
                self.assertEqual(plan["actions"][0]["item"]["item_name"], "P201-O/300ABC")
                self.assertEqual({key: data.tables[key] for key in before}, before)
                self.assertEqual(plan["raw_material_candidates"], [])

    def test_product_only_cannot_create_components_or_omit_configurations(self):
        for change in ({"plug_check": "Yes"}, {"head_check": "Yes"}, {}):
            doc = self.request(product_only=1)
            doc.update(change)
            self.assertFalse(plans.build_plan(doc, catalogue=self.legacy_catalogue())["ready"])

    def test_consistent_legacy_uom_snapshot_is_reviewed_without_rewriting(self):
        data = self.legacy_catalogue()
        row = next(row for row in data.tables["BOM Item"] if row["parent"] == "BOM-100XYZ")
        row["stock_uom"] = "Nos"
        plan = plans.build_plan(self.request(), catalogue=data)
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertTrue(any("old stock-UOM label" in warning for warning in plan["warnings"]))
        self.assertEqual(row["stock_uom"], "Nos")
        row["conversion_factor"] = .5
        self.assertFalse(plans.build_plan(self.request(), catalogue=ReuseCatalogue(data.tables))["ready"])

    def test_legacy_disabled_components_and_cycles_remain_errors(self):
        for problem in ("disabled", "cycle"):
            data = self.legacy_catalogue()
            if problem == "disabled":
                next(row for row in data.tables["Item"] if row["name"] == "100XYZ")["disabled"] = 1
            else:
                row = next(row for row in data.tables["BOM Item"] if row["parent"] == "BOM-100XYZ")
                row.update(item_code="300ABC", bom_no="BOM-300ABC")
            self.assertFalse(plans.build_plan(self.request(), catalogue=data)["ready"])

    def test_product_suggestions_skip_collisions_disabled_aliases_and_retired_codes(self):
        data = self.legacy_catalogue()
        data.tables["Item"].extend([item("420ABC", "Product"), item("420001", "Product"), item("/420002-P", "Product")])
        data.retired_codes = {"420003"}
        plan = plans.build_plan(self.request(product_only=1, rvm_check=1,
            product_variants=[dict(selected=1, body="521000", syringe="")]), catalogue=data)
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual(plan["product_suggestions"][0]["product_code"], "420004")
        self.assertEqual(plan["actions"][0]["item"]["item_code"], "420004")

    def test_explicit_product_code_overrides_are_not_replaced(self):
        data = self.legacy_catalogue()
        data.tables["Item"].append(item("420XYZ", "Product"))
        plan = plans.build_plan(self.request(product_only=1, rvm_check=1,
            product_variants=[dict(selected=1, body="521000", syringe="", product_code="420XYZ")]), catalogue=data)
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["actions"][0]["item"]["item_code"], "420XYZ")

    def test_explicit_retired_product_code_is_rejected_before_review(self):
        data = self.legacy_catalogue()
        data.retired_codes = {"420XYZ"}
        plan = plans.build_plan(self.request(product_only=1, rvm_check=1,
            product_variants=[dict(selected=1, body="521000", syringe="", product_code="420XYZ")]), catalogue=data)
        self.assertTrue(any("retired or reserved" in row["message"] for row in plan["errors"]))

    def test_existing_matching_product_is_reused_before_allocating_a_duplicate(self):
        data = self.legacy_catalogue()
        doc = self.request(product_only=1, rvm_check=1,
            product_variants=[dict(selected=1, body="521000", syringe="", product_code="420XYZ")])
        materialize(plans.build_plan(doc, catalogue=data), data)
        next(row for row in data.tables["Item"] if row["name"] == "420XYZ")["item_name"] = "Existing catalogue label"
        doc.product_variants[0]["product_code"] = ""
        for group in ("Product", "Products"):
            with self.subTest(group=group):
                next(row for row in data.tables["Item"] if row["name"] == "420XYZ")["item_group"] = group
                plan = plans.build_plan(doc, catalogue=ReuseCatalogue(data.tables))
                self.assertTrue(plan["ready"], plan["errors"])
                self.assertEqual(plan["actions"][0]["item_action"], "reuse")
                self.assertEqual(plan["product_suggestions"][0]["product_code"], "420XYZ")
                self.assertEqual(plan["actions"][0]["item"]["item_name"], "Existing catalogue label")

    def test_unique_reference_held_by_another_item_blocks_duplicate_in_preview(self):
        data = self.legacy_catalogue()
        expected = plans.build_plan(self.request(product_only=1, rvm_check=1,
            product_variants=[dict(selected=1, body="521000", syringe="")]), catalogue=data)["actions"][0]["item"]
        for code, group, disabled in (("420OLD", "Product", 1), ("OTHER-ITEM", "Raw Material", 0)):
            with self.subTest(owner=code):
                owner = item(code, group)
                owner.update(reference_code=expected["reference_code"], disabled=disabled)
                candidate = copy.deepcopy(data.tables)
                candidate["Item"].append(owner)
                plan = plans.build_plan(self.request(product_only=1, rvm_check=1,
                    product_variants=[dict(selected=1, body="521000", syringe="")]), catalogue=ReuseCatalogue(candidate))
                self.assertFalse(plan["ready"])
                self.assertTrue(any("already belongs to" in row["message"] for row in plan["errors"]))

    def test_product_numbering_continues_with_letters_after_decimal_capacity(self):
        from amf.amf.utils.item_creation_product_codes import suggest_product_code
        inventory = [dict(item_code="420" + str(number).zfill(3), item_group="Product",
                          item_name="Other Product", reference_code="Other reference") for number in range(1, 1000)]
        code, reason = suggest_product_code(dict(item_code="420080", item_name="New Product", reference_code="New"),
                                            "420", inventory, set(), set())
        self.assertEqual(code, "42000A")

    def test_a_code_taken_after_review_requires_a_new_review(self):
        data = self.legacy_catalogue()
        data.retired_codes = set()
        doc = self.request(product_only=1, rvm_check=1,
            product_variants=[dict(selected=1, body="521000", syringe="")])
        reviewed = plans.build_plan(doc, catalogue=data)
        doc.review_status, doc.approved_plan_hash = "Reviewed", reviewed["fingerprint"]
        doc.approved_input_hash = reviewed["input_hash"]
        data.retired_codes.add(reviewed["actions"][0]["item"]["item_code"])
        current = plans.build_plan(doc, catalogue=data)
        self.assertNotEqual(reviewed["fingerprint"], current["fingerprint"])
        with patch.object(workflow, "_lock_source"), patch.object(workflow, "build_plan", return_value=current), \
                patch.object(frappe, "flags", frappe._dict(mute_messages=True)):
            with self.assertRaisesRegex(frappe.ValidationError, "stale"):
                workflow.validate_submission(doc)


if __name__ == "__main__":
    unittest.main()
