# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from amf.amf.utils import item_learned_defaults


def peer(
	item_code,
	item_type,
	weight_per_unit,
	weight_uom,
	customs_tariff_number,
	has_batch_no,
):
	return SimpleNamespace(
		item_code=item_code,
		item_type=item_type,
		weight_per_unit=weight_per_unit,
		weight_uom=weight_uom,
		customs_tariff_number=customs_tariff_number,
		has_batch_no=has_batch_no,
	)


class TestItemLearnedDefaults(unittest.TestCase):
	def test_plug_component_description_uses_item_name_fields(self):
		description = item_learned_defaults.build_item_description(
			item_code="100042",
			item_name="PLUG-OS-2-4-050-P",
			item_group="Plug",
			item_type="Component",
			reference_code="RVM.1234-P",
		)

		self.assertIn("<b>Item Code:</b> 100042<br>", description)
		self.assertIn("<b>Valve Type:</b> On/Off-Switch<br>", description)
		self.assertIn("<b>Number of Stages:</b> 2<br>", description)
		self.assertIn("<b>Number of Ports:</b> 4<br>", description)
		self.assertIn("<b>Channel Size:</b> 0.50 mm<br>", description)
		self.assertIn("<b>Plug Material:</b> PTFE<br>", description)
		self.assertNotIn("SUB-ASSEMBLY", description)

	def test_valve_seat_sub_assembly_description_marks_upper_layer(self):
		description = item_learned_defaults.build_item_description(
			item_code="210042",
			item_name="SEAT-D-1-8-100-C",
			item_group="Valve Seat",
			item_type="Sub-Assembly",
			reference_code="RVM.1234-C.ASM",
		)

		self.assertIn("SUB-ASSEMBLY", description)
		self.assertIn("<b>R&amp;D Code:</b> RVM.1234-C.ASM<br>", description)
		self.assertIn("<b>Valve Material:</b> PCTFE<br>", description)

	def test_valve_head_description_uses_both_materials(self):
		description = item_learned_defaults.build_item_description(
			item_code="300042",
			item_name="VALVE HEAD-D-2-20-050-K-P",
			item_group="Valve Head",
			item_type="Sub-Assembly",
			reference_code="V-D-2-20-050-K-P",
		)

		self.assertIn("<b>Valve Head:</b> VALVE HEAD-D-2-20-050-K-P<br>", description)
		self.assertIn("<b>Valve Material:</b> PEEK<br>", description)
		self.assertIn("<b>Plug Material:</b> PTFE<br>", description)

	def test_product_description_uses_generic_product_pattern(self):
		description = item_learned_defaults.build_item_description(
			item_code="410042",
			item_name="P200-O/V-D-1-6-050-C-P",
			item_group="Product",
			item_type="Finished Good",
			reference_code="P200O300042",
		)

		self.assertIn("<b>Item Code:</b> 410042<br>", description)
		self.assertIn("<b>Reference:</b> P200O300042<br>", description)
		self.assertIn("<b>Item Group:</b> Product<br>", description)

	def test_product_numeric_defaults_are_learned_from_same_prefix(self):
		rows = [
			peer("410001", "Finished Good", 0.33, "Kg", "8479.5000", 0),
			peer("410002", "Finished Good", 0.33, "Kg", "8479.5000", 0),
			peer("450001", "Finished Good", 1.31, "Kg", "8413.5000", 0),
			peer("450002", "Finished Good", 1.31, "Kg", "8413.5000", 0),
		]
		with patch.object(item_learned_defaults.frappe, "get_all", return_value=rows):
			defaults = item_learned_defaults.get_new_item_learned_defaults(
				"410099",
				"RVM Product",
				"Product",
				"Finished Good",
				"RVM.9999",
			)

		self.assertEqual(defaults["weight_per_unit"], 0.33)
		self.assertEqual(defaults["weight_uom"], "Kg")
		self.assertEqual(defaults["customs_tariff_number"], "8479.5000")
		self.assertEqual(defaults["has_batch_no"], 0)

	def test_manufactured_group_defaults_force_batch_tracking(self):
		rows = [
			peer("100001", "Component", 0.1, "Kg", "8487.9000", 1),
			peer("100002", "Component", 0.1, "Kg", "8487.9000", 1),
		]
		with patch.object(item_learned_defaults.frappe, "get_all", return_value=rows):
			defaults = item_learned_defaults.get_new_item_learned_defaults(
				"100099",
				"PLUG-D-1-8-100-P",
				"Plug",
				"Component",
				"RVM.9999-P",
			)

		self.assertEqual(defaults["weight_per_unit"], 0.1)
		self.assertEqual(defaults["weight_uom"], "Kg")
		self.assertEqual(defaults["customs_tariff_number"], "8487.9000")
		self.assertEqual(defaults["has_batch_no"], 1)

if __name__ == "__main__":
	unittest.main()
