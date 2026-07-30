from __future__ import unicode_literals

import frappe


ITEM_CODE = "330001"


def execute():
	current_values = frappe.db.get_value(
		"Item",
		ITEM_CODE,
		["has_serial_no", "serial_no_series"],
		as_dict=True,
	)

	if not current_values:
		return

	if not current_values.has_serial_no and not current_values.serial_no_series:
		return

	frappe.db.set_value(
		"Item",
		ITEM_CODE,
		{
			"has_serial_no": 0,
			"serial_no_series": None,
		},
	)
	frappe.clear_document_cache("Item", ITEM_CODE)
	frappe.clear_cache(doctype="Item")
