# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


ADMINISTRATOR_SECTION_FIELD = "administrator_section"
SKIP_OTIF_KPI_FIELD = "skip_otif_kpi"


SALES_ORDER_OTIF_CUSTOM_FIELDS = {
	"Sales Order": [
		{
			"fieldname": ADMINISTRATOR_SECTION_FIELD,
			"fieldtype": "Section Break",
			"label": "Administrator",
			"insert_after": "contact_phone",
			"no_copy": 1,
			"print_hide": 1,
		},
		{
			"fieldname": SKIP_OTIF_KPI_FIELD,
			"fieldtype": "Check",
			"label": "Skip OTIF KPI",
			"insert_after": ADMINISTRATOR_SECTION_FIELD,
			"default": "0",
			"description": "Exclude this Sales Order from On Time Delivery KPI calculations.",
			"allow_on_submit": 1,
			"no_copy": 1,
			"print_hide": 1,
			"in_standard_filter": 1,
		},
	]
}


def sync_sales_order_otif_custom_fields():
	"""Install Sales Order controls used by OTIF KPI reporting."""
	create_custom_fields(SALES_ORDER_OTIF_CUSTOM_FIELDS, update=True)


def get_skip_otif_kpi_condition(table_alias="so"):
	"""Return the SQL condition that excludes Sales Orders marked out of OTIF."""
	if not frappe.db.has_column("Sales Order", SKIP_OTIF_KPI_FIELD):
		return ""

	return "IFNULL({0}.{1}, 0) = 0".format(table_alias, SKIP_OTIF_KPI_FIELD)
