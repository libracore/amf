# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from collections import OrderedDict

import frappe
from frappe.utils import flt


ITEM_COSTING_TABLE_FIELDNAME = "item_batch_costing"


def normalize_optional_currency(value):
	"""Return `None` for missing values and a rounded currency for numeric values."""
	if value in (None, ""):
		return None

	return flt(value, 2)



def calculate_item_batch_total_cost(machining_cost=None, assembly_cost=None):
	"""Return the combined cost only when at least one source cost exists."""
	cost_values = [
		flt(value)
		for value in (machining_cost, assembly_cost)
		if value not in (None, "")
	]
	if not cost_values:
		return None

	return flt(sum(cost_values), 2)



def get_item_machining_cost_entries(item_code):
	"""Fetch machining-side unit costs per batch from Planning Costing Table."""
	return frappe.db.sql(
		"""
		SELECT
			pct.name AS source_row,
			NULLIF(pct.batch_no, '') AS batch_no,
			pct.cost_per_part AS machining_cost
		FROM `tabPlanning Costing Table` pct
		INNER JOIN `tabPlanning` p ON p.name = pct.parent
		WHERE p.item_code = %(item_code)s
		ORDER BY
			CASE WHEN IFNULL(pct.batch_no, '') = '' THEN 1 ELSE 0 END,
			pct.batch_no ASC,
			p.modified DESC,
			pct.idx ASC
		""",
		{"item_code": item_code},
		as_dict=True,
	)



def get_item_assembly_cost_entries(item_code):
	"""Fetch assembly-side costs per batch from Timer Production Assembly Cost."""
	return frappe.db.sql(
		"""
		SELECT
			tpac.name AS source_row,
			NULLIF(b.name, '') AS batch_no,
			tpac.total_cost AS assembly_cost
		FROM `tabTimer Production Assembly Cost` tpac
		INNER JOIN `tabTimer Production` tp ON tp.name = tpac.parent
		LEFT JOIN `tabBatch` b ON b.work_order = tp.work_order AND b.item = %(item_code)s
		WHERE tp.item_code = %(item_code)s
		ORDER BY
			CASE WHEN IFNULL(b.name, '') = '' THEN 1 ELSE 0 END,
			b.name ASC,
			tp.modified DESC,
			tpac.idx ASC
		""",
		{"item_code": item_code},
		as_dict=True,
	)



def build_item_batch_costing_rows(machining_entries=None, assembly_entries=None):
	"""
	Merge machining and assembly cost sources into one per-batch display table.

	Optimization strategy:
	1. Each source is fetched in a compact SQL query that returns only the fields needed
	   for the table.
	2. We merge the result sets in Python using an `OrderedDict` so we keep deterministic
	   output while avoiding nested loops. The algorithm is O(n).
	3. Real batch numbers are used as the merge key so machining and assembly costs for
	   the same batch end up on the same row.
	4. When a source row has no batch, we keep it under its own synthetic key. That keeps
	   the batch cell empty, as requested, without accidentally merging unrelated rows.
	5. Missing machining or assembly values stay `None`, which leaves the corresponding
	   table cell empty in Frappe.
	"""
	machining_entries = machining_entries or []
	assembly_entries = assembly_entries or []
	rows_by_key = OrderedDict()

	def ensure_row(key, batch_no=None):
		row = rows_by_key.setdefault(
			key,
			{
				"batch_no": batch_no or None,
				"machining_cost": None,
				"assembly_cost": None,
				"total_cost": None,
			},
		)
		if batch_no and not row.get("batch_no"):
			row["batch_no"] = batch_no
		return row

	def merge_entries(entries, row_cost_field):
		for entry in entries:
			batch_no = entry.get("batch_no")
			if batch_no:
				row_key = "batch::{0}".format(batch_no)
			else:
				row_key = "{0}::{1}".format(row_cost_field, entry.get("source_row") or "missing")

			row = ensure_row(row_key, batch_no=batch_no)
			entry_cost = normalize_optional_currency(entry.get(row_cost_field))
			if entry_cost is None:
				continue

			if row.get(row_cost_field) is None:
				row[row_cost_field] = entry_cost
			else:
				# If several source rows point to the same batch, the batch-level view should
				# reflect the sum of those contributing costs.
				row[row_cost_field] = flt(row.get(row_cost_field) + entry_cost, 2)

	merge_entries(machining_entries, "machining_cost")
	merge_entries(assembly_entries, "assembly_cost")

	rows = []
	for row in rows_by_key.values():
		row["total_cost"] = calculate_item_batch_total_cost(
			machining_cost=row.get("machining_cost"),
			assembly_cost=row.get("assembly_cost"),
		)
		rows.append(row)

	return sorted(
		rows,
		key=lambda row: (row.get("batch_no") in (None, ""), row.get("batch_no") or ""),
	)



@frappe.whitelist()
def get_item_batch_costing_rows(item_code=None):
	"""Return the consolidated per-batch costing rows shown on Item."""
	if not item_code:
		return []

	return build_item_batch_costing_rows(
		machining_entries=get_item_machining_cost_entries(item_code),
		assembly_entries=get_item_assembly_cost_entries(item_code),
	)



def populate_item_batch_costing_table(doc, method=None):
	"""Populate the read-only Item child table with the latest per-batch cost view."""
	if not doc.meta.get_field(ITEM_COSTING_TABLE_FIELDNAME):
		return

	doc.set(ITEM_COSTING_TABLE_FIELDNAME, [])
	for row in get_item_batch_costing_rows(item_code=doc.name):
		doc.append(ITEM_COSTING_TABLE_FIELDNAME, row)
