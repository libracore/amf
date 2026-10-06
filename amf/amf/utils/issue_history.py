# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.utils import cstr


HISTORY_FIELDS = (
	"name",
	"creation",
	"opening_date",
	"status",
	"subject",
	"issue_type",
	"process_involved",
	"item",
	"serial_no",
	"loan_order",
	"sales_order",
	"delivery_note",
)


@frappe.whitelist()
def get_issue_history(input_selection, party):
	"""Return the issues visible to the user for one customer or supplier."""
	party_doctype = {
		"Customer Issue": "Customer",
		"Supplier Issue": "Supplier",
	}.get(cstr(input_selection).strip())
	if not party_doctype:
		frappe.throw(_("Choose Customer Issue or Supplier Issue to view history."))

	party = cstr(party).strip()
	if not party:
		frappe.throw(_("Select a {0} to view issue history.").format(_(party_doctype)))
	if not frappe.db.exists(party_doctype, party):
		frappe.throw(_("{0} {1} does not exist.").format(_(party_doctype), party))
	if not frappe.has_permission(party_doctype, "read", doc=party):
		frappe.throw(_("You do not have permission to view this {0}.").format(_(party_doctype)), frappe.PermissionError)

	new_issues = _get_party_issues("AMF Issue Test", party_doctype, party)
	legacy_issues = _get_party_issues("Issue", party_doctype, party)
	new_by_name = {row.name: row for row in new_issues}

	for row in new_issues:
		row.doctype = "AMF Issue Test"
		row.legacy_issue = None
		row["items"] = []
	for row in legacy_issues:
		row.doctype = "Issue"
		row["items"] = []
		if row.amf_issue_test in new_by_name:
			new_by_name[row.amf_issue_test].legacy_issue = row.name

	visible_source_names = set(new_by_name)
	rows = new_issues + [
		row for row in legacy_issues if row.amf_issue_test not in visible_source_names
	]
	_add_issue_items(new_issues)
	for row in rows:
		if not row["items"] and row.item:
			row["items"] = [{"item_code": row.item, "quantity": None, "serial_no": None, "batch_no": None}]
		row.date = cstr(row.opening_date or row.creation)[:10]
		row.creation = cstr(row.creation)
		row.pop("customer", None)
		row.pop("customer_issue", None)
		row.pop("supplier", None)
		row.pop("amf_issue_test", None)

	rows.sort(key=lambda row: row.creation, reverse=True)
	return {"party_type": party_doctype, "party": party, "issues": rows, "total": len(rows)}


def _get_party_issues(doctype, party_doctype, party):
	if not frappe.has_permission(doctype, "read"):
		return []

	fields = list(HISTORY_FIELDS)
	if doctype == "Issue":
		fields.append("amf_issue_test")
	if party_doctype == "Customer":
		fields.extend(("customer_issue", "customer"))
		matches = frappe.get_list(
			doctype,
			fields=fields,
			or_filters=[["customer_issue", "=", party], ["customer", "=", party]],
			order_by="creation desc",
		)
		# The visible custom field is authoritative when both customer fields differ.
		return [row for row in matches if (row.customer_issue or row.customer) == party]

	fields.append("supplier")
	return frappe.get_list(
		doctype,
		fields=fields,
		filters={"supplier": party},
		order_by="creation desc",
	)


def _add_issue_items(issues):
	if not issues:
		return

	issues_by_name = {row.name: row for row in issues}
	items = frappe.db.sql(
		"""
		SELECT parent, item_code, item_name, quantity, serial_no, batch_no
		FROM `tabAMF Issue Test Item`
		WHERE parenttype = 'AMF Issue Test'
		  AND parentfield = 'issue_items'
		  AND parent IN %(names)s
		ORDER BY parent, idx
		""",
		{"names": tuple(issues_by_name)},
		as_dict=True,
	)
	for item in items:
		issues_by_name[item.parent]["items"].append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"quantity": item.quantity,
			"serial_no": item.serial_no,
			"batch_no": item.batch_no,
		})
