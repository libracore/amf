# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def sync_loan_order_custom_fields():
	"""Create lightweight backlinks from stock documents to Loan Order."""
	create_custom_fields(
		{
			"Stock Entry": [
				{
					"fieldname": "loan_order",
					"fieldtype": "Link",
					"label": "Loan Order",
					"options": "Loan Order",
					"insert_after": "stock_entry_type",
					"allow_on_submit": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "loan_order_movement",
					"fieldtype": "Select",
					"label": "Loan Order Movement",
					"options": "\nOutward\nReturn",
					"insert_after": "loan_order",
					"allow_on_submit": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
				},
			],
			"Stock Entry Detail": [
				{
					"fieldname": "loan_order_item",
					"fieldtype": "Link",
					"label": "Loan Order Item",
					"options": "Loan Order Item",
					"insert_after": "item_code",
					"allow_on_submit": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
				},
			],
			"Delivery Note": [
				{
					"fieldname": "loan_order",
					"fieldtype": "Link",
					"label": "Loan Order",
					"options": "Loan Order",
					"insert_after": "object",
					"allow_on_submit": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"in_standard_filter": 1,
				},
				{
					"fieldname": "loan_order_movement",
					"fieldtype": "Select",
					"label": "Loan Order Movement",
					"options": "\nOutward\nReturn",
					"insert_after": "loan_order",
					"allow_on_submit": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
				},
			],
			"Delivery Note Item": [
				{
					"fieldname": "loan_order_item",
					"fieldtype": "Link",
					"label": "Loan Order Item",
					"options": "Loan Order Item",
					"insert_after": "item_code",
					"allow_on_submit": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
				},
			],
			"Issue": [
				{
					"fieldname": "loan_order",
					"fieldtype": "Link",
					"label": "Loan Order",
					"options": "Loan Order",
					"insert_after": "customer",
					"allow_on_submit": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"in_standard_filter": 1,
				},
			],
		},
		update=True,
	)
