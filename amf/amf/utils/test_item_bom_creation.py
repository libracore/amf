# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from amf.amf.utils import item_bom_creation


class FakeDB(object):
	def __init__(self, existing=None, tags=None):
		self.existing = set(existing or [])
		self.tags = tags or {}

	def exists(self, doctype, name):
		return doctype == "Item" and name in self.existing

	def get_value(self, doctype, name, fieldname, **kwargs):
		if doctype == "Item" and fieldname == "tag_raw_mat":
			return self.tags.get(name)
		return None


class FakeItem(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)

	def set(self, key, value):
		setattr(self, key, value)

	def check_permission(self, permission_type):
		self.checked_permission = permission_type


class TestItemBomCreation(unittest.TestCase):
	def test_component_and_sub_assembly_codes_share_component(self):
		with patch.object(item_bom_creation.frappe, "db", FakeDB()):
			component = item_bom_creation._get_creation_context(
				"100042", "Plug", "PTFE"
			)
			assembly = item_bom_creation._get_creation_context(
				"110042", "Plug", "PTFE"
			)

		self.assertEqual(component["layer"], "component")
		self.assertEqual(assembly["layer"], "sub_assembly")
		self.assertEqual(component["component_item_code"], "100042")
		self.assertEqual(assembly["component_item_code"], "100042")

	def test_valve_seat_layers_use_20_and_21(self):
		with patch.object(item_bom_creation.frappe, "db", FakeDB()):
			component = item_bom_creation._get_creation_context(
				"200042", "Valve Seat", "PEEK"
			)
			assembly = item_bom_creation._get_creation_context(
				"210042", "Valve Seat", "PEEK"
			)

		self.assertEqual(component["layer"], "component")
		self.assertEqual(assembly["layer"], "sub_assembly")
		self.assertEqual(assembly["component_item_code"], "200042")

	def test_existing_component_tag_is_authoritative(self):
		fake_db = FakeDB(existing=["100042"], tags={"100042": "PTFE"})
		with patch.object(item_bom_creation.frappe, "db", fake_db):
			context = item_bom_creation._get_creation_context(
				"110042", "Plug", ""
			)

		self.assertTrue(context["component_item_exists"])
		self.assertEqual(context["tag_raw_mat"], "PTFE")

	def test_raw_material_quantities_match_amf_rules(self):
		self.assertEqual(
			item_bom_creation.ITEM_GROUP_RULES["Plug"]["raw_material_qty"],
			0.02,
		)
		self.assertEqual(
			item_bom_creation.ITEM_GROUP_RULES["Valve Seat"]["raw_material_qty"],
			0.03,
		)

	def test_accessory_quantities(self):
		self.assertEqual(
			item_bom_creation._normalize_accessory_qty(
				"Plug", "PLUG-D-1-8-100-U"
			),
			8,
		)
		self.assertEqual(
			item_bom_creation._normalize_accessory_qty(
				"Valve Seat", "SEAT-D-1-8-100-C"
			),
			2,
		)

	def test_component_reference_removes_assembly_suffix(self):
		self.assertEqual(
			item_bom_creation._get_component_reference_code("RVM.1234-P.ASM"),
			"RVM.1234-P",
		)
		self.assertEqual(
			item_bom_creation._get_component_reference_code("RVM.1234-P"),
			"RVM.1234-P",
		)

	def test_component_copy_clears_upper_bom_and_qr_fields(self):
		class FakeMeta(object):
			def has_field(self, fieldname):
				return fieldname in {
					"item_default_bom", "bom_cost", "qrcode", "bom_table", "drawing_item"
				}

		upper = FakeItem(
			item_code="110042",
			item_name="PLUG-D-1-8-100-U",
			reference_code="RVM.1234-U.ASM",
			description="110042 / RVM.1234-U.ASM",
		)
		drawing = FakeItem(item_code="110042", item_name=upper.item_name, reference_code=upper.reference_code)
		component = FakeItem(
			name=None,
			item_code=upper.item_code,
			item_name=upper.item_name,
			item_group="Plug",
			item_type="Sub-Assembly",
			reference_code=upper.reference_code,
			reference_name="110042: " + upper.item_name,
			default_bom="BOM-110042-001",
			item_default_bom="BOM-110042-001",
			bom_cost=12,
			qrcode="/private/files/110042_qr.png",
			bom_table=[{"item_code": "100042"}],
			drawing_item=[drawing],
			meta=FakeMeta(),
		)

		def insert(ignore_permissions=False):
			component.name = component.item_code

		component.insert = insert
		context = {"component_item_code": "100042"}
		fake_db = FakeDB()
		with patch.object(item_bom_creation.frappe, "db", fake_db), \
			patch.object(item_bom_creation.frappe, "copy_doc", return_value=component):
			created, was_created = item_bom_creation._ensure_component_item(upper, context)

		self.assertTrue(was_created)
		self.assertEqual(created.name, "100042")
		self.assertEqual(created.item_type, "Component")
		self.assertEqual(created.reference_code, "RVM.1234-U")
		self.assertEqual(created.reference_name, "100042: " + upper.item_name)
		self.assertIsNone(created.default_bom)
		self.assertIsNone(created.item_default_bom)
		self.assertIsNone(created.bom_cost)
		self.assertIsNone(created.qrcode)
		self.assertEqual(created.bom_table, [])
		self.assertEqual(drawing.item_code, "100042")
		self.assertEqual(drawing.reference_code, "RVM.1234-U")

	def test_existing_active_bom_is_reused(self):
		item = FakeItem(name="100042")
		with patch.object(
			item_bom_creation, "_get_existing_bom", return_value="BOM-100042-001"
		), patch.object(item_bom_creation.frappe, "get_doc") as get_doc:
			bom_name, created = item_bom_creation._ensure_bom(
				item, [{"item_code": "MAT.1001", "qty": 0.02}]
			)

		self.assertEqual(bom_name, "BOM-100042-001")
		self.assertFalse(created)
		get_doc.assert_not_called()

	def test_plan_does_not_guess_when_tag_has_multiple_raw_materials(self):
		context = {
			"item_code": "100042",
			"item_group": "Plug",
			"layer": "component",
			"component_item_code": "100042",
			"component_item_exists": False,
			"tag_raw_mat": "PTFE",
			"rule": item_bom_creation.ITEM_GROUP_RULES["Plug"],
		}
		candidates = [
			{"name": "MAT.1001", "item_name": "PTFE A"},
			{"name": "MAT.1007", "item_name": "PTFE B"},
		]
		with patch.object(item_bom_creation, "_get_creation_context", return_value=context), \
			patch.object(item_bom_creation, "get_raw_material_candidates", return_value=candidates), \
			patch.object(item_bom_creation, "_get_existing_bom", return_value=""):
			plan = item_bom_creation.get_bom_creation_plan(
				"100042", "Plug", "PTFE"
			)

		self.assertEqual(plan["raw_material"], "")
		self.assertEqual(plan["raw_material_candidates"], candidates)

	def test_sub_assembly_plan_opens_when_accessory_qty_cannot_be_derived(self):
		context = {
			"item_code": "110042",
			"item_group": "Plug",
			"layer": "sub_assembly",
			"component_item_code": "100042",
			"component_item_exists": False,
			"tag_raw_mat": "PTFE",
			"rule": item_bom_creation.ITEM_GROUP_RULES["Plug"],
		}
		candidates = [{"name": "MAT.1001", "item_name": "PTFE A"}]
		with patch.object(item_bom_creation, "_get_creation_context", return_value=context), \
			patch.object(item_bom_creation, "get_raw_material_candidates", return_value=candidates), \
			patch.object(item_bom_creation, "_get_existing_bom", return_value=""), \
			patch.object(item_bom_creation, "_validate_accessory_item"):
			plan = item_bom_creation.get_bom_creation_plan(
				"110042",
				"Plug",
				"PTFE",
				item_name="PLUG-A-X-XX-XXX-B",
			)

		self.assertEqual(plan["accessory_item"], "SPL.3013")
		self.assertEqual(plan["accessory_qty"], 0)

	def test_sub_assembly_plan_reuses_existing_component_bom_without_raw_material(self):
		context = {
			"item_code": "210082",
			"item_group": "Valve Seat",
			"layer": "sub_assembly",
			"component_item_code": "200082",
			"component_item_exists": True,
			"tag_raw_mat": "PEEK",
			"rule": item_bom_creation.ITEM_GROUP_RULES["Valve Seat"],
		}

		def existing_bom(item_code):
			return "BOM-200082-001" if item_code == "200082" else ""

		with patch.object(item_bom_creation, "_get_creation_context", return_value=context), \
			patch.object(item_bom_creation, "get_raw_material_candidates") as get_candidates, \
			patch.object(item_bom_creation, "_get_existing_bom", side_effect=existing_bom), \
			patch.object(item_bom_creation, "_validate_accessory_item"):
			plan = item_bom_creation.get_bom_creation_plan(
				"210082",
				"Valve Seat",
				"PEEK",
				item_name="SEAT-D-1-8-100-C",
			)

		get_candidates.assert_not_called()
		self.assertFalse(plan["needs_raw_material"])
		self.assertEqual(plan["component_bom"], "BOM-200082-001")
		self.assertEqual(plan["raw_material"], "")
		self.assertEqual(plan["raw_material_candidates"], [])

	def test_sub_assembly_creates_component_bom_before_upper_bom(self):
		upper = FakeItem(name="110042", item_name="PLUG-D-1-8-100-U")
		component = FakeItem(name="100042")
		context = {
			"item_group": "Plug",
			"tag_raw_mat": "PTFE",
			"rule": item_bom_creation.ITEM_GROUP_RULES["Plug"],
		}

		with patch.object(item_bom_creation, "_validate_accessory_item"), \
			patch.object(item_bom_creation, "_ensure_component_item", return_value=(component, True)), \
			patch.object(item_bom_creation, "_validate_component_item"), \
			patch.object(item_bom_creation, "_get_existing_bom", return_value=""), \
			patch.object(item_bom_creation, "_validate_raw_material"), \
			patch.object(
				item_bom_creation,
				"_ensure_bom",
				side_effect=[("BOM-100042-001", True), ("BOM-110042-001", True)],
			) as ensure_bom:
			result = item_bom_creation._create_sub_assembly_chain(
				upper, context, "MAT.1003"
			)

		self.assertEqual(
			ensure_bom.call_args_list,
			[
				call(component, [{"item_code": "MAT.1003", "qty": 0.02}]),
				call(
					upper,
					[
						{
							"item_code": "100042",
							"qty": 1,
							"bom_no": "BOM-100042-001",
						},
						{"item_code": "SPL.3013", "qty": 8.0},
					],
				),
			],
		)
		self.assertEqual(result["upper_bom"], "BOM-110042-001")

	def test_sub_assembly_reuses_existing_component_bom_without_raw_material(self):
		upper = FakeItem(name="210082", item_name="SEAT-D-1-8-100-C")
		component = FakeItem(name="200082")
		context = {
			"item_group": "Valve Seat",
			"tag_raw_mat": "PEEK",
			"rule": item_bom_creation.ITEM_GROUP_RULES["Valve Seat"],
		}

		with patch.object(item_bom_creation, "_validate_accessory_item"), \
			patch.object(item_bom_creation, "_ensure_component_item", return_value=(component, False)), \
			patch.object(item_bom_creation, "_validate_component_item"), \
			patch.object(item_bom_creation, "_get_existing_bom", return_value="BOM-200082-001"), \
			patch.object(item_bom_creation, "_validate_raw_material") as validate_raw_material, \
			patch.object(
				item_bom_creation,
				"_ensure_bom",
				return_value=("BOM-210082-001", True),
			) as ensure_bom:
			result = item_bom_creation._create_sub_assembly_chain(
				upper,
				context,
				raw_material="",
			)

		validate_raw_material.assert_not_called()
		ensure_bom.assert_called_once_with(
			upper,
			[
				{
					"item_code": "200082",
					"qty": 1,
					"bom_no": "BOM-200082-001",
				},
				{"item_code": "SPL.3039", "qty": 2.0},
			],
		)
		self.assertEqual(result["component_bom"], "BOM-200082-001")
		self.assertFalse(result["component_bom_created"])
		self.assertEqual(result["upper_bom"], "BOM-210082-001")

	def test_component_creation_only_creates_base_bom(self):
		item = FakeItem(
			name="200042",
			item_code="200042",
			item_group="Valve Seat",
			tag_raw_mat="PEEK",
		)
		context = {
			"layer": "component",
			"rule": item_bom_creation.ITEM_GROUP_RULES["Valve Seat"],
			"tag_raw_mat": "PEEK",
		}
		fake_db = Mock()
		fake_db.exists.return_value = True

		with patch.object(item_bom_creation.frappe, "db", fake_db), \
			patch.object(item_bom_creation.frappe, "get_doc", return_value=item), \
			patch.object(item_bom_creation, "_lock_item"), \
			patch.object(item_bom_creation, "_get_creation_context", return_value=context), \
			patch.object(item_bom_creation, "_validate_raw_material"), \
			patch.object(item_bom_creation, "_get_existing_bom", return_value=""), \
			patch.object(item_bom_creation, "_ensure_bom", return_value=("BOM-200042-001", True)) as ensure_bom, \
			patch.object(item_bom_creation, "_create_sub_assembly_chain") as create_upper:
			result = item_bom_creation.create_item_boms_after_save(
				"200042", "MAT.1009"
			)

		ensure_bom.assert_called_once_with(
			item,
			[{"item_code": "MAT.1009", "qty": 0.03}],
		)
		create_upper.assert_not_called()
		self.assertEqual(result["component_bom"], "BOM-200042-001")


if __name__ == "__main__":
	unittest.main()
