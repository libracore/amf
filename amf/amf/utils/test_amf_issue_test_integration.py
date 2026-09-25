# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest
from unittest.mock import patch

import frappe

from amf.amf.utils.amf_issue_test_management import (
	AMF_ISSUE_TEST_INTEGRATION_CUSTOM_FIELDS,
	AMF_ISSUE_TEST_LINK_FIELD,
	create_linked_issue,
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


if __name__ == "__main__":
	unittest.main()
