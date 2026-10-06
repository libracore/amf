# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from unittest.mock import patch

import frappe

from amf.amf.utils.issue_history import _get_party_issues, get_issue_history


class TestIssueHistory(unittest.TestCase):
	@patch("amf.amf.utils.issue_history._add_issue_items")
	@patch("amf.amf.utils.issue_history._get_party_issues")
	@patch("amf.amf.utils.issue_history.frappe")
	def test_mirrored_issue_appears_once_with_legacy_link(self, mocked_frappe, get_party_issues, add_items):
		mocked_frappe.db.exists.return_value = True
		mocked_frappe.has_permission.return_value = True
		source = frappe._dict({
			"name": "AMF-ISS-TEST-0001", "creation": "2026-10-05 10:00:00",
			"opening_date": "2026-10-05", "item": None,
		})
		mirror = frappe._dict({
			"name": "ISS-0001", "creation": "2026-10-05 10:01:00",
			"opening_date": "2026-10-05", "item": None,
			"amf_issue_test": source.name,
		})
		older = frappe._dict({
			"name": "ISS-0000", "creation": "2026-10-01 10:00:00",
			"opening_date": "2026-10-01", "item": "ITEM-001",
			"amf_issue_test": None,
		})
		get_party_issues.side_effect = [[source], [mirror, older]]

		result = get_issue_history("Supplier Issue", "SUP-001")

		self.assertEqual(result["total"], 2)
		self.assertEqual([row.name for row in result["issues"]], [source.name, older.name])
		self.assertEqual(result["issues"][0].legacy_issue, mirror.name)
		self.assertEqual(result["issues"][1]["items"][0]["item_code"], "ITEM-001")
		add_items.assert_called_once_with([source])

	@patch("amf.amf.utils.issue_history.frappe")
	def test_visible_customer_field_overrides_stale_standard_customer(self, mocked_frappe):
		mocked_frappe.has_permission.return_value = True
		correct = frappe._dict({"customer_issue": "CUST-001", "customer": "CUST-002"})
		stale = frappe._dict({"customer_issue": "CUST-002", "customer": "CUST-001"})
		fallback = frappe._dict({"customer_issue": None, "customer": "CUST-001"})
		mocked_frappe.get_list.return_value = [correct, stale, fallback]

		rows = _get_party_issues("Issue", "Customer", "CUST-001")

		self.assertEqual(rows, [correct, fallback])


if __name__ == "__main__":
	unittest.main()
