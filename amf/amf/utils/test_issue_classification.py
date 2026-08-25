# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest

from amf.amf.utils.issue_classification import (
	ISSUE_CLASSIFICATION_CUSTOM_FIELDS,
	ISSUE_TYPE_DEFINITIONS,
	LEGACY_ISSUE_TYPE_MAP,
	PROCESS_DEFINITIONS,
	_issue_type_values_to_routing,
	rank_issue_type_suggestions,
)


class TestIssueClassification(unittest.TestCase):
	def test_process_names_codes_and_owners_are_unique(self):
		codes = [row["code"] for row in PROCESS_DEFINITIONS]
		names = [row["name"] for row in PROCESS_DEFINITIONS]
		self.assertEqual(len(codes), len(set(codes)))
		self.assertEqual(len(names), len(set(names)))
		self.assertTrue(all(row.get("primary_owner") for row in PROCESS_DEFINITIONS))

	def test_rnd_has_both_named_owners(self):
		rnd = next(row for row in PROCESS_DEFINITIONS if row["code"] == "RND")
		self.assertEqual(rnd["primary_owner"], "matthieu.gevers@amf.ch")
		self.assertEqual(rnd["secondary_owner"], "nicolas.craquelin@amf.ch")

	def test_each_type_has_a_valid_process_and_unique_code(self):
		process_names = {row["name"] for row in PROCESS_DEFINITIONS}
		codes = [row["code"] for row in ISSUE_TYPE_DEFINITIONS]
		names = [row["name"] for row in ISSUE_TYPE_DEFINITIONS]
		self.assertEqual(len(codes), len(set(codes)))
		self.assertEqual(len(names), len(set(names)))
		self.assertTrue(all(row["process"] in process_names for row in ISSUE_TYPE_DEFINITIONS))

	def test_each_legacy_mapping_targets_a_canonical_type(self):
		canonical_names = {row["name"] for row in ISSUE_TYPE_DEFINITIONS}
		self.assertTrue(all(target in canonical_names for target in LEGACY_ISSUE_TYPE_MAP.values()))

	def test_both_issue_doctypes_have_suggestion_and_confirmation_fields(self):
		for doctype in ("Issue", "AMF Issue Test"):
			fields = {
				definition["fieldname"]: definition
				for definition in ISSUE_CLASSIFICATION_CUSTOM_FIELDS[doctype]
			}
			self.assertEqual(fields["issue_type_suggestions"]["fieldtype"], "HTML")
			self.assertEqual(fields["issue_type_user_confirmed"]["hidden"], 1)
			self.assertEqual(fields["issue_type_user_confirmed"]["read_only"], 1)

	def test_issue_type_process_translates_to_issue_process_involved(self):
		routing = _issue_type_values_to_routing(
			{
				"process": "Manufacturing",
				"process_owner": "owner@example.com",
				"process_co_owner": "co-owner@example.com",
				"is_active": 1,
			},
			include_active=True,
		)
		self.assertEqual(routing["process_involved"], "Manufacturing")
		self.assertNotIn("process", routing)
		self.assertEqual(routing["is_active"], 1)

	def test_supplier_certificate_subject_is_classified_to_procurement_documentation(self):
		suggestions = rank_issue_type_suggestions(
			"Supplier material certificate is missing for the delivered batch"
		)
		self.assertTrue(suggestions)
		self.assertEqual(suggestions[0]["name"], "Supplier Documentation / Certificate Issue")
		self.assertEqual(suggestions[0]["process"], "Procurement")

	def test_permission_subject_is_classified_to_it_access(self):
		suggestions = rank_issue_type_suggestions(
			"ERPNext permission denied when the new user tries to login"
		)
		self.assertTrue(suggestions)
		self.assertEqual(suggestions[0]["name"], "IT Access / User Account Issue")

	def test_transit_damage_is_distinct_from_packaging(self):
		suggestions = rank_issue_type_suggestions(
			"Customer parcel damaged in transport by the carrier during delivery"
		)
		self.assertTrue(suggestions)
		self.assertEqual(suggestions[0]["name"], "Transit Damage / Delivery Condition Issue")

	def test_firmware_subject_is_classified_to_embedded_software(self):
		suggestions = rank_issue_type_suggestions(
			"Device firmware bootloader loses communication after restart"
		)
		self.assertTrue(suggestions)
		self.assertEqual(suggestions[0]["name"], "Firmware / Embedded Software Issue")

	def test_supplier_context_distinguishes_inbound_from_customer_delivery(self):
		suggestions = rank_issue_type_suggestions("Late delivery from supplier")
		self.assertEqual(suggestions[0]["name"], "Supplier Delivery / Availability Issue")

	def test_erpnext_error_outweighs_document_context(self):
		suggestions = rank_issue_type_suggestions("ERPNext error while saving Sales Order")
		self.assertEqual(suggestions[0]["name"], "ERPNext / Business Application Issue")

	def test_pcb_soldering_is_a_manufacturing_nonconformity(self):
		suggestions = rank_issue_type_suggestions("PCB soldering defect after assembly")
		self.assertEqual(suggestions[0]["name"], "Electrical / Electronic Manufacturing Nonconformity")

	def test_drawing_error_is_rnd_documentation_not_machining(self):
		suggestions = rank_issue_type_suggestions("Drawing has incorrect dimension")
		self.assertEqual(suggestions[0]["name"], "Product Specification / R&D Documentation Issue")

	def test_generic_subject_does_not_force_a_classification(self):
		self.assertEqual(rank_issue_type_suggestions("There is a problem"), [])


if __name__ == "__main__":
	unittest.main()
