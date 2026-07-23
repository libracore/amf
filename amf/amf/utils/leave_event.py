# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import hashlib

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import (
	make_property_setter,
)
from frappe.utils import cint, cstr, get_datetime, getdate


LEAVE_EVENT_FIELD = "amf_leave_event"
EVENT_LEAVE_FIELD = "amf_leave_application"

# Department approval moves the current workflow to Pending HR Approval.
# Approved remains eligible so a later workflow transition does not remove the
# already-created company calendar entry.
EVENT_STATES = ("Pending HR Approval", "Approved")
OUT_OF_OFFICE_CATEGORY = "Out of Office"

LEAVE_TYPE_COLORS = {
	"Jour autorisé": "#F59E0B",
	"Jour de congé": "#2563EB",
	"Jour de congé mat/paternité": "#8B5CF6",
	"Jour de congé non-payé": "#64748B",
	"Jour de maladie": "#DC2626",
	"Jour de repos": "#16A34A",
	"Jour de repos compensatoire": "#0D9488",
	"Jours de congé - cadres": "#4F46E5",
	"Télétravail": "#0891B2",
}

FALLBACK_COLORS = (
	"#2563EB",
	"#7C3AED",
	"#DB2777",
	"#DC2626",
	"#EA580C",
	"#CA8A04",
	"#16A34A",
	"#0D9488",
	"#0891B2",
	"#4F46E5",
)

LEAVE_EVENT_CUSTOM_FIELDS = {
	"Leave Application": [
		{
			"fieldname": LEAVE_EVENT_FIELD,
			"fieldtype": "Link",
			"label": "Company Leave Event",
			"options": "Event",
			"insert_after": "amended_from",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
	],
	"Event": [
		{
			"fieldname": EVENT_LEAVE_FIELD,
			"fieldtype": "Link",
			"label": "Leave Application",
			"options": "Leave Application",
			"insert_after": "description",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"unique": 1,
		},
	],
}


def setup_leave_event_integration():
	"""Install the links used to keep one Event per Leave Application."""
	create_custom_fields(LEAVE_EVENT_CUSTOM_FIELDS, update=True)
	ensure_out_of_office_event_category()


def ensure_out_of_office_event_category():
	"""Add Out of Office while preserving the standard Event categories."""
	event_category = frappe.get_meta("Event").get_field("event_category")
	options = merge_event_category_options(event_category.options)
	if cstr(event_category.options) == options:
		return

	make_property_setter(
		"Event",
		"event_category",
		"options",
		options,
		"Text",
	)
	frappe.clear_cache(doctype="Event")


def merge_event_category_options(current_options):
	options = [
		option.strip()
		for option in cstr(current_options).splitlines()
		if option.strip()
	]
	if OUT_OF_OFFICE_CATEGORY not in options:
		options.append(OUT_OF_OFFICE_CATEGORY)
	return "\n".join(options)


def sync_leave_event(doc, method=None):
	"""
	Keep a native ERPNext Event aligned with a Leave Application.

	This hook intentionally performs only the internal ERPNext step. Generated
	Events have Google synchronization disabled.
	"""
	if not _tracking_fields_are_installed():
		return {"status": "incomplete", "reason": "missing_custom_fields"}

	if method == "on_trash" or not should_have_leave_event(doc):
		return remove_leave_event(doc)

	return upsert_leave_event(doc)


@frappe.whitelist()
def backfill_leave_events():
	"""System Manager entry point for the idempotent Event reconciliation."""
	frappe.only_for("System Manager")
	return reconcile_leave_events()


def reconcile_leave_events():
	"""Create or update Events for every currently eligible Leave Application."""
	leave_applications = frappe.get_all(
		"Leave Application",
		filters={
			"workflow_state": ["in", EVENT_STATES],
			"docstatus": ["!=", 2],
			"status": ["not in", ("Rejected", "Cancelled")],
		},
		fields=["name"],
		order_by="from_date asc, name asc",
	)

	counts = {
		"eligible": len(leave_applications),
		"created": 0,
		"updated": 0,
		"unchanged": 0,
	}
	for row in leave_applications:
		result = upsert_leave_event(
			frappe.get_doc("Leave Application", row.name)
		)
		counts[result["status"]] += 1

	return counts


def should_have_leave_event(leave):
	if not leave or cint(_doc_value(leave, "docstatus")) == 2:
		return False
	if _doc_value(leave, "status") in ("Rejected", "Cancelled"):
		return False
	return _doc_value(leave, "workflow_state") in EVENT_STATES


def build_leave_event_values(leave):
	"""Build privacy-safe values using ERPNext's inclusive all-day end date."""
	raw_from_date = _doc_value(leave, "from_date")
	raw_to_date = _doc_value(leave, "to_date")
	if not raw_from_date or not raw_to_date:
		raise frappe.ValidationError(
			"Leave dates are required to create the company calendar event."
		)
	from_date = getdate(raw_from_date)
	to_date = getdate(raw_to_date)
	if to_date < from_date:
		raise frappe.ValidationError(
			"Leave end date cannot be before its start date."
		)

	employee_name = cstr(
		_doc_value(leave, "employee_name") or _doc_value(leave, "employee")
	).strip()
	leave_type = cstr(_doc_value(leave, "leave_type")).strip()
	subject_type = leave_type or OUT_OF_OFFICE_CATEGORY
	if cint(_doc_value(leave, "half_day")):
		subject_type = "{0} (half day)".format(subject_type)
	subject = "{0} \u2013 {1}".format(employee_name, subject_type)[:140]

	employee = cstr(_doc_value(leave, "employee")).strip()
	participants = []
	if employee:
		participants.append(
			{
				"reference_doctype": "Employee",
				"reference_docname": employee,
			}
		)

	return {
		"subject": subject,
		"event_category": OUT_OF_OFFICE_CATEGORY,
		"event_type": "Public",
		"color": get_leave_type_color(leave_type),
		"starts_on": get_datetime(
			"{0} 00:00:00".format(from_date.isoformat())
		),
		"ends_on": get_datetime(
			"{0} 23:59:59".format(to_date.isoformat())
		),
		"all_day": 1,
		"status": "Open",
		"send_reminder": 0,
		"repeat_this_event": 0,
		"description": "",
		"event_participants": participants,
		EVENT_LEAVE_FIELD: _doc_value(leave, "name"),
		# Google publication is deliberately a separate second step.
		"sync_with_google_calendar": 0,
	}


def get_leave_type_color(leave_type):
	leave_type = cstr(leave_type).strip()
	if leave_type in LEAVE_TYPE_COLORS:
		return LEAVE_TYPE_COLORS[leave_type]

	digest = hashlib.sha256(leave_type.encode("utf-8")).hexdigest()
	return FALLBACK_COLORS[int(digest[:8], 16) % len(FALLBACK_COLORS)]


def upsert_leave_event(leave):
	event_values = build_leave_event_values(leave)
	event_name = find_leave_event(leave)

	if event_name:
		event = frappe.get_doc("Event", event_name)
		changed = False
		for fieldname, value in event_values.items():
			if _values_differ(event.get(fieldname), value):
				event.set(fieldname, value)
				changed = True

		if changed:
			event.flags.ignore_version = True
			event.save(ignore_permissions=True)
			status = "updated"
		else:
			status = "unchanged"
	else:
		event = frappe.get_doc(
			dict({"doctype": "Event"}, **event_values)
		)
		event.flags.ignore_version = True
		event.insert(ignore_permissions=True)
		event_name = event.name
		status = "created"

	_set_leave_event_link(leave, event_name)
	return {
		"status": status,
		"leave_application": _doc_value(leave, "name"),
		"event": event_name,
	}


def find_leave_event(leave):
	linked_event = _doc_value(leave, LEAVE_EVENT_FIELD)
	if linked_event and frappe.db.exists("Event", linked_event):
		return linked_event

	return frappe.db.get_value(
		"Event",
		{EVENT_LEAVE_FIELD: _doc_value(leave, "name")},
		"name",
	)


def remove_leave_event(leave):
	event_name = find_leave_event(leave)
	_set_leave_event_link(leave, None)

	if not event_name:
		return {
			"status": "unchanged",
			"leave_application": _doc_value(leave, "name"),
		}

	frappe.delete_doc(
		"Event",
		event_name,
		ignore_permissions=True,
		ignore_missing=True,
	)
	return {
		"status": "removed",
		"leave_application": _doc_value(leave, "name"),
		"event": event_name,
	}


def _set_leave_event_link(leave, event_name):
	leave_name = _doc_value(leave, "name")
	if not leave_name or _doc_value(leave, LEAVE_EVENT_FIELD) == event_name:
		return

	frappe.db.set_value(
		"Leave Application",
		leave_name,
		LEAVE_EVENT_FIELD,
		event_name,
		update_modified=False,
	)
	if hasattr(leave, "set"):
		leave.set(LEAVE_EVENT_FIELD, event_name)
	else:
		setattr(leave, LEAVE_EVENT_FIELD, event_name)


def _tracking_fields_are_installed():
	return (
		frappe.db.has_column("Leave Application", LEAVE_EVENT_FIELD)
		and frappe.db.has_column("Event", EVENT_LEAVE_FIELD)
	)


def _values_differ(current, expected):
	if isinstance(expected, (list, tuple)):
		return _normalize_participants(current) != _normalize_participants(
			expected
		)
	if hasattr(expected, "isoformat"):
		return get_datetime(current) != expected
	return cstr(current) != cstr(expected)


def _normalize_participants(participants):
	return sorted(
		(
			cstr(_doc_value(participant, "reference_doctype")),
			cstr(_doc_value(participant, "reference_docname")),
		)
		for participant in (participants or [])
	)


def _doc_value(doc, fieldname):
	if not doc:
		return None
	if hasattr(doc, "get"):
		return doc.get(fieldname)
	return getattr(doc, fieldname, None)
