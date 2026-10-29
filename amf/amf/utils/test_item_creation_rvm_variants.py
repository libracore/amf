import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from amf.amf.utils import item_creation_compatibility as compatibility
from amf.amf.utils import item_creation_plan as plans
from amf.amf.utils import item_creation_workflow as workflow
from amf.amf.utils.test_item_creation_plan import MemoryCatalogue, catalogue, item, materialize, source


RVM_EXPECTED = {
    "511000": ("410", "P200O300ABC"), "521000": ("420", "P201O300ABC"),
    "521001": ("420", "P201O300ABCRSB"), "521002": ("422", "P201O300ABCRS485"),
    "521003": ("420", "P201O300ABCLPH"), "521004": ("420", "P201O300ABCAIR"),
    "521005": ("420", "P201O300ABCELV"), "521006": ("420", "P201O300ABCSYS"),
    "521101": ("421", "P211O300ABC"), "5D1000": ("4D0", "P202O300ABC"),
    "5D1001": ("4D1", "P202O300ABC/RS485"), "5D1002": ("4D2", "P202O300ABC/CAN"),
}


class TestRvmVariants(unittest.TestCase):
    def setUp(self):
        self.context = patch.object(frappe, "db", SimpleNamespace(
            get_value=Mock(return_value=frappe._dict(company="AMF", is_group=0, disabled=0))))
        self.context.start()
        self.addCleanup(self.context.stop)

    def request(self, bodies=RVM_EXPECTED):
        return source(rvm_check=1, product_variants=[dict(selected=1, body=body, syringe="") for body in bodies])

    def test_all_current_variants_have_distinct_codes_and_correct_references(self):
        data = catalogue()
        plan = plans.build_plan(self.request(), catalogue=data)
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual(len(plan["actions"]), 17)
        self.assertEqual(len({row["item"]["item_code"] for row in plan["actions"]}), 17)
        for row in plan["product_suggestions"]:
            prefix, reference = RVM_EXPECTED[row["body"]]
            self.assertTrue(row["product_code"].startswith(prefix))
            self.assertEqual(row["product_reference"], reference)
        products = {next(row["item_code"] for row in action["materials"] if row["item_code"] in RVM_EXPECTED): action
                    for action in plan["actions"] if action["item"]["item_group"] == "Product"}
        self.assertEqual(products["521000"]["item"]["item_code"], "420ABC")
        self.assertEqual(products["521101"]["item"]["item_code"], "421ABC")
        self.assertEqual(products["521002"]["item"]["item_code"], "422ABC")
        self.assertEqual(products["521101"]["item"]["weight_per_unit"], .7)
        for body in ("5D1000", "5D1001", "5D1002"):
            self.assertEqual(products[body]["item"]["weight_per_unit"], .1)
        self.assertTrue(any("I2C address" in warning for warning in plan["warnings"]))
        self.assertEqual(data.variant_reads, 1)
        self.assertLessEqual(sum(row[0] == "Item" for row in data.reads), 2)

    def test_shared_prefix_allocation_is_independent_of_grid_row_order(self):
        doc = self.request()
        first = plans.build_plan(doc, catalogue=catalogue())
        doc.product_variants.reverse()
        second = plans.build_plan(doc, catalogue=catalogue())
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_entered_codes_are_kept_free_for_their_rows_during_automatic_allocation(self):
        doc = self.request(("521000", "521001", "521004"))
        doc.product_variants[-1]["product_code"] = "420001"
        plan = plans.build_plan(doc, catalogue=catalogue())
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual({row["body"]: row["product_code"] for row in plan["product_suggestions"]},
                         {"521000": "420ABC", "521001": "420002", "521004": "420001"})

    def legacy_variant_catalogue(self):
        doc, data = self.request(("521002", "521101")), catalogue()
        original = plans.build_plan(doc, catalogue=data)
        mapping = {"422ABC": "420099", "421ABC": "430081"}
        for action in original["actions"]:
            code = action["item"]["item_code"]
            action["item"]["item_code"] = mapping.get(code, code)
        materialize(original, data)
        doc.update(dict(product_only=1, head_check="No", head_item="300ABC", plug_check="No", seat_check="No"))
        return doc, data

    def test_legacy_rs485_and_nmth_products_are_reused_without_renumbering(self):
        doc, data = self.legacy_variant_catalogue()
        before = copy.deepcopy(data.tables)
        plan = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual({row["body"]: row["product_code"] for row in plan["product_suggestions"]},
                         {"521002": "420099", "521101": "430081"})
        self.assertTrue(all(row["item_action"] == row["bom_action"] == "reuse" for row in plan["actions"]))
        self.assertEqual({key: data.tables[key] for key in before}, before)

    def test_legacy_reference_reuse_still_requires_the_reviewed_bom_composition(self):
        doc, data = self.legacy_variant_catalogue()
        row = next(row for row in data.tables["BOM Item"]
                   if row["parent"] == "BOM-420099" and row["item_code"] == "521002")
        row["item_code"] = "521000"
        plan = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
        self.assertFalse(plan["ready"])
        self.assertEqual(next(row for row in plan["product_suggestions"] if row["body"] == "521002")["product_code"],
                         "420099")
        self.assertEqual(row["item_code"], "521000")

    def test_new_overrides_use_dedicated_prefixes_and_old_prefixes_are_reuse_only(self):
        for body, old_code, new_code in (("521002", "420XYZ", "422XYZ"), ("521101", "430XYZ", "421XYZ")):
            with self.subTest(body=body):
                doc = self.request((body,))
                doc.product_variants[0]["product_code"] = old_code
                self.assertFalse(plans.build_plan(doc, catalogue=catalogue())["ready"])
                doc.product_variants[0]["product_code"] = new_code
                plan = plans.build_plan(doc, catalogue=catalogue())
                self.assertTrue(plan["ready"], plan["errors"])
                self.assertEqual(plan["product_suggestions"][0]["product_code"], new_code)

    def test_disabled_and_retired_legacy_reference_owners_block_duplicates(self):
        for problem in ("disabled", "retired"):
            with self.subTest(problem=problem):
                doc, data = self.legacy_variant_catalogue()
                owner = next(row for row in data.tables["Item"] if row["name"] == "420099")
                if problem == "disabled":
                    owner["disabled"] = 1
                else:
                    owner["name"] = "/420099"
                plan = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
                self.assertFalse(plan["ready"])
                self.assertTrue(any("already belongs to" in row["message"] for row in plan["errors"]))

    def test_existing_exact_variant_references_reuse_items_and_boms(self):
        doc, data = self.request(), catalogue()
        materialize(plans.build_plan(doc, catalogue=data), data)
        doc.update(dict(product_only=1, head_check="No", head_item="300ABC", plug_check="No", seat_check="No"))
        plan = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual(len(plan["actions"]), 12)
        self.assertTrue(all(row["item_action"] == row["bom_action"] == "reuse" for row in plan["actions"]))

    def test_additional_511_and_521_variants_are_discovered_without_a_code_edit(self):
        data = catalogue()
        for code, reference in (("511001", "P200-O.RS485"), ("52100A", "P201-O.CAN")):
            body = item(code, "Body")
            body["reference_code"] = reference
            data.tables["Item"].append(body)
        doc = self.request(("511001", "52100A"))
        plan = plans.build_plan(doc, catalogue=data)
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual({row["body"]: row["product_reference"] for row in plan["product_suggestions"]},
                         {"511001": "P200O300ABCRS485", "52100A": "P201O300ABCCAN"})
        with patch.object(workflow, "_source_for_preview", return_value=doc), \
                patch.object(frappe, "get_all", return_value=[frappe._dict(row) for row in data.tables["Item"]]):
            choices = workflow.get_compatible_variants({})
        self.assertTrue({"511001", "52100A"}.issubset({row["body"] for row in choices}))

    def test_disabled_or_undefined_additional_bodies_cannot_be_reviewed(self):
        for reference, disabled in (("P201-O.CAN", 1), ("UNDEFINED", 0), (None, 0)):
            with self.subTest(reference=reference, disabled=disabled):
                data = catalogue()
                body = item("52100A", "Body")
                body.update(reference_code=reference, disabled=disabled)
                data.tables["Item"].append(body)
                plan = plans.build_plan(self.request(("52100A",)), catalogue=data)
                self.assertFalse(plan["ready"])

    def test_variant_reference_changes_invalidate_the_dependency_snapshot(self):
        data = catalogue()
        body = item("52100A", "Body")
        body["reference_code"] = "P201-O.CAN"
        data.tables["Item"].append(body)
        doc = self.request(("52100A",))
        first = plans.build_plan(doc, catalogue=MemoryCatalogue(copy.deepcopy(data.tables)))
        body["reference_code"] = "P201-O.RS485"
        second = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_lph_exact_address_reference_is_an_explicit_reviewed_override(self):
        doc, data = self.request(("521003",)), catalogue()
        doc.product_variants[0]["product_reference"] = "P201O300ABCI2C2LPH"
        original = plans.build_plan(doc, catalogue=data)
        materialize(original, data)
        doc.update(dict(product_only=1, head_check="No", head_item="300ABC", plug_check="No", seat_check="No"))
        plan = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual(plan["actions"][0]["item"]["reference_code"], "P201O300ABCI2C2LPH")
        self.assertEqual(plan["actions"][0]["item_action"], "reuse")

    def test_variant_table_has_a_bounded_request_size(self):
        doc = self.request(("521000",))
        doc.product_variants *= compatibility.MAX_VARIANTS + 1
        rows, errors = compatibility.validate_selections(doc)
        self.assertEqual(rows, [])
        self.assertTrue(any("Too many" in error for error in errors))

    def test_historical_bom_names_are_skipped_without_reusing_earlier_revisions(self):
        bom = SimpleNamespace(item="210ABC", name="BOM-210ABC-001", set_new_name=Mock())
        with patch.object(frappe.db, "sql", create=True, return_value=[("bom-210abc-001",), ("BOM-210ABC-002",)]):
            workflow._set_available_bom_name(bom)
        self.assertEqual(bom.name, "BOM-210ABC-003")
        bom.name = "BOM-210ABC-004"
        with patch.object(frappe.db, "sql", create=True, return_value=[("BOM-210ABC-001",)]):
            workflow._set_available_bom_name(bom)
        self.assertEqual(bom.name, "BOM-210ABC-004")


if __name__ == "__main__":
    unittest.main()
