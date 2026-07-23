# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.utils import cint, cstr, now_datetime, strip_html_tags


ALLOWED_ROLES = {
	"Stock User",
	"Stock Manager",
	"Manufacturing User",
	"Manufacturing Manager",
	"Quality Manager",
	"System Manager",
}
VALID_SERIES = {"", "10", "20"}
VALID_DRAWING_STATUSES = {"", "with", "missing"}


@frappe.whitelist()
def get_components(search=None, series=None, drawing_status=None, include_disabled=0):
	"""Return six-digit 10/20 components and their single default drawing."""
	_assert_register_access()

	search = cstr(search).strip()
	series = cstr(series).strip()
	drawing_status = cstr(drawing_status).strip()
	include_disabled = cint(include_disabled)

	if series not in VALID_SERIES:
		series = ""
	if drawing_status not in VALID_DRAWING_STATUSES:
		drawing_status = ""

	series_condition = ""
	if series:
		series_condition = "and tabItem.item_code like %(series_pattern)s"

	rows = frappe.db.sql(
		"""
		select
			tabItem.name as item_code,
			tabItem.item_name,
			tabItem.description,
			tabItem.item_group,
			tabItem.stock_uom,
			ifnull(tabItem.reference_code, '') as reference_code,
			tabItem.disabled,
			default_drawing.name as drawing_row,
			default_drawing.drawing,
			ifnull(default_drawing.reference_code, '') as drawing_reference_code,
			ifnull(default_drawing.version, '') as version,
			ifnull(default_drawing.revision, '') as revision,
			ifnull(default_drawing.is_active, 0) as drawing_is_active
		from tabItem
		left join `tabDrawing Item` default_drawing
			on default_drawing.name = (
				select candidate.name
				from `tabDrawing Item` candidate
				where candidate.parent = tabItem.name
					and candidate.parenttype = 'Item'
					and candidate.parentfield = 'drawing_item'
					and ifnull(candidate.is_default, 0) = 1
				order by candidate.idx asc, candidate.modified desc, candidate.name asc
				limit 1
			)
		where tabItem.docstatus < 2
			and tabItem.item_code regexp '^(10|20)[0-9]{{4}}$'
			and (%(include_disabled)s = 1 or tabItem.disabled = 0)
			and (
				%(search)s = ''
				or tabItem.item_code like %(search_pattern)s
				or tabItem.item_name like %(search_pattern)s
				or ifnull(tabItem.reference_code, '') like %(search_pattern)s
				or tabItem.item_group like %(search_pattern)s
				or ifnull(default_drawing.reference_code, '') like %(search_pattern)s
				or ifnull(default_drawing.drawing, '') like %(search_pattern)s
			)
			{series_condition}
			{match_condition}
		order by tabItem.item_code asc
		""".format(
			series_condition=series_condition,
			match_condition=get_match_cond("Item").replace("%", "%%"),
		),
		{
			"include_disabled": include_disabled,
			"search": search,
			"search_pattern": "%{0}%".format(search),
			"series_pattern": "{0}%".format(series),
		},
		as_dict=True,
	)

	for row in rows:
		row.has_default_drawing = cint(bool(row.drawing_row))
		row.drawing_file_name = _get_file_name(row.drawing)
		row.description = _plain_text(row.description, 180)

	missing_drawings = [row for row in rows if not row.has_default_drawing]
	filtered_rows = rows
	if drawing_status == "with":
		filtered_rows = [row for row in rows if row.has_default_drawing]
	elif drawing_status == "missing":
		filtered_rows = missing_drawings

	return {
		"rows": filtered_rows,
		"missing_drawings": missing_drawings,
		"summary": _get_summary(filtered_rows),
		"generated_at": cstr(now_datetime()),
		"filters": {
			"search": search,
			"series": series,
			"drawing_status": drawing_status,
			"include_disabled": include_disabled,
		},
	}


def _get_summary(rows):
	with_drawing = len([row for row in rows if row.has_default_drawing])
	return {
		"components": len(rows),
		"with_drawing": with_drawing,
		"missing_drawing": len(rows) - with_drawing,
		"series_10": len([row for row in rows if cstr(row.item_code).startswith("10")]),
		"series_20": len([row for row in rows if cstr(row.item_code).startswith("20")]),
		"disabled": len([row for row in rows if cint(row.disabled)]),
	}


def _get_file_name(file_url):
	file_url = cstr(file_url).strip()
	return file_url.rsplit("/", 1)[-1] if file_url else ""


def _plain_text(value, limit):
	text = " ".join(cstr(strip_html_tags(value or "")).split())
	if len(text) > limit:
		return "{0}…".format(text[:limit - 1].rstrip())
	return text


def _assert_register_access():
	if frappe.session.user == "Guest":
		frappe.throw(
			_("Please sign in to use the Component Drawing Register."),
			frappe.PermissionError,
		)
	if frappe.session.user == "Administrator":
		return
	if not ALLOWED_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(
			_("You do not have access to the Component Drawing Register."),
			frappe.PermissionError,
		)
