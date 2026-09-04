# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import unittest

import frappe
from frappe.utils import nowdate


TEST_SIGNATURE = (
	"data:image/png;base64,"
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class TestOrganizationalModificationRequest(unittest.TestCase):
	def setUp(self):
		self.created_documents = []
		frappe.set_user("Administrator")

	def tearDown(self):
		for name in reversed(self.created_documents):
			doc = frappe.get_doc("Organizational Modification Request", name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc(
				"Organizational Modification Request",
				name,
				force=1,
				ignore_permissions=True,
			)

	def test_approval_implementation_and_closure_lifecycle(self):
		doc = self.make_request("Approved")
		doc.insert(ignore_permissions=True)
		self.created_documents.append(doc.name)
		self.assertEqual(doc.status, "Draft")

		doc.submit()
		self.assertEqual(doc.status, "Approved")

		doc.actions[0].completed = 1
		doc.actual_implementation_date = "2026-10-15"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.status, "Effectiveness Review")
		self.assertEqual(str(doc.actions[0].completion_date), nowdate())

		doc.effectiveness_review_result = "The target control operated without incident."
		doc.change_effective = "Yes"
		doc.closure_quality_reviewer = "Administrator"
		doc.closure_date = "2027-01-15"
		doc.closure_quality_signature = TEST_SIGNATURE
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.status, "Closed")
		self.assertTrue(doc.closure_quality_reviewer_name)

	def test_rejected_request_cannot_be_implemented(self):
		doc = self.make_request("Rejected", include_action=False)
		doc.insert(ignore_permissions=True)
		self.created_documents.append(doc.name)
		doc.submit()
		self.assertEqual(doc.status, "Rejected")

		doc.actual_implementation_date = "2026-10-15"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	@staticmethod
	def make_request(decision, include_action=True):
		values = {
			"doctype": "Organizational Modification Request",
			"requester": "Administrator",
			"request_date": "2026-09-02",
			"planned_implementation_date": "2026-10-15",
			"change_level": "C2 - Significant",
			"change_type_organization": 1,
			"what_is_changing": "A controlled organizational responsibility is changing.",
			"why_change": "The target organization improves accountability.",
			"impact_organization_skills": 1,
			"risk_if_failed": "Responsibilities may be unclear.",
			"risk_controls_before_implementation": "Approve the responsibility matrix and train the affected users.",
			"training_documentation_required": "No",
			"effectiveness_validation_criteria": "The new responsibility is followed without incident.",
			"effectiveness_review_period": "3 months",
			"decision": decision,
			"change_responsible_name_function": "Test Change Owner",
			"change_responsible_approval_date": "2026-09-02",
			"change_responsible_signature": TEST_SIGNATURE,
			"quality_name_function": "Test Quality Manager",
			"quality_approval_date": "2026-09-02",
			"quality_signature": TEST_SIGNATURE,
		}
		if include_action:
			values["actions"] = [{
				"action": "Publish the approved responsibility matrix.",
				"responsible": "Administrator",
				"due_date": "2026-10-10",
			}]
		return frappe.get_doc(values)
