from __future__ import unicode_literals

import unittest

from amf.amf.utils.purchased_item_description_update_2026 import (
	CLIENT_START,
	FACTS_END,
	FACTS_START,
	INTERNAL_START,
	PRESERVED_END,
	PRESERVED_START,
	RESEARCHED_ITEMS,
	choose_catalog_facts,
	classify_part_item,
	client_description,
	customs_description,
	div,
	meaningful_lines,
	original_internal_note,
	plain,
)


class TestPurchasedItemDescriptionUpdate2026(unittest.TestCase):
	def item(self, **values):
		item = {
			"name": "TEST.001",
			"item_code": "TEST.001",
			"item_name": "Syringe glass - 50 uL",
			"item_group": "Glass",
			"internal_description": "",
			"description": "",
		}
		item.update(values)
		return item

	def test_client_uses_item_code_and_required_wording(self):
		item = self.item(item_name="Shipping Foam RVMmini")
		value = client_description(item, "Packaging foam for transport protection.")
		self.assertIn(div("Item reference", "TEST.001"), value)
		self.assertIn("<div><br></div>" + div("Item reference", "TEST.001"), value)
		self.assertIn("RVM mini", plain(value))
		self.assertNotIn("non-medical", plain(value).lower())

	def test_generated_facts_are_stable_on_rerun(self):
		item = self.item()
		item["description"] = "{}{}<div>Reviewed fact.</div>{}".format(
			CLIENT_START, FACTS_START, FACTS_END
		)
		facts, basis = choose_catalog_facts(item, [], [])
		self.assertEqual("Reviewed fact", facts)
		self.assertEqual("previous-generated", basis)

	def test_existing_internal_note_is_preserved(self):
		note = "<div>Solder this component only for the RS-485 option.</div>"
		generated = "{}{}{}{}".format(INTERNAL_START, PRESERVED_START, note, PRESERVED_END)
		self.assertEqual(note, original_internal_note(generated))

	def test_catalog_boilerplate_and_urls_are_filtered(self):
		item = self.item(item_name="Rubber foot")
		lines = meaningful_lines(
			"<div>Informations environnementales</div>"
			"<div>Réglementation REACH Pas de SVHC</div>"
			"<div>Rubber foot 12.7 x 3.5 mm https://example.invalid/catalog</div>",
			item,
		)
		self.assertEqual(["Rubber foot 12.7 x 3.5 mm"], lines)

	def test_customs_group_precedence(self):
		syringe = self.item(item_group="Syringe", item_name="Syringe 500-P uL")
		value = customs_description(syringe, "Glass barrel with PTFE plunger")
		self.assertTrue(value.startswith("Precision glass syringe"))
		board = self.item(item_group="Electronic Board", item_name="PCB with RS485 transceiver")
		self.assertTrue(customs_description(board, "32-pin transceiver").startswith("Printed electronic circuit board"))

	def test_exact_researched_electronic_customs_description(self):
		item = self.item(
			name="RVM.3020",
			item_code="RVM.3020",
			item_name="RS485/422/232 Component",
			item_group="Part",
		)
		value = customs_description(item, RESEARCHED_ITEMS["RVM.3020"]["facts"])
		self.assertTrue(value.startswith("Electronic integrated circuit"))
		self.assertLessEqual(len(value), 512)

	def test_part_child_group_classification_priorities(self):
		base = self.item(item_group="Part")
		self.assertEqual("Springs", classify_part_item(
			dict(base, item_name="Spring washer M3"), "", []
		))
		self.assertEqual("Seals and Elastomers", classify_part_item(
			dict(base, item_name="Washer NBR 70ShA"), "", []
		))
		self.assertEqual("Fluidic Components", classify_part_item(
			dict(base, item_name="PEEK fitting nut 1/4-28"), "", []
		))
		self.assertEqual("Fasteners", classify_part_item(
			dict(base, item_name="Screw ISO 4762 M3x8"), "", []
		))

	def test_part_child_group_custom_and_stable_fallbacks(self):
		base = self.item(item_group="Part", item_name="Reference-specific component")
		self.assertEqual("Custom Mechanical Parts", classify_part_item(
			base, "", [{"supplier": "SZ LCH INDUSTRY CO., LTD"}]
		))
		self.assertEqual("General Mechanical Parts", classify_part_item(base, "", []))
		self.assertEqual("Fasteners", classify_part_item(
			dict(base, item_group="Fasteners"), "", []
		))


if __name__ == "__main__":
	unittest.main()
