# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest
from unittest.mock import patch

import frappe

from amf.amf.utils.amf_issue_test_management import (
	AMF_ISSUE_TEST_INTEGRATION_CUSTOM_FIELDS,
	AMF_ISSUE_TEST_LINK_FIELD,
	create_linked_issue,
	set_linked_issue_party,
	sync_linked_issue_party,
)


class FakeIssue(object):
	def __init__(self):
		self.name = "ISS-TEST-0001"
		self.values = {}
		self.insert_kwargs = None

	def set(self, fieldname, value):
		self.values[fieldname] = value

	def insert(self, **kwargs):
		self.insert_kwargs = kwargs


class TestAMFIssueTestIntegration(unittest.TestCase):
	def setUp(self):
		self.source = frappe._dict(
			{
				"doctype": "AMF Issue Test",
				"name": "AMF-ISS-TEST-2026-0001",
				"subject": "Test traceability bridge",
				"input_selection": "Internal Issue",
				"issue_type": "ERPNext / Business Application Issue",
				"urgency": "Low",
				"impact": "Medium",
				"customer": None,
				"customer_issue": "CUST-0001",
				"supplier": None,
				"contact": None,
				"contact_new": "CONT-0001",
				"raised_by_email": None,
			}
		)

	def test_traceability_field_is_a_unique_link(self):
		field = AMF_ISSUE_TEST_INTEGRATION_CUSTOM_FIELDS["Issue"][0]
		self.assertEqual(field["fieldname"], AMF_ISSUE_TEST_LINK_FIELD)
		self.assertEqual(field["fieldtype"], "Link")
		self.assertEqual(field["options"], "AMF Issue Test")
		self.assertEqual(field["read_only"], 1)
		self.assertEqual(field["unique"], 1)

	@patch("amf.amf.utils.amf_issue_test_management.frappe")
	def test_create_linked_issue_copies_only_required_values(self, mocked_frappe):
		mocked_frappe.db.get_value.return_value = None
		issue = FakeIssue()
		mocked_frappe.new_doc.return_value = issue

		result = create_linked_issue(self.source)

		self.assertEqual(result, issue.name)
		self.assertEqual(
			issue.values,
			{
				"subject": self.source.subject,
				"input_selection": self.source.input_selection,
				"issue_type": self.source.issue_type,
				"urgency": self.source.urgency,
				"impact": self.source.impact,
				"customer": self.source.customer_issue,
				"customer_issue": self.source.customer_issue,
				"supplier": "",
				"contact": "",
				"contact_new": self.source.contact_new,
				"raised_by_email": "",
				AMF_ISSUE_TEST_LINK_FIELD: self.source.name,
			},
		)
		self.assertEqual(issue.insert_kwargs, {"ignore_permissions": True})

	@patch("amf.amf.utils.amf_issue_test_management.frappe")
	def test_create_linked_issue_is_idempotent(self, mocked_frappe):
		mocked_frappe.db.get_value.return_value = "ISS-2026-00001"

		result = create_linked_issue(self.source)

		self.assertEqual(result, "ISS-2026-00001")
		mocked_frappe.new_doc.assert_not_called()

	def test_party_mapping_clears_new_doc_defaults_when_source_has_no_customer(self):
		issue = FakeIssue()
		source = frappe._dict(
			{
				"customer": None,
				"customer_issue": None,
				"supplier": None,
				"contact": None,
				"contact_new": None,
				"raised_by_email": None,
			}
		)

		set_linked_issue_party(issue, source)

		self.assertIsNone(issue.values["customer"])
		self.assertIsNone(issue.values["customer_issue"])
		self.assertIsNone(issue.values["supplier"])
		self.assertIsNone(issue.values["contact"])
		self.assertIsNone(issue.values["contact_new"])
		self.assertIsNone(issue.values["raised_by_email"])

	@patch("amf.amf.utils.amf_issue_test_management.frappe")
	def test_validate_restores_source_customer_after_erpnext_inference(self, mocked_frappe):
		issue = FakeIssue()
		issue.doctype = "Issue"
		issue.values.update(
			{
				AMF_ISSUE_TEST_LINK_FIELD: self.source.name,
				"customer": "WRONG-CUSTOMER",
				"customer_issue": None,
				"supplier": "WRONG-SUPPLIER",
				"contact": "WRONG-CONTACT",
			}
		)
		issue.get = issue.values.get
		mocked_frappe.db.get_value.return_value = self.source

		sync_linked_issue_party(issue)

		self.assertEqual(issue.values["customer"], self.source.customer_issue)
		self.assertEqual(issue.values["customer_issue"], self.source.customer_issue)
		self.assertIsNone(issue.values["supplier"])
		self.assertIsNone(issue.values["contact"])
		self.assertEqual(issue.values["contact_new"], self.source.contact_new)

	def test_party_mapping_copies_supplier(self):
		issue = FakeIssue()
		source = frappe._dict(
			{
				"customer": None,
				"customer_issue": None,
				"supplier": "SUPP-0001",
				"contact": None,
				"contact_new": None,
				"raised_by_email": None,
			}
		)

		set_linked_issue_party(issue, source)

		self.assertEqual(issue.values["supplier"], source.supplier)
		self.assertIsNone(issue.values["customer"])
		self.assertIsNone(issue.values["customer_issue"])


if __name__ == "__main__":
	unittest.main()
