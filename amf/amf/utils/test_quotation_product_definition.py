import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from amf.amf.utils import quotation_product_definition as products


class TestProductFamilyResolution(unittest.TestCase):
    def setUp(self):
        self.body = frappe._dict(name="521000", item_code="521000", reference_code="P201-O")
        self.head = frappe._dict(name="300ABC", item_code="300ABC")
        self.product = frappe._dict(name="420ABC", item_code="420ABC")
        self.bom = SimpleNamespace(item="420ABC", docstatus=1, is_active=1,
                               items=[frappe._dict(item_code="521000"),
                                      frappe._dict(item_code="300ABC"),
                                      frappe._dict(item_code="SPL.3013")])
        self.groups = {"521000": "Body", "300ABC": "Valve Head", "SPL.3013": "Part"}
        contexts = [patch.object(products.frappe, "db", Mock()),
                    patch.object(products.frappe, "get_doc", return_value=self.bom),
                    patch.object(products.frappe, "get_all", side_effect=self.get_groups)]
        self.db = contexts[0].start()
        self.addCleanup(contexts[0].stop)
        self.db.get_value.return_value = "BOM-420ABC-001"
        for context in contexts[1:]:
            context.start()
            self.addCleanup(context.stop)

    def get_groups(self, *args, **kwargs):
        return [frappe._dict(name=code, item_group=group) for code, group in self.groups.items()]

    def matches(self, syringe=None):
        return products.product_matches_configuration(self.product, self.body, self.head, syringe)

    def test_alphanumeric_family_and_exact_core_bom_match(self):
        self.assertTrue(self.matches())

    def test_same_suffix_does_not_authorize_the_wrong_body(self):
        self.body.item_code = "511000"
        self.assertFalse(self.matches())

    def test_product_suffix_can_differ_when_the_actual_bom_matches(self):
        self.product.item_code = "420085"
        self.product.name = self.bom.item = "420085"
        self.assertTrue(self.matches())

    def test_resolver_accepts_the_reference_match_with_a_different_product_suffix(self):
        self.product.name = self.product.item_code = self.bom.item = "420XYZ"
        with patch.object(products, "get_item_reference", side_effect=[self.body, self.head]), \
                patch.object(products, "get_product_item_by_reference", return_value=self.product), \
                patch.object(products, "get_product_item_by_code") as fallback:
            result = products.resolve_product_definition_item("521000", "300ABC")
        self.assertEqual(result["item_code"], "420XYZ")
        fallback.assert_not_called()

    def test_reference_match_cannot_override_actual_head(self):
        self.bom.items[1].item_code = "300033"
        self.groups["300033"] = "Valve Head"
        self.assertFalse(self.matches())

    def test_syringe_must_match_the_bom(self):
        syringe = frappe._dict(item_code="70E000")
        self.assertFalse(self.matches(syringe))
        self.groups["70E000"] = "Syringe"
        self.bom.items.append(frappe._dict(item_code="70E000"))
        self.assertTrue(self.matches(syringe))
        self.assertFalse(self.matches())

    def test_disabled_parts_and_invalid_defaults_are_rejected(self):
        self.head.disabled = 1
        self.assertFalse(self.matches())
        self.head.disabled = 0
        for field, value in (("docstatus", 0), ("is_active", 0), ("item", "420ABD")):
            with self.subTest(field=field):
                original = getattr(self.bom, field)
                setattr(self.bom, field, value)
                self.assertFalse(self.matches())
                setattr(self.bom, field, original)

    def test_resolver_reports_review_when_both_candidates_disagree(self):
        with patch.object(products, "get_item_reference", side_effect=[self.body, self.head]), \
                patch.object(products, "get_product_item_by_reference", return_value=self.product), \
                patch.object(products, "get_product_item_by_code", return_value=self.product):
            self.bom.items[1].item_code = "300033"
            result = products.resolve_product_definition_item("521000", "300ABC")
        self.assertEqual(result["error"], "configuration_mismatch")
        self.assertNotIn("item_code", result)

    def test_mini_body_interfaces_keep_distinct_six_character_codes(self):
        for body_code, expected in (("5D1000", "4D0ABC"), ("5D1001", "4D1ABC"),
                                    ("5D1002", "4D2ABC")):
            self.assertEqual(products.make_fallback_item_code(
                {"item_code": body_code}, self.head), expected)


if __name__ == "__main__":
    unittest.main()
