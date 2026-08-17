# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import unittest
from unittest.mock import patch

from amf.amf.utils import check_issue, forecast


class TestDisabledLegacyWeeklyEmails(unittest.TestCase):
	def test_weekly_open_issues_entry_does_not_query_or_send(self):
		with patch.object(check_issue.frappe, "get_list") as get_list:
			result = check_issue.fetch_open_issues()

		self.assertTrue(result["disabled"])
		get_list.assert_not_called()

	def test_weekly_open_issues_sender_is_disabled(self):
		result = check_issue.send_email_report("content", ["test@example.com"])

		self.assertTrue(result["disabled"])

	def test_standard_item_availability_entry_does_not_query_or_send(self):
		result = forecast.get_item_details_and_quantities()

		self.assertTrue(result["disabled"])

	def test_standard_item_availability_sender_is_disabled(self):
		result = forecast.send_email_forecast("content")

		self.assertTrue(result["disabled"])


if __name__ == "__main__":
	unittest.main()
