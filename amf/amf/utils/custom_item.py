# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, cstr, escape_html


CUSTOM_ITEM_FIELD = "custom_item"
CUSTOM_ITEM_WARNING_SHOWN_FIELD = "custom_item_warning_shown"
PRODUCT_ITEM_GROUP = "Product"
VALVE_HEAD_ITEM_GROUP = "Valve Head"


CUSTOM_ITEM_FIELDS = {
	"Item": [
		{
			"fieldname": CUSTOM_ITEM_FIELD,
			"fieldtype": "Check",
			"label": "Custom Item",
			"insert_after": "is_sales_item",
			"default": "0",
			"in_standard_filter": 1,
			"description": (
				"Marks an item that requires review with the R&D department. "
				"Products are checked automatically when their default BOM contains "
				"a custom Valve Head."
			),
		}
	],
	"Quotation": [
		{
			"fieldname": CUSTOM_ITEM_WARNING_SHOWN_FIELD,
			"fieldtype": "Check",
			"label": "Custom Item Warning Shown",
			"insert_after": "items",
			"default": "0",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"description": "Prevents the R&D warning from repeating when custom items have not changed.",
		}
	],
	"Sales Order": [
		{
			"fieldname": CUSTOM_ITEM_WARNING_SHOWN_FIELD,
			"fieldtype": "Check",
			"label": "Custom Item Warning Shown",
			"insert_after": "items",
			"default": "0",
			"hidden": 1,
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"description": "Prevents the R&D warning from repeating when custom items have not changed.",
		}
	],
}


def sync_custom_item_configuration():
	"""Install the field and propagate existing custom Valve Heads to Products."""
	create_custom_fields(CUSTOM_ITEM_FIELDS, update=True)
	frappe.clear_cache(doctype="Item")
	return sync_all_custom_products()


def sync_products_from_custom_valve_head(doc, method=None):
	"""Check Products whose current default BOM directly contains this custom head."""
	if doc.get("item_group") != VALVE_HEAD_ITEM_GROUP:
		return []
	if not cint(doc.get(CUSTOM_ITEM_FIELD)):
		return []

	return _mark_items_custom(_get_related_unchecked_products(doc.name))


def sync_product_from_bom(doc, method=None):
	"""Check a Product when its submitted, active default BOM has a custom head."""
	if cint(doc.get("docstatus")) != 1:
		return []
	if not cint(doc.get("is_active")) or not cint(doc.get("is_default")):
		return []
	if _get_item_group(doc.get("item")) != PRODUCT_ITEM_GROUP:
		return []
	if not _bom_contains_custom_valve_head(doc.name):
		return []

	return _mark_items_custom([doc.get("item")])


@frappe.whitelist()
def sync_all_custom_products():
	"""Backfill Products related to every currently custom Valve Head."""
	if not frappe.db.has_column("Item", CUSTOM_ITEM_FIELD):
		return {"updated": 0, "skipped": "missing_custom_item_field"}

	products = frappe.db.sql(
		"""
		SELECT DISTINCT product.name
		FROM `tabBOM` bom
		INNER JOIN `tabItem` product
			ON product.name = bom.item
			AND product.item_group = %(product_group)s
		INNER JOIN `tabBOM Item` bom_item
			ON bom_item.parent = bom.name
		INNER JOIN `tabItem` head
			ON head.name = bom_item.item_code
			AND head.item_group = %(valve_head_group)s
			AND IFNULL(head.custom_item, 0) = 1
		WHERE
			bom.docstatus = 1
			AND bom.is_active = 1
			AND bom.is_default = 1
			AND IFNULL(product.custom_item, 0) = 0
		""",
		{
			"product_group": PRODUCT_ITEM_GROUP,
			"valve_head_group": VALVE_HEAD_ITEM_GROUP,
		},
	)
	updated = _mark_items_custom([row[0] for row in products])
	return {"updated": len(updated), "items": updated}


def warn_custom_items_on_save(doc, method=None):
	"""Show the R&D popup once per unchanged set of custom items during draft save."""
	custom_items = _get_custom_items(doc.get("items"))
	if not custom_items:
		doc.set(CUSTOM_ITEM_WARNING_SHOWN_FIELD, 0)
		return []

	custom_item_codes = {item["item_code"] for item in custom_items}
	previous_doc = doc.get_doc_before_save()
	previous_custom_item_codes = set()
	if previous_doc:
		previous_custom_item_codes = {
			item["item_code"] for item in _get_custom_items(previous_doc.get("items"))
		}

	custom_items_changed = bool(previous_doc) and (
		custom_item_codes != previous_custom_item_codes
	)
	if cint(doc.get(CUSTOM_ITEM_WARNING_SHOWN_FIELD)) and not custom_items_changed:
		return []

	doc.set(CUSTOM_ITEM_WARNING_SHOWN_FIELD, 1)

	item_list = "".join(
		"<li><strong>{0}</strong>{1}</li>".format(
			escape_html(item["item_code"]),
			" &mdash; {0}".format(escape_html(item["item_name"]))
			if item["item_name"] and item["item_name"] != item["item_code"]
			else "",
		)
		for item in custom_items
	)
	frappe.msgprint(
		_(
			"The following custom item(s) require review with the R&D department:"
			"<ul>{0}</ul>Please confirm the configuration with R&D."
		).format(item_list),
		title=_("R&D Review Required"),
		indicator="orange",
	)
	return [item["item_code"] for item in custom_items]


def _get_related_unchecked_products(valve_head):
	rows = frappe.db.sql(
		"""
		SELECT DISTINCT product.name
		FROM `tabBOM` bom
		INNER JOIN `tabItem` product
			ON product.name = bom.item
			AND product.item_group = %(product_group)s
		INNER JOIN `tabBOM Item` bom_item
			ON bom_item.parent = bom.name
		WHERE
			bom.docstatus = 1
			AND bom.is_active = 1
			AND bom.is_default = 1
			AND bom_item.item_code = %(valve_head)s
			AND IFNULL(product.custom_item, 0) = 0
		""",
		{"product_group": PRODUCT_ITEM_GROUP, "valve_head": valve_head},
	)
	return [row[0] for row in rows]


def _get_item_group(item_code):
	return frappe.db.get_value("Item", item_code, "item_group")


def _bom_contains_custom_valve_head(bom_name):
	return bool(
		frappe.db.sql(
			"""
			SELECT bom_item.name
			FROM `tabBOM Item` bom_item
			INNER JOIN `tabItem` head
				ON head.name = bom_item.item_code
			WHERE
				bom_item.parent = %(bom_name)s
				AND head.item_group = %(valve_head_group)s
				AND IFNULL(head.custom_item, 0) = 1
			LIMIT 1
			""",
			{"bom_name": bom_name, "valve_head_group": VALVE_HEAD_ITEM_GROUP},
		)
	)


def _mark_items_custom(item_codes):
	updated = []
	for item_code in dict.fromkeys(item_codes or []):
		if not item_code:
			continue
		if cint(frappe.db.get_value("Item", item_code, CUSTOM_ITEM_FIELD)):
			continue

		frappe.db.set_value("Item", item_code, CUSTOM_ITEM_FIELD, 1)
		updated.append(item_code)

	return updated


def _get_custom_items(rows):
	item_codes = []
	for row in rows or []:
		item_code = cstr(row.get("item_code")).strip()
		if item_code and item_code not in item_codes:
			item_codes.append(item_code)

	if not item_codes:
		return []

	items = frappe.get_all(
		"Item",
		filters={
			"name": ["in", item_codes],
			CUSTOM_ITEM_FIELD: 1,
		},
		fields=["name", "item_name"],
	)
	items_by_code = {item.name: item for item in items}
	return [
		{
			"item_code": item_code,
			"item_name": cstr(items_by_code[item_code].item_name),
		}
		for item_code in item_codes
		if item_code in items_by_code
	]
