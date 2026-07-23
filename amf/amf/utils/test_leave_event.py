# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from amf.amf.utils import leave_event


class FakeDoc(SimpleNamespace):
	def __init__(self, **values):
		super(FakeDoc, self).__init__(**values)
		self.flags = SimpleNamespace()

	def get(self, fieldname):
		return getattr(self, fieldname, None)

	def set(self, fieldname, value):
		setattr(self, fieldname, value)


def make_leave(**overrides):
	values = {
		"name": "HR-LAP-2026-00001",
		"employee": "EMP-0001",
		"employee_name": "Jane Example",
		"leave_type": "Jour de congé",
		"from_date": "2026-08-03",
		"to_date": "2026-08-05",
		"half_day": 0,
		"workflow_state": "Pending HR Approval",
		"status": "Open",
		"docstatus": 0,
		leave_event.LEAVE_EVENT_FIELD: None,
	}
	values.update(overrides)
	return FakeDoc(**values)


class TestLeaveEvent(unittest.TestCase):
	def test_pending_hr_approval_creates_event_without_waiting_for_hr(self):
		self.assertTrue(leave_event.should_have_leave_event(make_leave()))
		self.assertTrue(
			leave_event.should_have_leave_event(
				make_leave(
					workflow_state="Approved",
					status="Approved",
					docstatus=1,
				)
			)
		)

	def test_unapproved_rejected_and_cancelled_leave_have_no_event(self):
		self.assertFalse(
			leave_event.should_have_leave_event(
				make_leave(workflow_state="Pending Dept Approval")
			)
		)
		self.assertFalse(
			leave_event.should_have_leave_event(
				make_leave(workflow_state="Rejected", status="Rejected")
			)
		)
		self.assertFalse(
			leave_event.should_have_leave_event(
				make_leave(
					workflow_state="Cancelled",
					status="Cancelled",
					docstatus=2,
				)
			)
		)

	def test_event_is_public_all_day_and_google_sync_is_off(self):
		values = leave_event.build_leave_event_values(make_leave())

		self.assertEqual(
			values["subject"], "Jane Example \u2013 Jour de congé"
		)
		self.assertEqual(
			str(values["starts_on"]), "2026-08-03 00:00:00"
		)
		self.assertEqual(
			str(values["ends_on"]), "2026-08-05 23:59:59"
		)
		self.assertEqual(values["event_type"], "Public")
		self.assertEqual(
			values["event_category"], leave_event.OUT_OF_OFFICE_CATEGORY
		)
		self.assertEqual(values["color"], "#2563EB")
		self.assertEqual(values["all_day"], 1)
		self.assertEqual(values["send_reminder"], 0)
		self.assertEqual(values["sync_with_google_calendar"], 0)
		self.assertEqual(values["description"], "")
		self.assertEqual(
			values[leave_event.EVENT_LEAVE_FIELD],
			"HR-LAP-2026-00001",
		)
		self.assertEqual(
			values["event_participants"],
			[
				{
					"reference_doctype": "Employee",
					"reference_docname": "EMP-0001",
				}
			],
		)

	def test_half_day_is_named_with_its_leave_type(self):
		values = leave_event.build_leave_event_values(
			make_leave(
				from_date="2026-08-03",
				to_date="2026-08-03",
				half_day=1,
			)
		)

		self.assertEqual(
			values["subject"],
			"Jane Example \u2013 Jour de congé (half day)",
		)

	def test_each_known_leave_type_has_a_stable_distinct_color(self):
		colors = {
			leave_event.get_leave_type_color(leave_type)
			for leave_type in leave_event.LEAVE_TYPE_COLORS
		}

		self.assertEqual(
			len(colors), len(leave_event.LEAVE_TYPE_COLORS)
		)
		self.assertEqual(
			leave_event.get_leave_type_color("Jour de maladie"),
			"#DC2626",
		)
		self.assertEqual(
			leave_event.get_leave_type_color("Future leave type"),
			leave_event.get_leave_type_color("Future leave type"),
		)

	def test_out_of_office_category_preserves_standard_options(self):
		self.assertEqual(
			leave_event.merge_event_category_options(
				"Event\nMeeting\nCall\nOther"
			),
			"Event\nMeeting\nCall\nOther\nOut of Office",
		)
		self.assertEqual(
			leave_event.merge_event_category_options(
				"Event\nOut of Office"
			),
			"Event\nOut of Office",
		)

	def test_invalid_dates_are_rejected(self):
		with self.assertRaises(leave_event.frappe.ValidationError):
			leave_event.build_leave_event_values(
				make_leave(from_date=None, to_date=None)
			)

		with self.assertRaises(leave_event.frappe.ValidationError):
			leave_event.build_leave_event_values(
				make_leave(from_date="2026-08-05", to_date="2026-08-03")
			)

	def test_existing_link_is_preferred(self):
		leave = make_leave(
			**{leave_event.LEAVE_EVENT_FIELD: "EV00001"}
		)

		with patch.object(
			leave_event.frappe,
			"db",
			SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: "unexpected",
			),
		):
			self.assertEqual(
				leave_event.find_leave_event(leave), "EV00001"
			)

	def test_creation_is_idempotently_linked_to_leave(self):
		leave = make_leave()
		event = FakeDoc(name="EV00001")
		event.insert = lambda **kwargs: None
		db = SimpleNamespace(set_value=unittest.mock.Mock())

		with patch.object(
			leave_event, "find_leave_event", return_value=None
		), patch.object(
			leave_event.frappe, "get_doc", return_value=event
		), patch.object(
			leave_event.frappe, "db", db
		):
			result = leave_event.upsert_leave_event(leave)

		self.assertEqual(result["status"], "created")
		self.assertEqual(result["event"], "EV00001")
		self.assertEqual(
			leave.get(leave_event.LEAVE_EVENT_FIELD), "EV00001"
		)
		db.set_value.assert_called_once()

	def test_unchanged_event_is_not_saved_again(self):
		leave = make_leave(
			**{leave_event.LEAVE_EVENT_FIELD: "EV00001"}
		)
		values = leave_event.build_leave_event_values(leave)
		event = FakeDoc(name="EV00001", **values)
		event.save = unittest.mock.Mock()

		with patch.object(
			leave_event, "find_leave_event", return_value="EV00001"
		), patch.object(
			leave_event.frappe, "get_doc", return_value=event
		):
			result = leave_event.upsert_leave_event(leave)

		self.assertEqual(result["status"], "unchanged")
		event.save.assert_not_called()

	def test_date_change_updates_same_event(self):
		leave = make_leave(
			to_date="2026-08-07",
			**{leave_event.LEAVE_EVENT_FIELD: "EV00001"}
		)
		old_values = leave_event.build_leave_event_values(
			make_leave(to_date="2026-08-05")
		)
		event = FakeDoc(name="EV00001", **old_values)
		event.save = unittest.mock.Mock()

		with patch.object(
			leave_event, "find_leave_event", return_value="EV00001"
		), patch.object(
			leave_event.frappe, "get_doc", return_value=event
		):
			result = leave_event.upsert_leave_event(leave)

		self.assertEqual(result["status"], "updated")
		self.assertEqual(str(event.ends_on), "2026-08-07 23:59:59")
		event.save.assert_called_once_with(ignore_permissions=True)

	def test_rejection_clears_link_then_removes_event(self):
		leave = make_leave(
			workflow_state="Rejected",
			status="Rejected",
			**{leave_event.LEAVE_EVENT_FIELD: "EV00001"}
		)
		db = SimpleNamespace(set_value=unittest.mock.Mock())

		with patch.object(
			leave_event, "find_leave_event", return_value="EV00001"
		), patch.object(
			leave_event.frappe, "db", db
		), patch.object(
			leave_event.frappe, "delete_doc"
		) as delete_doc:
			result = leave_event.remove_leave_event(leave)

		self.assertEqual(result["status"], "removed")
		self.assertIsNone(leave.get(leave_event.LEAVE_EVENT_FIELD))
		delete_doc.assert_called_once_with(
			"Event",
			"EV00001",
			ignore_permissions=True,
			ignore_missing=True,
		)

	def test_backfill_processes_every_eligible_leave_idempotently(self):
		rows = [
			SimpleNamespace(name="HR-LAP-2026-00001"),
			SimpleNamespace(name="HR-LAP-2026-00002"),
			SimpleNamespace(name="HR-LAP-2026-00003"),
		]
		results = iter(
			(
				{"status": "created"},
				{"status": "updated"},
				{"status": "unchanged"},
			)
		)

		with patch.object(
			leave_event.frappe, "only_for"
		) as only_for, patch.object(
			leave_event.frappe, "get_all", return_value=rows
		) as get_all, patch.object(
			leave_event.frappe,
			"get_doc",
			side_effect=lambda doctype, name: make_leave(name=name),
		), patch.object(
			leave_event,
			"upsert_leave_event",
			side_effect=lambda leave: next(results),
		):
			counts = leave_event.backfill_leave_events()

		self.assertEqual(
			counts,
			{
				"eligible": 3,
				"created": 1,
				"updated": 1,
				"unchanged": 1,
			},
		)
		only_for.assert_called_once_with("System Manager")
		self.assertEqual(
			get_all.call_args.kwargs["filters"]["workflow_state"],
			["in", leave_event.EVENT_STATES],
		)


if __name__ == "__main__":
	unittest.main()
