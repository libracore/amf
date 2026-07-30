# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.model.db_query import DatabaseQuery
from frappe.utils import cstr, flt


STOCK_FIELDS = (
	"actual_qty",
	"ordered_qty",
	"indented_qty",
	"planned_qty",
	"reserved_qty",
	"reserved_qty_for_production",
	"reserved_qty_for_sub_contract",
	"projected_qty",
)
ON_HAND_WAREHOUSE = "Main Stock - AMF21"


@frappe.whitelist()
def get_item_hover_data(item_code=None):
	"""Return a compact, permission-aware stock snapshot for an Item link preview."""
	item_code = cstr(item_code).strip()
	if not item_code:
		frappe.throw(_("Please select an Item."))

	items = frappe.get_list(
		"Item",
		filters={"name": item_code},
		fields=[
			"name",
			"item_name",
			"item_group",
			"stock_uom",
			"default_bom",
			"is_stock_item",
			"disabled",
		],
		limit_page_length=1,
	)
	if not items:
		return None

	if not items[0].get("is_stock_item"):
		return _build_item_hover_data(items[0])

	stock_access = _can_access_stock_warehouse()
	stock = _get_stock_totals(item_code) if stock_access else {}

	return _build_item_hover_data(items[0], stock, stock_access=stock_access)


def _can_access_stock_warehouse():
	"""Check only the configured stock Warehouse when user restrictions apply."""
	try:
		has_restrictions = DatabaseQuery(
			"Warehouse", user=frappe.session.user
		).build_match_conditions()
		if not has_restrictions:
			return True

		return bool(
			frappe.get_list(
				"Warehouse",
				filters={"name": ON_HAND_WAREHOUSE},
				fields=["name"],
				limit_page_length=1,
			)
		)
	except frappe.PermissionError:
		return False


def _get_stock_totals(item_code):
	rows = frappe.db.sql(
		"""
		select
			sum(actual_qty) as actual_qty,
			sum(ordered_qty) as ordered_qty,
			sum(indented_qty) as indented_qty,
			sum(planned_qty) as planned_qty,
			sum(reserved_qty) as reserved_qty,
			sum(reserved_qty_for_production) as reserved_qty_for_production,
			sum(reserved_qty_for_sub_contract) as reserved_qty_for_sub_contract,
			sum(projected_qty) as projected_qty
		from `tabBin`
		where item_code = %(item_code)s
			and warehouse = %(warehouse)s
		""",
		{
			"item_code": item_code,
			"warehouse": ON_HAND_WAREHOUSE,
		},
		as_dict=True,
	)
	return rows[0] if rows else {}


def _build_item_hover_data(item, stock=None, stock_access=True):
	stock = stock or {}
	quantities = {
		fieldname: flt(stock.get(fieldname))
		for fieldname in STOCK_FIELDS
	}
	total_reserved = (
		quantities["reserved_qty"]
		+ quantities["reserved_qty_for_production"]
		+ quantities["reserved_qty_for_sub_contract"]
	)
	incoming_qty = (
		quantities["ordered_qty"]
		+ quantities["indented_qty"]
		+ quantities["planned_qty"]
	)

	return {
		"amf_item_preview": 1,
		"item_code": item.get("name"),
		"item_name": item.get("item_name") or item.get("name"),
		"item_group": item.get("item_group"),
		"stock_uom": item.get("stock_uom"),
		"default_bom": item.get("default_bom"),
		"is_stock_item": bool(item.get("is_stock_item")),
		"disabled": bool(item.get("disabled")),
		"stock_access": bool(stock_access),
		"actual_qty": quantities["actual_qty"],
		"on_hand_qty": quantities["actual_qty"],
		"on_hand_warehouse": ON_HAND_WAREHOUSE,
		"available_qty": quantities["actual_qty"] - total_reserved,
		"reserved_qty": total_reserved,
		"incoming_qty": incoming_qty,
		"projected_qty": quantities["projected_qty"],
	}
