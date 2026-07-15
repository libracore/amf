# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.utils import cstr, flt, today


RCA_TABLE_FIELD = "root_cause_whys"
RCA_STATUS_FIELD = "root_cause_analysis_status"
RCA_REQUIRED_FIELD = "root_cause_analysis_required"
RCA_STATEMENT_FIELD = "root_cause_statement"
RCA_LEGACY_DESCRIPTION_FIELD = "root_cause_description"
EFFECTIVENESS_RESULT_FIELD = "effectiveness_result"
ISSUE_ITEMS_TABLE_FIELD = "issue_items"

PRIORITY_MATRIX = {
	("Low", "Low"): "P3 - Routine Follow-Up",
	("Medium", "Low"): "P3 - Routine Follow-Up",
	("High", "Low"): "P2 - Controlled Action",
	("Low", "Medium"): "P3 - Routine Follow-Up",
	("Medium", "Medium"): "P2 - Controlled Action",
	("High", "Medium"): "P1 - Immediate Containment",
	("Low", "High"): "P2 - Controlled Action",
	("Medium", "High"): "P1 - Immediate Containment",
	("High", "High"): "P1 - Immediate Containment",
}

DEFAULT_WHY_ROWS = (
	{
		"question": "Why did the issue occur?",
		"cause_type": "Symptom",
	},
	{
		"question": "Why was that condition possible?",
		"cause_type": "Direct Cause",
	},
	{
		"question": "Why did the process or control not prevent it?",
		"cause_type": "Process Cause",
	},
	{
		"question": "Why was the weakness not detected earlier?",
		"cause_type": "Escape Cause",
	},
	{
		"question": "Why does the management system allow this recurrence risk?",
		"cause_type": "System Cause",
	},
)


def clear_amf_issue_test_management_meta_cache():
	"""Clear metadata after Issue customizations are synced from amf/custom JSON files."""
	frappe.clear_cache(doctype="AMF Issue Test")
	frappe.clear_cache(doctype="Issue Type")
	frappe.clear_cache(doctype="AMF Issue Test Item")
	frappe.clear_cache(doctype="AMF Issue Test Root Cause Why")


def validate_issue_management(doc, method=None):
	"""Normalize computed Issue management fields without blocking normal support flow."""
	if doc.doctype != "AMF Issue Test":
		return

	normalize_root_cause_whys(doc)
	set_issue_creator(doc)
	set_internal_contact_from_person(doc)
	sync_issue_items_from_source(doc)
	normalize_raised_by_contact(doc)
	derive_root_cause_statement(doc)
	derive_root_cause_analysis_status(doc)
	derive_priority_result(doc)
	set_resolution_dates(doc)


def set_issue_creator(doc):
	if not _doc_has_field(doc, "amf_person") or cstr(doc.get("amf_person")).strip():
		return

	user = cstr(doc.get("owner")).strip() or cstr(frappe.session.user).strip()
	if user and user != "Guest" and frappe.db.exists("User", user):
		doc.set("amf_person", user)


def set_internal_contact_from_person(doc):
	if not _doc_has_field(doc, "amf_contact"):
		return

	user = cstr(doc.get("amf_person")).strip()
	if not user:
		doc.set("amf_contact", "")
		return

	full_name = frappe.db.get_value("User", user, "full_name")
	doc.set("amf_contact", full_name or user)


def sync_issue_items_from_source(doc):
	if not _doc_has_field(doc, ISSUE_ITEMS_TABLE_FIELD):
		return

	source = get_issue_items_source(doc)
	if not source:
		return

	source_doctype, source_name = source
	if not frappe.db.exists(source_doctype, source_name):
		return

	source_doc = frappe.get_doc(source_doctype, source_name)
	source_rows = get_issue_item_rows_from_source(source_doc)
	if get_existing_issue_item_rows(doc) == source_rows:
		return

	doc.set(ISSUE_ITEMS_TABLE_FIELD, [])

	for source_row in source_rows:
		doc.append(
			ISSUE_ITEMS_TABLE_FIELD,
			source_row,
		)


def get_issue_items_source(doc):
	delivery_note = cstr(doc.get("delivery_note")).strip()
	if delivery_note:
		return "Delivery Note", delivery_note

	sales_order = cstr(doc.get("sales_order")).strip()
	if sales_order:
		return "Sales Order", sales_order

	return None


def get_issue_item_rows_from_source(source_doc):
	rows = []
	for source_row in source_doc.get("items") or []:
		rows.append(
			{
				"item_code": cstr(source_row.get("item_code")).strip(),
				"item_name": cstr(source_row.get("item_name")).strip(),
				"quantity": flt(source_row.get("qty")),
				"serial_no": cstr(source_row.get("serial_no")).strip(),
				"batch_no": cstr(source_row.get("batch_no")).strip(),
			}
		)

	return rows


def get_existing_issue_item_rows(doc):
	rows = []
	for row in doc.get(ISSUE_ITEMS_TABLE_FIELD) or []:
		rows.append(
			{
				"item_code": cstr(row.get("item_code")).strip(),
				"item_name": cstr(row.get("item_name")).strip(),
				"quantity": flt(row.get("quantity")),
				"serial_no": cstr(row.get("serial_no")).strip(),
				"batch_no": cstr(row.get("batch_no")).strip(),
			}
		)

	return rows


def normalize_raised_by_contact(doc):
	if not _doc_has_field(doc, "raised_by_email"):
		return

	value = cstr(doc.get("raised_by_email")).strip()
	if not value:
		return

	if frappe.db.exists("Contact", value):
		sync_raised_by_email_from_contact(doc, value)
		return

	if "@" not in value:
		return

	contact = get_contact_for_email(
		value,
		cstr(doc.get("customer_issue")).strip() or cstr(doc.get("customer")).strip(),
	)
	if contact:
		doc.set("raised_by_email", contact)
		sync_raised_by_email_from_contact(doc, contact)
		return

	if _doc_has_field(doc, "raised_by") and not cstr(doc.get("raised_by")).strip():
		doc.set("raised_by", value)
	doc.set("raised_by_email", "")


def sync_raised_by_email_from_contact(doc, contact):
	if not _doc_has_field(doc, "raised_by"):
		return

	email = get_contact_email(contact)
	if email:
		doc.set("raised_by", email)


def get_contact_email(contact):
	email = frappe.db.get_value("Contact", contact, "email_id")
	if email:
		return email

	return frappe.db.get_value(
		"Contact Email",
		{"parent": contact, "parenttype": "Contact", "is_primary": 1},
		"email_id",
	) or frappe.db.get_value(
		"Contact Email",
		{"parent": contact, "parenttype": "Contact"},
		"email_id",
	)


def get_contact_for_email(email, customer=None):
	if customer:
		contact = frappe.db.sql(
			"""
			SELECT contact.name
			FROM `tabContact` contact
			INNER JOIN `tabDynamic Link` link
				ON link.parent = contact.name
				AND link.parenttype = 'Contact'
				AND link.link_doctype = 'Customer'
				AND link.link_name = %s
			LEFT JOIN `tabContact Email` contact_email
				ON contact_email.parent = contact.name
				AND contact_email.parenttype = 'Contact'
			WHERE contact.email_id = %s OR contact_email.email_id = %s
			ORDER BY contact.is_primary_contact DESC, contact.idx DESC, contact.name
			LIMIT 1
			""",
			(customer, email, email),
		)
		if contact:
			return contact[0][0]

	contact = frappe.db.get_value("Contact", {"email_id": email}, "name")
	if contact:
		return contact

	return frappe.db.get_value(
		"Contact Email",
		{"email_id": email, "parenttype": "Contact"},
		"parent",
	)


def derive_priority_result(doc):
	if not _doc_has_field(doc, "priority_result"):
		return

	for fieldname in ("impact", "urgency"):
		if _doc_has_field(doc, fieldname) and cstr(doc.get(fieldname)).strip() == "Critical":
			doc.set(fieldname, "High")

	doc.set(
		"priority_result",
		get_priority_result(doc.get("impact"), doc.get("urgency")),
	)


def get_priority_result(impact, urgency):
	normalized_impact = normalize_priority_level(impact)
	normalized_urgency = normalize_priority_level(urgency)
	if not normalized_impact or not normalized_urgency:
		return ""

	return PRIORITY_MATRIX.get((normalized_impact, normalized_urgency), "")


def normalize_priority_level(value):
	value = cstr(value).strip()
	if value == "Critical":
		return "High"
	if value in ("Low", "Medium", "High"):
		return value

	return ""


def normalize_root_cause_whys(doc):
	if not _doc_has_field(doc, RCA_TABLE_FIELD):
		return

	for idx, row in enumerate(doc.get(RCA_TABLE_FIELD) or [], start=1):
		default = get_default_why_row(idx)
		if not default:
			continue
		if not cstr(row.get("why_question")).strip():
			row.why_question = default["question"]
		if not cstr(row.get("cause_type")).strip() or is_old_generated_cause_type(row, idx):
			row.cause_type = default["cause_type"]


def get_default_why_row(idx):
	if idx <= 0 or idx > len(DEFAULT_WHY_ROWS):
		return None

	return DEFAULT_WHY_ROWS[idx - 1]


def is_old_generated_cause_type(row, idx):
	return (
		idx == 4
		and cstr(row.get("why_question")).strip() == DEFAULT_WHY_ROWS[idx - 1]["question"]
		and cstr(row.get("cause_type")).strip() == "System Cause"
	)


def derive_root_cause_statement(doc):
	if not _doc_has_field(doc, RCA_STATEMENT_FIELD):
		return
	if cstr(doc.get(RCA_STATEMENT_FIELD)).strip():
		return

	root_cause_row = get_selected_root_cause_row(doc)
	if root_cause_row and cstr(root_cause_row.get("cause_statement")).strip():
		doc.set(RCA_STATEMENT_FIELD, cstr(root_cause_row.get("cause_statement")).strip())


def derive_root_cause_analysis_status(doc):
	if not _doc_has_field(doc, RCA_STATUS_FIELD):
		return

	if cstr(doc.get(EFFECTIVENESS_RESULT_FIELD)) == "Effective":
		doc.set(RCA_STATUS_FIELD, "Verified")
		return

	if cstr(doc.get(RCA_STATEMENT_FIELD)).strip() or get_selected_root_cause_row(doc):
		doc.set(RCA_STATUS_FIELD, "Root Cause Identified")
		return

	has_analysis = bool(cstr(doc.get(RCA_LEGACY_DESCRIPTION_FIELD)).strip())
	for row in doc.get(RCA_TABLE_FIELD) or []:
		if cstr(row.get("cause_statement")).strip() or cstr(row.get("evidence")).strip():
			has_analysis = True
			break

	doc.set(RCA_STATUS_FIELD, "In Progress" if has_analysis else "Not Started")


def get_selected_root_cause_row(doc):
	selected = [
		row
		for row in doc.get(RCA_TABLE_FIELD) or []
		if row.get("is_root_cause") and cstr(row.get("cause_statement")).strip()
	]
	if not selected:
		return None

	return sorted(selected, key=lambda row: row.get("idx") or 0)[-1]


def set_resolution_dates(doc):
	if cstr(doc.get("status")) != "Closed":
		return

	if _doc_has_field(doc, "resolution_date_issue") and not doc.get("resolution_date_issue"):
		doc.set("resolution_date_issue", today())

	if _doc_has_field(doc, "closing_date") and not doc.get("closing_date"):
		doc.set("closing_date", doc.get("resolution_date_issue") or today())


def _doc_has_field(doc, fieldname):
	return bool(doc.meta.get_field(fieldname))
