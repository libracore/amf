# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import defaultdict

import frappe
from frappe.utils import cstr, now_datetime


def _is_truthy(value):
	return cstr(value).strip().lower() in ("1", "true", "yes", "y")


@frappe.whitelist()
def sync_item_suppliers_from_purchase_orders(dry_run=0, item_code=None):
	"""Add missing Item Supplier rows found on non-cancelled Purchase Orders."""
	dry_run = _is_truthy(dry_run)
	required_pairs = _get_purchase_order_supplier_pairs(item_code=item_code)
	existing_rows = _get_existing_supplier_rows(item_code=item_code)
	existing_pairs = {
		(row.parent, row.supplier)
		for row in existing_rows
		if row.supplier
	}
	missing_pairs = find_missing_supplier_pairs(required_pairs, existing_pairs)
	duplicate_pairs = _count_duplicate_pairs(existing_rows)

	result = {
		"dry_run": dry_run,
		"items_checked": len({item for item, _supplier in required_pairs}),
		"purchase_order_pairs": len(required_pairs),
		"existing_pairs": len(existing_pairs),
		"existing_duplicate_pairs": duplicate_pairs,
		"rows_added": len(missing_pairs),
		"items_updated": len({item for item, _supplier in missing_pairs}),
		"changes": [
			{"item_code": item, "supplier": supplier}
			for item, supplier in missing_pairs
		],
	}
	if dry_run or not missing_pairs:
		return result

	next_index = defaultdict(int)
	for row in existing_rows:
		next_index[row.parent] = max(next_index[row.parent], int(row.idx or 0))
	affected_items = set()
	modified_at = now_datetime()

	try:
		for item, supplier in missing_pairs:
			next_index[item] += 1
			child = frappe.get_doc({
				"doctype": "Item Supplier",
				"parent": item,
				"parenttype": "Item",
				"parentfield": "supplier_items",
				"idx": next_index[item],
				"supplier": supplier,
				"supplier_part_no": None,
			})
			child.db_insert()
			affected_items.add(item)

		for item in affected_items:
			frappe.db.set_value(
				"Item",
				item,
				{
					"modified": modified_at,
					"modified_by": frappe.session.user,
				},
				update_modified=False,
			)
			frappe.clear_document_cache("Item", item)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			frappe.get_traceback(),
			"Item Supplier Synchronization Failed",
		)
		raise

	return result


def find_missing_supplier_pairs(required_pairs, existing_pairs):
	"""Return deterministic, de-duplicated Item–Supplier pairs to insert."""
	required = {
		(cstr(item).strip(), cstr(supplier).strip())
		for item, supplier in required_pairs
		if cstr(item).strip() and cstr(supplier).strip()
	}
	existing = {
		(cstr(item).strip(), cstr(supplier).strip())
		for item, supplier in existing_pairs
		if cstr(item).strip() and cstr(supplier).strip()
	}
	return sorted(required - existing, key=lambda pair: (pair[0].lower(), pair[1].lower()))


def _get_purchase_order_supplier_pairs(item_code=None):
	conditions = [
		"po.docstatus < 2",
		"item.is_purchase_item = 1",
		"IFNULL(po.supplier, '') != ''",
	]
	values = []
	if item_code:
		conditions.append("poi.item_code = %s")
		values.append(item_code)

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT poi.item_code, po.supplier
		FROM `tabPurchase Order Item` poi
		INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
		INNER JOIN `tabItem` item ON item.name = poi.item_code
		WHERE {conditions}
		ORDER BY poi.item_code, po.supplier
		""".format(conditions=" AND ".join(conditions)),
		tuple(values),
		as_list=True,
	)
	return [(row[0], row[1]) for row in rows]


def _get_existing_supplier_rows(item_code=None):
	filters = {
		"parenttype": "Item",
		"parentfield": "supplier_items",
	}
	if item_code:
		filters["parent"] = item_code
	return frappe.get_all(
		"Item Supplier",
		filters=filters,
		fields=["parent", "supplier", "supplier_part_no", "idx"],
		order_by="parent, idx",
		limit_page_length=0,
	)


def _count_duplicate_pairs(rows):
	counts = defaultdict(int)
	for row in rows:
		if row.supplier:
			counts[(row.parent, row.supplier)] += 1
	return sum(1 for count in counts.values() if count > 1)
