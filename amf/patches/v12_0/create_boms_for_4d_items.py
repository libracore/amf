# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re

import frappe


TARGET_ITEM_PATTERN = re.compile(r"^4D[A-Za-z0-9]{4}$")
SOURCE_ITEM_PATTERN = re.compile(r"^/?42[A-Za-z0-9]{4}$")

TARGET_BODY_ITEM = "5D1000"
TARGET_DRIVER_REFERENCE_PREFIX = "P202O"
SOURCE_DRIVER_REFERENCE_PREFIX = "P201O"


def execute():
	"""Create submitted default BOMs for the six-character 4D Item family."""
	target_items = [
		item for item in _get_target_items()
		if not _get_active_bom(item.name)
	]
	if not target_items:
		return

	_validate_target_body_item()
	creation_plan = []

	# Resolve and validate every template before the first BOM is submitted. This
	# avoids a partial migration when one target has incomplete source data.
	for target_item in target_items:
		source_bom_name = _get_source_bom_name(target_item)
		if not source_bom_name:
			frappe.throw(
				"Could not find an active 42-family BOM to use as the template for {0}.".format(
					target_item.name
				)
			)
		_get_new_bom_items(frappe.get_doc("BOM", source_bom_name))
		creation_plan.append((target_item.name, source_bom_name))

	for target_item_code, source_bom_name in creation_plan:
		_create_bom(target_item_code, source_bom_name)


def _get_target_items():
	items = frappe.get_all(
		"Item",
		filters={"name": ["like", "4D%"]},
		fields=["name", "item_name", "reference_code"],
		order_by="name asc",
	)
	return [item for item in items if TARGET_ITEM_PATTERN.match(item.name or "")]


def _get_source_bom_name(target_item):
	for item_code in _get_source_item_candidates(target_item):
		bom_name = _get_active_bom(item_code)
		if bom_name:
			return bom_name

	# Some legacy 42 Items were renamed or have no BOM. In that case, locate the
	# 42 BOM which uses the same Valve Head referenced by the new 4D Item.
	head_item_code = _get_referenced_head_item_code(target_item.get("reference_code"))
	if not head_item_code:
		return None

	rows = frappe.db.sql(
		"""
			SELECT DISTINCT bom.name
			FROM `tabBOM` AS bom
			INNER JOIN `tabBOM Item` AS bom_item
				ON bom_item.parent = bom.name
			WHERE bom.docstatus = 1
				AND bom.is_active = 1
				AND (
					(CHAR_LENGTH(bom.item) = 6 AND bom.item LIKE '42%%')
					OR (CHAR_LENGTH(bom.item) = 7 AND bom.item LIKE '/42%%')
				)
				AND bom_item.item_code = %s
			ORDER BY bom.is_default DESC, bom.modified DESC, bom.name DESC
			LIMIT 1
		""",
		head_item_code,
		as_dict=True,
	)
	return rows[0].name if rows else None


def _get_source_item_candidates(target_item):
	candidates = []

	item_name = target_item.get("item_name") or ""
	source_item_name = item_name.replace("P202-O/", "P201-O/", 1)
	if source_item_name != item_name:
		for row in frappe.get_all(
			"Item",
			filters={"item_name": source_item_name},
			fields=["name"],
			order_by="name asc",
		):
			_add_source_candidate(candidates, row.name)

	reference_code = target_item.get("reference_code") or ""
	if reference_code.startswith(TARGET_DRIVER_REFERENCE_PREFIX):
		source_reference_code = SOURCE_DRIVER_REFERENCE_PREFIX + reference_code[
			len(TARGET_DRIVER_REFERENCE_PREFIX):
		]
		for row in frappe.get_all(
			"Item",
			filters={"reference_code": source_reference_code},
			fields=["name"],
			order_by="name asc",
		):
			_add_source_candidate(candidates, row.name)

	head_item_code = _get_referenced_head_item_code(reference_code)
	if head_item_code:
		_add_source_candidate(candidates, "420{0}".format(head_item_code[-3:]))

	return candidates


def _add_source_candidate(candidates, item_code):
	if SOURCE_ITEM_PATTERN.match(item_code or "") and item_code not in candidates:
		candidates.append(item_code)


def _get_referenced_head_item_code(reference_code):
	reference_code = reference_code or ""
	if not reference_code.startswith(TARGET_DRIVER_REFERENCE_PREFIX):
		return None

	head_item_code = reference_code[len(TARGET_DRIVER_REFERENCE_PREFIX):][:6]
	return head_item_code if re.match(r"^3[A-Za-z0-9]{5}$", head_item_code) else None


def _get_active_bom(item_code):
	rows = frappe.get_all(
		"BOM",
		filters={
			"item": item_code,
			"docstatus": 1,
			"is_active": 1,
		},
		fields=["name"],
		order_by="is_default desc, modified desc, name desc",
		limit_page_length=1,
	)
	return rows[0].name if rows else None


def _create_bom(target_item_code, source_bom_name):
	source_bom = frappe.get_doc("BOM", source_bom_name)
	items = _get_new_bom_items(source_bom)

	bom = frappe.get_doc({
		"doctype": "BOM",
		"item": target_item_code,
		"quantity": source_bom.quantity or 1,
		"company": source_bom.company,
		"currency": source_bom.currency,
		"conversion_rate": source_bom.conversion_rate or 1,
		"is_active": 1,
		"is_default": 1,
		"with_operations": 0,
		"rm_cost_as_per": source_bom.rm_cost_as_per or "Valuation Rate",
		"buying_price_list": source_bom.buying_price_list,
		"set_rate_of_sub_assembly_item_based_on_bom": (
			source_bom.set_rate_of_sub_assembly_item_based_on_bom
		),
		"items": items,
	})
	_set_collision_safe_name(bom)
	bom.insert(ignore_permissions=True)
	bom.submit()
	return bom.name


def _set_collision_safe_name(bom):
	"""Work around ERPNext v12 BOM names already occupied by suffixed prototype Items."""
	bom.set_new_name()
	if not frappe.db.exists("BOM", bom.name):
		return

	name_prefix = "BOM-{0}-".format(bom.item)
	for index in range(1, 10000):
		candidate = "{0}{1:03d}".format(name_prefix, index)
		if not frappe.db.exists("BOM", candidate):
			bom.name = candidate
			return

	frappe.throw("Could not allocate a unique BOM name for Item {0}.".format(bom.item))


def _get_new_bom_items(source_bom):
	body_rows = [row for row in source_bom.items if _is_42_body_item(row.item_code)]
	if len(body_rows) != 1:
		frappe.throw(
			"Expected exactly one 52-family Body in source BOM {0}, found {1}.".format(
				source_bom.name, len(body_rows)
			)
		)

	body_row_name = body_rows[0].name
	items = []
	for row in source_bom.items:
		is_body = row.name == body_row_name
		items.append({
			"item_code": TARGET_BODY_ITEM if is_body else row.item_code,
			"qty": row.qty,
			"uom": row.uom,
			"conversion_factor": row.conversion_factor,
			"bom_no": None if is_body else row.bom_no,
			"include_item_in_manufacturing": row.include_item_in_manufacturing,
		})

	return items


def _is_42_body_item(item_code):
	item_code = item_code or ""
	return len(item_code) == 6 and item_code.startswith("52")


def _validate_target_body_item():
	values = frappe.db.get_value(
		"Item",
		TARGET_BODY_ITEM,
		["item_group", "disabled"],
		as_dict=True,
	)
	if not values or values.disabled or values.item_group != "Body":
		frappe.throw(
			"Target Body Item {0} is missing, disabled, or not in the Body Item Group.".format(
				TARGET_BODY_ITEM
			)
		)
