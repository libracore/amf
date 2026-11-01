import copy
import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from amf.amf.utils import item_creation_compatibility as compatibility
from amf.amf.utils import item_creation_plan as plans
from amf.amf.utils import item_creation_workflow as workflow
from amf.amf.utils import item_creation_traceability as traceability


class MemoryCatalogue(plans.Catalogue):
    def __init__(self, tables=None):
        super().__init__()
        self.tables = tables or defaultdict(list)
        self.reads = []
        self.variant_reads = 0

    def rows(self, doctype, fields, key, names):
        if not names:
            return []
        self.reads.append((doctype, key, len(names)))
        return [frappe._dict({key: row.get(key) for key in fields}) for row in self.tables[doctype]
                if row.get(key) in names]

    def raw_candidates(self, tags):
        return [dict(row) for row in self.tables["Item"] if row["item_group"] == "Raw Material"
                and row.get("tag_raw_mat") in tags and not row.get("disabled")]

    def product_code_inventory(self, references=()):
        return self.tables["Item"]

    def rvm_bodies(self):
        self.variant_reads += 1
        return [dict(row) for row in self.tables["Item"] if row["item_group"] == "Body"
                and compatibility.RVM_BODY_RE.fullmatch(row["name"])]

    def reserved_product_codes(self):
        return set()


def item(code, group, **fields):
    return dict(name=code, item_name=code, item_group=group, reference_code=code,
                stock_uom="Nos", modified="2026-10-27 12:00:00", disabled=0, default_bom=None,
                include_item_in_manufacturing=1,
                **fields)


def source(**fields):
    result = frappe._dict(doctype="Item Creation", name="TEST-REQUEST", head_check="Yes", head_code="300ABC",
        head_name="VALVE HEAD-D-1-6-050-C-P", head_rnd="V-D-1-6-050-C-P", head_description="Reviewed head",
        plug_check="Yes", plug_name="PLUG-D-1-6-050-P", plug_rnd="P-TEST", plug_mat="PTFE", plug_acc=6,
        seat_check="Yes", seat_name="SEAT-D-1-6-050-C", seat_rnd="S-TEST", seat_mat="PCTFE", seat_pin_item="SPL.3039", seat_acc=2,
        plug_raw_material="RAW-P", plug_raw_qty=0.02, plug_raw_uom="Meter",
        seat_raw_material="RAW-C", seat_raw_qty=0.03, seat_raw_uom="Meter", company="AMF", default_warehouse="Main",
        screw_type="SCREW", screw_quantity=2, cap_type="CAP", product_variants=[], rvm_check=0, pump_check=0, pump_hv_check=0)
    result.update(fields)
    return result


def catalogue():
    tables = defaultdict(list)
    for code, group in (("SPL.3013", "Part"), ("SPL.3039", "Part"), ("SCREW", "Part"), ("CAP", "Part"),
                        ("RVM.1204", "Part"), ("C100", "Part"), ("C101", "Part"), ("T100", "Part")):
        tables["Item"].append(item(code, group))
    for code, tag in (("RAW-P", "PTFE"), ("RAW-C", "PCTFE")):
        row = item(code, "Raw Material", tag_raw_mat=tag)
        row["stock_uom"] = "Meter"
        tables["Item"].append(row)
    for rule in compatibility.BODY_RULES:
        body = item(rule[0], "Body")
        body["reference_code"] = rule[4]
        tables["Item"].append(body)
    for token in "234589DEF":
        row = item("70" + token + "000", "Syringe")
        row["reference_code"] = compatibility.SYRINGE_REFERENCES[token]
        tables["Item"].append(row)
    return MemoryCatalogue(tables)


def materialize(plan, data):
    for action in plan["actions"]:
        values = action["item"]
        code = values["item_code"]
        existing = item(code, values["item_group"])
        existing.update({key: values.get(key) for key in ("item_name", "reference_code", "tag_raw_mat", "stock_uom")})
        existing["default_bom"] = "BOM-" + code
        data.tables["Item"].append(existing)
        data.tables["BOM"].append(dict(name="BOM-"+code, item=code, docstatus=1, is_active=1, is_default=1,
            company="AMF", quantity=1, uom="Nos", with_operations=0, modified="2026-10-27 12:00:00"))
        for index, row in enumerate(action["materials"], 1):
            row = dict(row, parent="BOM-"+code, idx=index)
            if row["bom_no"].startswith("@new:"):
                row["bom_no"] = "BOM-" + row["bom_no"][5:]
            data.tables["BOM Item"].append(row)
        for index, row in enumerate(action["scraps"], 1):
            data.tables["BOM Scrap Item"].append(dict(row, parent="BOM-"+code, idx=index))


class TestItemCreationPlan(unittest.TestCase):
    def setUp(self):
        self.db = SimpleNamespace(get_value=Mock(return_value=frappe._dict(company="AMF", is_group=0, disabled=0)))
        self.contexts = [patch.object(frappe, "db", self.db),
                         patch.object(frappe, "throw", side_effect=lambda message, *args: (_ for _ in ()).throw(frappe.ValidationError(message)))]
        for context in self.contexts:
            context.start()
            self.addCleanup(context.stop)

    def test_complete_head_includes_both_raw_material_boms(self):
        plan = plans.build_plan(source(), catalogue=catalogue())
        self.assertEqual(plan["errors"], [])
        self.assertEqual(plan["summary"]["new_boms"], 5)
        self.assertEqual([row["item"]["item_code"] for row in plan["actions"]],
                         ["100ABC", "110ABC", "200ABC", "210ABC", "300ABC"])
        self.assertEqual(plan["actions"][0]["materials"][0]["uom"], "Meter")
        self.assertEqual(plan["actions"][0]["materials"][0]["qty"], 0.02)
        self.assertNotIn("valuation_rate", plan["actions"][0]["item"])

    def test_missing_stock_does_not_guess_a_rod_or_quantity(self):
        plan = plans.build_plan(source(plug_raw_material="", plug_raw_qty=0), catalogue=catalogue())
        self.assertFalse(plan["ready"])
        self.assertTrue(any("exact plug" in error["message"] for error in plan["errors"]))
        self.assertTrue(any("positive plug" in error["message"] for error in plan["errors"]))
        self.assertEqual(plan["raw_material_candidates"][0]["name"], "RAW-P")

    def test_raw_material_tag_and_current_stock_uom_are_enforced(self):
        for change in ({"plug_raw_material": "RAW-C"}, {"plug_raw_uom": "Nos"}, {"plug_raw_qty": float("nan")},
                       {"plug_raw_qty": 0.0000001}, {"plug_raw_qty": 1e12}):
            with self.subTest(change=change):
                self.assertFalse(plans.build_plan(source(**change), catalogue=catalogue())["ready"])

    def test_only_selected_products_are_generated(self):
        plan = plans.build_plan(source(rvm_check=1, product_variants=[dict(selected=1, body="521000", syringe="")]), catalogue=catalogue())
        self.assertEqual(plan["errors"], [])
        self.assertEqual(len(plan["actions"]), 6)
        self.assertEqual(plan["actions"][-1]["item"]["item_code"], "420ABC")
        self.assertNotIn("410ABC", [row["item"]["item_code"] for row in plan["actions"]])

    def test_product_code_override_keeps_the_selected_head_and_configuration(self):
        doc = source(rvm_check=1, product_variants=[dict(selected=1, body="521000", syringe="", product_code="420XYZ")])
        plan = plans.build_plan(doc, catalogue=catalogue())
        self.assertTrue(plan["ready"], plan["errors"])
        product = plan["actions"][-1]
        self.assertEqual(product["item"]["item_code"], "420XYZ")
        self.assertEqual(product["item"]["reference_code"], "P201O300ABC")
        self.assertIn("300ABC", [row["item_code"] for row in product["materials"]])
        self.assertNotEqual(plans.input_hash(doc), plans.input_hash(source(rvm_check=1,
            product_variants=[dict(selected=1, body="521000", syringe="")])))

    def test_product_override_cannot_reuse_a_conflicting_identity_or_configuration_prefix(self):
        doc = source(rvm_check=1, product_variants=[dict(selected=1, body="521000", syringe="", product_code="420XYZ")])
        data = catalogue()
        data.tables["Item"].append(item("420XYZ", "Product"))
        plan = plans.build_plan(doc, catalogue=data)
        self.assertTrue(any("different identity" in row["message"] for row in plan["errors"]))
        for code in ("410XYZ", "420000", "420XY_", "420XYZ-extra"):
            doc.product_variants[0]["product_code"] = code
            plan = plans.build_plan(doc, catalogue=catalogue())
            self.assertFalse(plan["ready"])
            self.assertTrue(any("Product code" in row["message"] for row in plan["errors"]))

    def test_matching_product_with_a_different_head_suffix_is_reused(self):
        doc = source(rvm_check=1, product_variants=[dict(selected=1, body="521000", syringe="", product_code="420XYZ")])
        data = catalogue()
        materialize(plans.build_plan(doc, catalogue=data), data)
        plan = plans.build_plan(doc, catalogue=MemoryCatalogue(data.tables))
        self.assertTrue(plan["ready"], plan["errors"])
        self.assertEqual(plan["actions"][-1]["item_action"], "reuse")
        self.assertEqual(plan["actions"][-1]["bom_action"], "reuse")

    def test_approved_u_syringes_generate_the_correct_product_for_each_lv_body(self):
        for body, motor in (("551000", "5"), ("571000", "7"), ("591000", "9"), ("5B1000", "B")):
            for syringe, reference in (("704000", "S-100-U"), ("709000", "S-500-U")):
                with self.subTest(body=body, syringe=syringe):
                    plan = plans.build_plan(source(pump_check=1, product_variants=[
                        dict(selected=1, body=body, syringe=syringe)]), catalogue=catalogue())
                    self.assertEqual(plan["errors"], [])
                    product = plan["actions"][-1]
                    self.assertEqual(product["item"]["item_code"], "4" + motor + syringe[2] + "ABC")
                    self.assertTrue(product["item"]["reference_code"].endswith(reference.replace("-", "")))
                    self.assertIn(syringe, [row["item_code"] for row in product["materials"]])

    def test_u_syringes_still_require_enabled_items_and_the_correct_u_reference(self):
        for syringe in ("704000", "709000"):
            for change in ({"disabled": 1}, {"reference_code": "S-500-P"}):
                with self.subTest(syringe=syringe, change=change):
                    data = catalogue()
                    next(row for row in data.tables["Item"] if row["name"] == syringe).update(change)
                    plan = plans.build_plan(source(pump_check=1, product_variants=[
                        dict(selected=1, body="551000", syringe=syringe)]), catalogue=data)
                    self.assertFalse(plan["ready"])

    def test_u_syringes_are_not_added_to_hv_bodies(self):
        for syringe in ("704000", "709000"):
            plan = plans.build_plan(source(head_name="VALVE HEAD-D-1-6-050-C-P-HV", pump_hv_check=1,
                product_variants=[dict(selected=1, body="561000", syringe=syringe)]), catalogue=catalogue())
            self.assertTrue(any("Unsupported" in row["message"] for row in plan["errors"]))

    def test_configuration_chooser_includes_all_eight_approved_u_pairs(self):
        doc = source(pump_check=1)
        with patch.object(workflow, "_source_for_preview", return_value=doc), \
                patch.object(frappe, "get_all", return_value=[frappe._dict(row) for row in catalogue().tables["Item"]]):
            rows = workflow.get_compatible_variants({})
        pairs = {(row["body"], row["syringe"]) for row in rows if row["syringe"] in ("704000", "709000")}
        self.assertEqual(pairs, {(body, syringe) for body in ("551000", "571000", "591000", "5B1000")
                                for syringe in ("704000", "709000")})

    def test_hv_chooser_shows_all_hv_and_hd_choices_with_head_requirements(self):
        for head_name, needs_geometry in (("VALVE HEAD-D-1-6-050-C-P", True),
                                          ("VALVE HEAD-DS-1-6-050-C-P-HV", False)):
            doc = source(head_name=head_name, pump_hv_check=1)
            with patch.object(workflow, "_source_for_preview", return_value=doc), \
                    patch.object(frappe, "get_all", return_value=[frappe._dict(row) for row in catalogue().tables["Item"]]):
                rows = workflow.get_compatible_variants({})
            self.assertEqual({(row["body"], row["syringe"]) for row in rows},
                {(body, syringe) for body in ("561000", "581000", "5A1000", "5C1000")
                 for syringe in ("70E000", "70F000")})
            self.assertTrue(all(bool(row["compatibility_note"]) == needs_geometry for row in rows))
            for row in rows:
                reference = "S-2500-P" if row["syringe"] == "70E000" else "S-5000-P"
                self.assertIn(reference, row["configuration"])
                self.assertEqual("HV / HD" in row["configuration"], row["body"] in ("5A1000", "5C1000"))

    def test_all_hv_and_hd_products_use_the_selected_large_syringe(self):
        for body, motor in (("561000", "6"), ("581000", "8"), ("5A1000", "A"), ("5C1000", "C")):
            for syringe in ("70E000", "70F000"):
                with self.subTest(body=body, syringe=syringe):
                    plan = plans.build_plan(source(head_name="VALVE HEAD-D-1-6-050-C-P-HV", pump_hv_check=1,
                        product_variants=[dict(selected=1, body=body, syringe=syringe)]), catalogue=catalogue())
                    self.assertTrue(plan["ready"], plan["errors"])
                    product = plan["actions"][-1]
                    self.assertEqual(product["item"]["item_code"], "4" + motor + syringe[2] + "ABC")
                    self.assertIn(syringe, [row["item_code"] for row in product["materials"]])
                    self.assertTrue(product["item"]["reference_code"].endswith(
                        "S2500P" if syringe == "70E000" else "S5000P"))

    def test_hd_low_volume_choices_are_labelled_explicitly(self):
        for body in ("591000", "5B1000"):
            rule = compatibility.BY_KEY[body + ":709000"]
            self.assertIn("LV / HD", compatibility.configuration_label(rule, "S-500-U"))

    def test_compatibility_rule_change_invalidates_a_previous_draft_approval(self):
        doc = source(review_status="Reviewed", plug_code="100ABC", seat_code="200ABC")
        with patch.object(compatibility, "RULE_VERSION", "2026-10-27.1"):
            old = plans.build_plan(doc, catalogue=catalogue())
        doc.approved_plan_hash, doc.approved_input_hash = old["fingerprint"], old["input_hash"]
        current = plans.build_plan(doc, catalogue=catalogue())
        with patch.object(workflow, "_lock_source"), patch.object(workflow, "build_plan", return_value=current):
            with self.assertRaisesRegex(frappe.ValidationError, "stale"):
                workflow.validate_submission(doc)

    def test_hv_requires_hv_head_and_standard_products_reject_hv_heads(self):
        for changes in (dict(pump_hv_check=1, product_variants=[dict(selected=1, body="561000", syringe="70E000")]),
                        dict(head_name="VALVE HEAD-D-1-6-050-C-P-HV", rvm_check=1,
                             product_variants=[dict(selected=1, body="521000", syringe="")])):
            self.assertFalse(plans.build_plan(source(**changes), catalogue=catalogue())["ready"])
        doc = source(head_name="VALVE HEAD-D-1-6-050-C-P-HV", pump_hv_check=1,
                     product_variants=[dict(selected=1, body="561000", syringe="70E000")])
        plan = plans.build_plan(doc, catalogue=catalogue())
        self.assertEqual(plan["errors"], [])
        self.assertIn("46EABC", [row["item"]["item_code"] for row in plan["actions"]])

    def test_variants_are_unique_and_respect_family_flags(self):
        variant = dict(selected=1, body="521000", syringe="")
        for rows, flag in (([variant, variant], 1), ([variant], 0)):
            self.assertFalse(plans.build_plan(source(rvm_check=flag, product_variants=rows), catalogue=catalogue())["ready"])

    def test_non_distribution_head_needs_a_new_pump_compatibility_rule(self):
        doc = source(head_name="VALVE HEAD-T-1-3-050-C-P", pump_check=1,
                     product_variants=[dict(selected=1, body="551000", syringe="708000")])
        plan = plans.build_plan(doc, catalogue=catalogue())
        self.assertTrue(any("no standard LV" in row["message"] for row in plan["errors"]))

    def test_hv_customer_suffix_is_recognized(self):
        self.assertEqual(compatibility.allowed_families("VALVE HEAD-DS-1-12-050-C-P-HV MGA"), {"HV"})

    def test_preview_uses_the_item_manufacturing_flag(self):
        data = catalogue()
        for row in data.tables["Item"]:
            if row["name"] == "708000":
                row["include_item_in_manufacturing"] = 0
        plan = plans.build_plan(source(pump_check=1,
            product_variants=[dict(selected=1, body="571000", syringe="708000")]), catalogue=data)
        self.assertTrue(plan["ready"])
        syringe = next(row for row in plan["actions"][-1]["materials"] if row["item_code"] == "708000")
        self.assertEqual(syringe["include_item_in_manufacturing"], 0)

    def test_zero_accessory_count_is_explicit_and_negative_count_is_invalid(self):
        plan = plans.build_plan(source(seat_acc=0), catalogue=catalogue())
        self.assertTrue(plan["ready"])
        self.assertEqual([row["item_code"] for row in plan["actions"][3]["materials"]], ["200ABC"])
        self.assertFalse(plans.build_plan(source(seat_acc=-1), catalogue=catalogue())["ready"])

    def test_selected_pin_item_and_quantity_are_used_and_reviewed(self):
        data = catalogue()
        data.tables["Item"].append(item("ALTERNATE-PIN", "Fasteners"))
        default_plan = plans.build_plan(source(), catalogue=data)
        plan = plans.build_plan(source(seat_pin_item="ALTERNATE-PIN", seat_acc=3), catalogue=MemoryCatalogue(data.tables))
        self.assertTrue(plan["ready"], plan["errors"])
        pins = [row for row in plan["actions"][3]["materials"] if row["item_code"] != "200ABC"]
        self.assertEqual([(row["item_code"], row["qty"]) for row in pins], [("ALTERNATE-PIN", 3)])
        self.assertNotEqual(default_plan["fingerprint"], plan["fingerprint"])
        self.assertNotEqual(default_plan["input_hash"], plan["input_hash"])

    def test_positive_pin_quantity_requires_an_enabled_item_but_zero_needs_none(self):
        self.assertFalse(plans.build_plan(source(seat_pin_item=""), catalogue=catalogue())["ready"])
        data = catalogue()
        next(row for row in data.tables["Item"] if row["name"] == "SPL.3039")["disabled"] = 1
        self.assertFalse(plans.build_plan(source(), catalogue=data)["ready"])
        plan = plans.build_plan(source(seat_acc=0, seat_pin_item=""), catalogue=catalogue())
        self.assertTrue(plan["ready"], plan["errors"])

    def test_existing_matching_items_and_boms_are_reused(self):
        data = catalogue()
        materialize(plans.build_plan(source(), catalogue=data), data)
        plan = plans.build_plan(source(), catalogue=MemoryCatalogue(data.tables))
        self.assertEqual(plan["errors"], [])
        self.assertTrue(all(row["item_action"] == "reuse" and row["bom_action"] == "reuse" for row in plan["actions"]))

    def test_bom_conflicts_show_exact_diff_and_require_explicit_review_mode(self):
        data = catalogue()
        materialize(plans.build_plan(source(), catalogue=data), data)
        data.tables["BOM Item"][0]["qty"] = 0.04
        plan = plans.build_plan(source(), catalogue=MemoryCatalogue(data.tables))
        self.assertFalse(plan["ready"])
        replacement = plan["actions"][0]
        self.assertEqual(replacement["bom_action"], "replace")
        self.assertEqual(replacement["diff"]["materials"]["before"][0]["qty"], 0.04)
        self.assertEqual(replacement["diff"]["materials"]["after"][0]["qty"], 0.02)
        reviewed = plans.build_plan(source(replace_boms=1), catalogue=MemoryCatalogue(data.tables))
        self.assertEqual(reviewed["errors"], [])
        self.assertTrue(reviewed["affected_parents"])

    def test_approval_hash_changes_when_recipe_or_dependency_changes(self):
        data = catalogue()
        first = plans.build_plan(source(), catalogue=data)
        second = plans.build_plan(source(), catalogue=catalogue())
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        changed = catalogue()
        changed.tables["Item"][0]["modified"] = "2026-10-27 13:00:00"
        self.assertNotEqual(first["fingerprint"], plans.build_plan(source(), catalogue=changed)["fingerprint"])
        self.assertNotEqual(first["fingerprint"], plans.build_plan(source(plug_raw_qty=0.025), catalogue=catalogue())["fingerprint"])

    def test_stock_candidate_changes_do_not_change_an_approved_recipe(self):
        data = catalogue()
        first = plans.build_plan(source(), catalogue=data)
        data.tables["Item"].append(item("OTHER-ROD", "Raw Material", tag_raw_mat="PTFE"))
        second = plans.build_plan(source(), catalogue=MemoryCatalogue(data.tables))
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_largest_standard_selection_uses_bulk_reads_and_preloaded_syringes(self):
        variants = [dict(selected=1, body=row["body"], syringe=row["syringe"])
                    for row in compatibility.CONFIGURATIONS if row["family"] != "HV"]
        data = catalogue()
        plan = plans.build_plan(source(rvm_check=1, pump_check=1, product_variants=variants), catalogue=data)
        self.assertEqual(plan["errors"], [])
        self.assertEqual(len(plan["actions"]), 45)
        self.assertEqual(self.db.get_value.call_count, 1)  # Warehouse, never repeated syringe lookups.
        self.assertEqual(sum(row[0] == "Item" for row in data.reads), 2)
        self.assertEqual(data.variant_reads, 1)

    def test_input_hash_ignores_review_fields_and_numeric_serialization(self):
        doc = source()
        original = plans.input_hash(doc)
        doc.reviewed_by = "Reviewer"
        doc.head_description_check = 1
        doc.plug_raw_qty = "0.020000000"
        self.assertEqual(original, plans.input_hash(doc))
        doc.plug_raw_qty = 0.03
        self.assertNotEqual(original, plans.input_hash(doc))

    def test_amendment_plan_approval_includes_predecessor_and_reason(self):
        doc = source(amended_from="CANCELLED-REQUEST", amendment_reason="Approved screw change",
                     plug_code="100ABC", seat_code="200ABC")
        plan = plans.build_plan(doc, catalogue=catalogue())
        self.assertEqual(plan["inputs"]["amended_from"], doc.amended_from)
        self.assertEqual(plan["inputs"]["amendment_reason"], doc.amendment_reason)
        self.assertEqual(plan["input_hash"], plans.input_hash(doc))

    def test_historical_submitted_requests_do_not_invent_a_reviewed_plan(self):
        historical = source(docstatus=1, review_history=[])
        with patch.object(workflow, "_source_for_preview", return_value=historical), \
                patch.object(workflow, "build_plan") as build:
            plan = workflow.get_creation_plan({"name": "OLD-REQUEST"})
        self.assertFalse(plan["ready"])
        self.assertIn("Historical request", plan["warnings"][0])
        build.assert_not_called()

    def test_submit_without_review_or_with_stale_dependency_cannot_execute(self):
        doc = source()
        with patch.object(workflow, "_lock_source"):
            with self.assertRaisesRegex(frappe.ValidationError, "engineering review"):
                workflow.validate_submission(doc)
        doc.update(dict(review_status="Reviewed", approved_plan_hash="OLD", approved_input_hash="OLD"))
        with patch.object(workflow, "_lock_source"), patch.object(workflow, "build_plan", return_value={
                "errors": [], "fingerprint": "NEW", "input_hash": "NEW"}):
            with self.assertRaisesRegex(frappe.ValidationError, "stale"):
                workflow.validate_submission(doc)

    def test_approval_history_and_results_cannot_be_forged(self):
        doc = source(review_status="Reviewed", approved_plan_hash="FORGED")
        doc.get_doc_before_save = lambda: None
        with self.assertRaisesRegex(frappe.ValidationError, "server actions"):
            workflow.protect_review_fields(doc)

    def test_review_rows_and_reviewed_requests_cannot_be_deleted_or_edited_directly(self):
        from amf.amf.doctype.item_creation_review.item_creation_review import ItemCreationReview
        from amf.amf.doctype.item_creation.item_creation import ItemCreation
        for operation in (lambda: ItemCreationReview.validate(None), lambda: ItemCreationReview.on_trash(None),
                          lambda: ItemCreation.on_trash(source(review_history=[{}]))):
            with self.assertRaises(frappe.ValidationError):
                operation()

    def test_editing_a_reviewed_input_invalidates_approval_but_retains_history(self):
        previous = source(review_status="Reviewed", approved_plan_hash="PLAN", reviewed_by="Reviewer",
                          approved_input_hash=plans.input_hash(source()), review_history=[])
        doc = copy.deepcopy(previous)
        doc.plug_raw_qty = 0.04
        doc.get_doc_before_save = lambda: previous
        workflow.protect_review_fields(doc)
        self.assertEqual(doc.review_status, "Stale")
        self.assertIsNone(doc.approved_plan_hash)

    def test_executor_preserves_product_defaults_without_nested_commits(self):
        class NewItem(frappe._dict):
            def insert(self, **kwargs):
                self.name = self.item_code
                return self
        action = dict(item=dict(item_code="420ABC", item_name="Reviewed Product", item_group="Product",
                      reference_code="P201O300ABC", stock_uom="Nos", has_batch_no=0),
                      item_action="create", bom_action="create", existing_bom="")
        plan = dict(fingerprint="HASH", actions=[action])
        doc = source(approved_plan_hash="HASH", reviewed_by="Reviewer", reviewed_at="2026-10-27 12:00:00")
        doc.flags = frappe._dict(amf_reviewed_creation_plan=plan)
        doc.add_comment = Mock()
        created = []
        def get_doc(data):
            result = NewItem(data)
            created.append(result)
            return result
        self.db.set_value = Mock()
        self.db.commit, self.db.rollback = Mock(), Mock()
        with patch.object(frappe, "get_doc", side_effect=get_doc), \
                patch.object(workflow, "_new_bom", return_value="BOM-NEW"), \
                patch.object(traceability, "store_results") as store, \
                patch.object(workflow, "now_datetime", return_value="2026-10-27 12:01:00"):
            result = workflow.execute_reviewed_plan(doc)
        store.assert_called_once_with(doc, result)
        self.assertEqual(created[0].has_batch_no, 0)
        self.assertEqual(result["records"][0]["bom"], "BOM-NEW")
        self.assertEqual(doc.review_status, "Created")
        self.db.commit.assert_not_called()
        self.db.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
