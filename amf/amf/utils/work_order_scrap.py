# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt


USAGE_JSON_FIELD = "amf_raw_material_usage_json"
DYNAMIC_SCRAP_FIELD = "amf_dynamic_usage_scrap"
DEFAULT_SOURCE_WAREHOUSE = "Main Stock - AMF21"
DEFAULT_SCRAP_WAREHOUSE = "Scrap - AMF21"


def sync_work_order_usage_scrap_custom_fields():
	"""Install hidden fields used by the manual Stock Entry usage review flow."""
	create_custom_fields(
		{
			"Stock Entry": [
				{
					"fieldname": "amf_usage_scrap_section",
					"fieldtype": "Section Break",
					"label": "AMF Usage Scrap",
					"insert_after": "remarks",
					"hidden": 1,
					"no_copy": 1,
					"print_hide": 1,
				},
				{
					"fieldname": USAGE_JSON_FIELD,
					"fieldtype": "Code",
					"label": "AMF Raw Material Usage JSON",
					"insert_after": "amf_usage_scrap_section",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"allow_on_submit": 1,
					"ignore_xss_filter": 1,
				},
			],
			"Stock Entry Detail": [
				{
					"fieldname": DYNAMIC_SCRAP_FIELD,
					"fieldtype": "Check",
					"label": "AMF Dynamic Usage Scrap",
					"insert_after": "t_warehouse",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"allow_on_submit": 1,
				},
			],
		},
		update=True,
	)


def prepare_dynamic_usage_scrap_rows(doc, method=None):
	"""
	Keep popup-created scrap rows as Main Stock -> Scrap movements inside the
	Manufacture Stock Entry.

	ERPNext v12 Manufacture validation normalizes non-BOM rows to source-only
	material consumption rows. This hook runs after that validation in before_save
	and before_submit, so the dynamic scrap rows keep both warehouses for the
	actual stock ledger movement.
	"""
	if doc.doctype != "Stock Entry" or doc.purpose != "Manufacture":
		return

	if not any(_is_dynamic_usage_scrap_row(row) for row in doc.get("items") or []):
		return

	target_warehouse = _get_scrap_warehouse(doc)

	for row in doc.get("items") or []:
		if not _is_dynamic_usage_scrap_row(row):
			continue

		if not row.item_code:
			frappe.throw(_("Dynamic usage scrap row is missing an Item Code."))

		row.s_warehouse = DEFAULT_SOURCE_WAREHOUSE
		row.t_warehouse = target_warehouse
		row.bom_no = None
		row.qty = flt(row.qty, row.precision("qty"))
		row.conversion_factor = flt(row.conversion_factor) or 1
		row.transfer_qty = flt(
			flt(row.qty) * flt(row.conversion_factor),
			row.precision("transfer_qty"),
		)

		if row.s_warehouse == row.t_warehouse:
			frappe.throw(_("Source and target warehouses cannot be the same for dynamic usage scrap."))


def is_dynamic_usage_scrap_row(row):
	return _is_dynamic_usage_scrap_row(row)


def _is_dynamic_usage_scrap_row(row):
	return cint(row.get(DYNAMIC_SCRAP_FIELD)) == 1


def _get_scrap_warehouse(doc):
	if doc.work_order:
		warehouse = frappe.db.get_value("Work Order", doc.work_order, "scrap_warehouse")
		if warehouse:
			return warehouse

	return DEFAULT_SCRAP_WAREHOUSE
