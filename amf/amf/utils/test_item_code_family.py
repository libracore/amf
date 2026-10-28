import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from amf.amf.utils import item_code_family as family
from amf.amf.doctype.item_creation import item_creation


class RegistryDB:
    def __init__(self, items=()):
        self.items = list(items)
        self.series = set()
        self.queries = []
        self.commit = Mock()
        self.rollback = Mock()

    def sql(self, query, values=None, as_dict=False):
        self.queries.append((query, values))
        if "INSERT" in query:
            self.series.add(values)
            return []
        if "FROM `tabItem`" in query:
            return self.items
        if "name IN" in query:
            return [(key,) for key in values if key in self.series]
        if "CHAR_LENGTH" in query:
            return [(key,) for key in self.series if key.startswith(family.REGISTRY_PREFIX)
                    and len(key) == len(family.REGISTRY_PREFIX) + 3]
        return [(values,)] if values in self.series else []


class Doc(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)

    def set(self, key, value):
        setattr(self, key, value)


class TestItemCodeFamily(unittest.TestCase):
    def setUp(self):
        self.local = SimpleNamespace()
        self.db = RegistryDB()
        self.patches = [patch.object(frappe, "local", self.local),
                        patch.object(frappe, "db", self.db),
                        patch.object(frappe, "throw", side_effect=self.throw)]
        for context in self.patches:
            context.start()
            self.addCleanup(context.stop)

    @staticmethod
    def throw(message, *args, **kwargs):
        raise frappe.ValidationError(message)

    def test_every_layer_and_variant_blocks_the_same_suffix(self):
        for code in ("100001", "101001", "110001", "20C001", "211001", "301001",
                     "420001", "46E001", "4D1001", "4D2001"):
            with self.subTest(code=code):
                self.assertEqual(family.next_available_suffix([code]), "002")

    def test_retired_disabled_and_variant_aliases_remain_reserved(self):
        rows = [{"item_code": "/420001", "disabled": 1},
                {"item_code": "4D0002-P", "disabled": 0},
                {"item_code": "//20C003", "disabled": 1}]
        self.assertEqual(family.next_available_suffix(rows), "004")

    def test_non_chain_stock_does_not_occupy_a_head_suffix(self):
        self.assertEqual(family.next_available_suffix(["511001", "701001", "MAT.1001", "SPL.3013"]), "001")

    def test_custom_product_group_is_included(self):
        self.assertEqual(family.next_available_suffix([
            {"item_code": "UF0001", "item_group": "Product"}]), "002")

    def test_numeric_then_alphanumeric_order_and_existing_letters(self):
        rows = ["420%03d" % n for n in range(1, 1000)]
        self.assertEqual(family.next_available_suffix(rows), "00A")
        self.assertEqual(family.next_available_suffix(rows + ["20C00A"]), "00B")

    def test_same_suffix_is_blocked_across_old_four_digit_ranges(self):
        self.assertEqual(family.next_available_suffix(["301001"]), "002")

    def test_suffix_domain_and_exhaustion(self):
        for value in ("000", "AB", "ABCD", "A_B", "é12", "１２３"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                family.normalize_suffix(value)
        suffixes = list(family.iter_suffixes())
        self.assertEqual(len(suffixes), 46655)
        self.assertEqual(len(set(suffixes)), 46655)
        with self.assertRaises(ValueError):
            family.next_available_suffix([], suffixes)

    def test_production_collision_rejects_085(self):
        self.db.items = [{"item_code": "420085", "item_group": "Product"}]
        with self.assertRaisesRegex(frappe.ValidationError, "already used"):
            family.reserve_suffix("085", ("Item Creation", "REQUEST-A"))
        self.assertNotIn(family.REGISTRY_PREFIX + "085", self.db.series)

    def test_request_reservation_is_durable_idempotent_and_has_an_owner(self):
        family.reserve_suffix("ABC", ("Item Creation", "REQUEST-A"))
        family.reserve_suffix("ABC", ("Item Creation", "REQUEST-A"))
        self.assertTrue(family.is_reserved_for("ABC", ("Item Creation", "REQUEST-A")))
        with self.assertRaisesRegex(frappe.ValidationError, "another creation"):
            family.reserve_suffix("ABC", ("Item Creation", "REQUEST-B"))
        self.assertIn("ABC", family.get_reservations())
        self.db.commit.assert_not_called()

    def test_preview_includes_pending_request_reservations(self):
        family.reserve_suffix("001", ("Item Creation", "REQUEST-A"))
        self.assertEqual(family.suggest_suffix(), "002")

    def test_verified_continuation_is_separate_from_fresh_allocation(self):
        self.db.items = [{"item_code": "300ABC"}]
        family.reserve_suffix("ABC", ("Item Creation", "REQUEST-A"), continuation=True)
        with self.assertRaises(frappe.ValidationError):
            family.reserve_suffix("ABC", ("Item", "100ABC"))

    def test_family_context_cannot_insert_a_different_suffix(self):
        with family.family_creation(("Item Creation", "REQUEST-A"), "ABC"):
            with self.assertRaisesRegex(frappe.ValidationError, "must use"):
                family.validate_new_item_family(Doc(item_code="100ABD"))
        self.assertIsNone(self.local.amf_item_code_family)

    def test_new_item_guard_checks_the_full_chain(self):
        self.db.items = [{"item_code": "46E085"}]
        with self.assertRaises(frappe.ValidationError):
            family.validate_new_item_family(Doc(item_code="100085", item_group="Plug"))

    def test_new_item_guard_reserves_an_alphanumeric_family(self):
        doc = Doc(item_code="100abc", item_group="Plug")
        family.validate_new_item_family(doc)
        self.assertEqual(doc.item_code, "100ABC")
        self.assertTrue(family.is_reserved_for("ABC", ("Item", "100ABC")))

    def test_new_alias_cannot_bypass_the_reserved_six_character_namespace(self):
        with self.assertRaisesRegex(frappe.ValidationError, "exactly six"):
            family.validate_new_item_family(Doc(item_code="420ABC-P", item_group="Product"))

    def test_trusted_family_scans_member_occupancy_once(self):
        source = ("Item Creation", "REQUEST-A")
        family.reserve_suffix("ABC", source)
        self.db.queries.clear()
        with family.family_creation(source, "ABC"):
            for code in ("100ABC", "200ABC", "300ABC"):
                family.validate_new_item_family(Doc(item_code=code))
        self.assertEqual(sum("FROM `tabItem`" in query for query, values in self.db.queries), 1)

    def test_deleted_item_code_cannot_be_reissued_by_its_old_family_owner(self):
        family.validate_new_item_family(Doc(item_code="100ABC", item_group="Plug"))
        # The original Item's reservation survives, even when Item is absent.
        with self.assertRaisesRegex(frappe.ValidationError, "already allocated"):
            family.validate_new_item_family(Doc(item_code="100ABC", item_group="Plug"))

    def test_retired_member_code_cannot_be_reissued_within_an_existing_family(self):
        self.db.items = [{"item_code": "/110ABC"}]
        family.reserve_suffix("ABC", ("Item Creation", "REQUEST-A"), continuation=True)
        with family.family_creation(("Item Creation", "REQUEST-A"), "ABC"):
            with self.assertRaisesRegex(frappe.ValidationError, "already allocated"):
                family.validate_new_item_family(Doc(item_code="110ABC", item_group="Plug"))

    def test_new_product_bom_allows_a_different_head_suffix(self):
        doc = Doc(__islocal=1, item="46EABC", items=[Doc(item_code="300ABD")])
        family.validate_new_bom_family(doc)

    def test_product_in_a_creation_context_does_not_claim_its_own_head_suffix(self):
        source = ("Item Creation", "REQUEST-A")
        family.reserve_suffix("ABC", source)
        family.reserve_suffix("XYZ", ("Item Creation", "OTHER-HEAD"))
        with family.family_creation(source, "ABC"):
            family.validate_new_item_family(Doc(item_code="46EXYZ", item_group="Product"))
        self.assertIn(family.MEMBER_PREFIX + "46EXYZ", self.db.series)
        self.assertFalse(family.is_reserved_for("XYZ", source))

    def test_standalone_product_reserves_its_referenced_head_family(self):
        self.db.get_value = Mock(return_value=frappe._dict(item_group="Valve Head", disabled=0))
        with patch.object(family, "validate_existing_head_family"):
            source = family._product_head_source(Doc(reference_code="P101O300ABDS2500P"), "46EXYZ")
        self.assertEqual(source, ("Item", "300ABD"))

    def test_new_head_bom_checks_retired_component_aliases_too(self):
        doc = Doc(__islocal=1, item="300ABC", items=[Doc(item_code="/100ABD")])
        with self.assertRaisesRegex(frappe.ValidationError, "another head suffix"):
            family.validate_new_bom_family(doc)

    def test_new_sub_assembly_bom_cannot_hide_another_component_suffix(self):
        with self.assertRaisesRegex(frappe.ValidationError, "another head suffix"):
            family.validate_new_bom_family(Doc(__islocal=1, item="110ABC",
                                              items=[Doc(item_code="100ABD")]))

    def test_existing_head_checks_the_component_below_its_sub_assembly(self):
        docs = {
            ("Item", "300ABC"): Doc(default_bom="HEAD-BOM"),
            ("Item", "110ABC"): Doc(disabled=0, default_bom="PLUG-BOM"),
            ("BOM", "HEAD-BOM"): Doc(name="HEAD-BOM", item="300ABC", docstatus=1,
                is_active=1, items=[Doc(item_code="110ABC", bom_no="PLUG-BOM")]),
            ("BOM", "PLUG-BOM"): Doc(name="PLUG-BOM", item="110ABC", docstatus=1,
                is_active=1, items=[Doc(item_code="100ABD")]),
        }
        with patch.object(frappe, "get_doc", side_effect=lambda *key: docs[key]):
            with self.assertRaisesRegex(frappe.ValidationError, "another suffix"):
                item_creation._validate_existing_head_family("300ABC")

    def test_old_bom_edits_do_not_automatically_rewrite_legacy_data(self):
        family.validate_new_bom_family(Doc(item="46EABC", items=[Doc(item_code="300ABD")]))

    def test_draft_changes_and_direct_submission_are_rechecked(self):
        for docstatus, method in ((0, "before_save"), (1, "before_submit")):
            with self.subTest(method=method), self.assertRaisesRegex(frappe.ValidationError, "exactly one Valve Head"):
                family.validate_new_bom_family(Doc(docstatus=docstatus, item="46EABC",
                                                  items=[]), method)

    def test_custom_product_bom_still_requires_exactly_one_head(self):
        self.db.get_value = Mock(return_value="Product")
        family.validate_new_bom_family(Doc(__islocal=1, item="UF0ABC", items=[Doc(item_code="300ABD")]))
        with self.assertRaisesRegex(frappe.ValidationError, "exactly one Valve Head"):
            family.validate_new_bom_family(Doc(__islocal=1, item="UF0ABC",
                                              items=[Doc(item_code="300ABD"), Doc(item_code="300ABC")]))

    def test_family_context_leaves_transaction_methods_with_the_request(self):
        commit, rollback = self.db.commit, self.db.rollback
        with family.atomic_family_creation():
            self.assertTrue(self.local.amf_atomic_family_creation)
            self.assertIs(self.db.commit, commit)
            self.assertIs(self.db.rollback, rollback)
        self.assertFalse(self.local.amf_atomic_family_creation)
        commit.assert_not_called()
        rollback.assert_not_called()

    def test_family_failure_propagates_and_restores_context(self):
        with self.assertRaisesRegex(RuntimeError, "injected"):
            with family.atomic_family_creation():
                raise RuntimeError("injected")
        self.assertFalse(self.local.amf_atomic_family_creation)

    def test_saving_source_derives_all_alphanumeric_member_codes(self):
        doc = Doc(doctype="Item Creation", name="REQUEST-A", head_check="Yes",
                  head_code="300ABC", plug_check="Yes", seat_check="Yes")
        item_creation._validate_source_family(doc)
        self.assertEqual(doc.plug_code, "100ABC")
        self.assertEqual(doc.seat_code, "200ABC")
        self.assertTrue(family.is_reserved_for("ABC", (doc.doctype, doc.name)))

    def test_source_rejects_cross_family_component_reuse(self):
        doc = Doc(doctype="Item Creation", name="REQUEST-A", head_check="Yes",
                  head_code="300ABC", plug_check="No", plug_item="100ABD", seat_check="Yes")
        with self.assertRaisesRegex(frappe.ValidationError, "reviewed replacement"):
            item_creation._validate_source_family(doc)

    def test_item_creation_submit_executes_on_the_server(self):
        doc = Doc(doctype="Item Creation", name="REQUEST-A", head_code="300ABC")
        with patch.object(item_creation, "_execute_creation_plan") as execute:
            item_creation.ItemCreation.on_submit(doc)
        execute.assert_called_once_with(doc)

    def test_legacy_http_group_creation_cannot_bypass_reservation(self):
        with self.assertRaisesRegex(frappe.ValidationError, "complete reserved family"):
            item_creation.create_item_from_doc({"head_code": "300085"}, "head")

    def test_builders_accept_three_characters_and_preserve_six_characters(self):
        codes = item_creation.get_bom_managed_family_codes("ABC")
        self.assertEqual(set(codes.values()), {"100ABC", "110ABC", "200ABC", "210ABC", "300ABC"})
        self.assertEqual(item_creation.get_sub_assembly_item_code_for_component("Plug", "100ABC"), "110ABC")

    def test_hv_recipe_keeps_selected_screws_and_consumed_adapter(self):
        self.db.get_value = Mock(return_value="SYR-2500-P")
        doc = Doc(head_code="300ABC", head_rnd="V-D-HV", head_description="HV head",
                  screw_type="SPL.3028", screw_quantity=2)
        data, materials = item_creation._prepare_pump_hv_data(doc, "6", "E")
        self.assertEqual(data["item_code"], "46EABC")
        self.assertIn({"item_code": "SPL.3028", "qty": 2}, materials)
        self.assertIn({"item_code": "RVM.1204", "qty": 1}, materials)

    def test_lv_laboratory_recipe_keeps_cable_and_adapter_scrap(self):
        self.db.get_value = Mock(return_value="SYR-500-P")
        doc = Doc(head_code="300ABC", head_rnd="V-D", head_description="Head",
                  screw_type="SPL.3028", screw_quantity=2)
        data, materials, scraps = item_creation._prepare_pump_data(doc, "7", "8")
        self.assertEqual(data["item_code"], "478ABC")
        self.assertIn({"item_code": "T100", "qty": 1}, materials)
        self.assertEqual(scraps, [{"item_code": "RVM.1204", "qty": 1}])


if __name__ == "__main__":
    unittest.main()
