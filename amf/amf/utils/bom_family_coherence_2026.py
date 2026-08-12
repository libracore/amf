from __future__ import unicode_literals

import frappe
from frappe.utils import cint, flt, now

from erpnext.manufacturing.doctype.bom.bom import get_boms_in_bottom_up_order


TARGET_ITEM_LIKE = ("4B%", "4C%")
TARGET_ITEM_LENGTH = 6
DISABLED_COMPONENT = "RVM.1204-HV"
REPLACEMENT_COMPONENT = "700030"
INHERITED_COMPONENT = "SPL.3027"
ASSEMBLY_ITEM = "5C0000"
CHILD_ASSEMBLY_ITEM = "5A0000"


def repair_bom_family_coherence(dry_run=True, commit=True):
	"""Repair the shared 4C assembly BOM and stale disabled links in 4B/4C BOMs.

	Dry-run executes the same writes and validations inside the current transaction,
	then rolls them back. This makes the preview exercise ERPNext's BOM controllers.
	"""
	dry_run = cint(dry_run)
	commit = cint(commit)

	try:
		before = audit_bom_family()
		_validate_audit_scope(before)

		changed_assembly = _repair_shared_assembly()
		repaired_child_bom_links = _repair_invalid_child_bom_links()
		removed_links = _remove_stale_disabled_links()
		after = audit_bom_family()
		_validate_final_state(after)

		summary = {
			"dry_run": bool(dry_run),
			"changed_assembly_bom": changed_assembly,
			"repaired_child_bom_links": repaired_child_bom_links,
			"removed_disabled_links": removed_links,
			"before": before,
			"after": after,
		}

		if dry_run or not commit:
			frappe.db.rollback()
		else:
			frappe.db.commit()

		return summary
	except Exception:
		frappe.db.rollback()
		raise


def audit_bom_family():
	target_counts = frappe.db.sql(
		"""
		SELECT
			COUNT(DISTINCT b.item) AS item_count,
			COUNT(*) AS bom_count,
			SUM(b.docstatus = 1 AND b.is_active = 1) AS active_submitted_count,
			SUM(b.docstatus = 1 AND b.is_active = 1 AND b.is_default = 1) AS default_count
		FROM `tabBOM` b
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		""",
		(TARGET_ITEM_LIKE[0], TARGET_ITEM_LIKE[1], TARGET_ITEM_LENGTH),
		as_dict=True,
	)[0]

	enabled_default_counts = frappe.db.sql(
		"""
		SELECT COUNT(*) AS bom_count
		FROM `tabBOM` b
		INNER JOIN `tabItem` finished_item ON finished_item.name = b.item
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		  AND finished_item.disabled = 0
		  AND b.docstatus = 1
		  AND b.is_active = 1
		  AND b.is_default = 1
		""",
		(TARGET_ITEM_LIKE[0], TARGET_ITEM_LIKE[1], TARGET_ITEM_LENGTH),
		as_dict=True,
	)[0]

	disabled_direct_links = _get_disabled_direct_links()
	invalid_child_bom_links = _get_invalid_child_bom_links()
	rvm_direct_rows = _get_rvm_direct_rows()
	rvm_exploded_rows = _get_rvm_exploded_rows()
	rvm_scrap_rows = _get_rvm_scrap_rows()

	assembly_bom = _get_active_default_bom(ASSEMBLY_ITEM)
	assembly_special_rows = frappe.db.sql(
		"""
		SELECT name, idx, item_code, qty, stock_qty, conversion_factor, bom_no
		FROM `tabBOM Item`
		WHERE parent = %s
		  AND item_code IN (%s, %s, %s)
		ORDER BY idx
		""",
		(assembly_bom, CHILD_ASSEMBLY_ITEM, REPLACEMENT_COMPONENT, INHERITED_COMPONENT),
		as_dict=True,
	)

	default_special_quantities = frappe.db.sql(
		"""
		SELECT
			b.item,
			b.name,
			SUM(CASE WHEN exploded.item_code = %s THEN exploded.stock_qty ELSE 0 END) AS replacement_qty,
			SUM(CASE WHEN exploded.item_code = %s THEN exploded.stock_qty ELSE 0 END) AS inherited_qty,
			SUM(CASE WHEN exploded.item_code = %s THEN exploded.stock_qty ELSE 0 END) AS disabled_qty
		FROM `tabBOM` b
		INNER JOIN `tabItem` finished_item ON finished_item.name = b.item
		LEFT JOIN `tabBOM Explosion Item` exploded ON exploded.parent = b.name
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		  AND finished_item.disabled = 0
		  AND b.docstatus = 1
		  AND b.is_active = 1
		  AND b.is_default = 1
		GROUP BY b.item, b.name
		ORDER BY b.item
		""",
		(
			REPLACEMENT_COMPONENT,
			INHERITED_COMPONENT,
			DISABLED_COMPONENT,
			TARGET_ITEM_LIKE[0],
			TARGET_ITEM_LIKE[1],
			TARGET_ITEM_LENGTH,
		),
		as_dict=True,
	)

	bad_default_quantities = [
		row
		for row in default_special_quantities
		if abs(flt(row.replacement_qty) - 2) > 0.000001
		or abs(flt(row.inherited_qty) - 2) > 0.000001
		or abs(flt(row.disabled_qty)) > 0.000001
	]

	return {
		"target_counts": target_counts,
		"enabled_default_count": cint(enabled_default_counts.bom_count),
		"assembly_bom": assembly_bom,
		"assembly_special_rows": assembly_special_rows,
		"disabled_direct_links": disabled_direct_links,
		"invalid_child_bom_links": invalid_child_bom_links,
		"rvm_direct_rows": rvm_direct_rows,
		"rvm_exploded_rows": rvm_exploded_rows,
		"rvm_scrap_rows": rvm_scrap_rows,
		"bad_default_quantities": bad_default_quantities,
	}


def _get_active_default_bom(item_code):
	bom_no = frappe.db.get_value("Item", item_code, "default_bom")
	if not bom_no:
		frappe.throw("Item {0} has no default BOM".format(item_code))

	bom = frappe.db.get_value(
		"BOM",
		bom_no,
		["item", "docstatus", "is_active", "is_default"],
		as_dict=True,
	)
	if not bom or bom.item != item_code or bom.docstatus != 1 or not bom.is_active or not bom.is_default:
		frappe.throw("{0} is not the active submitted default BOM for {1}".format(bom_no, item_code))
	return bom_no


def _get_disabled_direct_links():
	return frappe.db.sql(
		"""
		SELECT b.item, b.name AS bom_no, material.name AS row_name, material.idx, material.item_code
		FROM `tabBOM` b
		INNER JOIN `tabItem` finished_item ON finished_item.name = b.item
		INNER JOIN `tabBOM Item` material ON material.parent = b.name
		INNER JOIN `tabItem` component ON component.name = material.item_code
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		  AND finished_item.disabled = 0
		  AND b.docstatus = 1
		  AND b.is_active = 1
		  AND component.disabled = 1
		ORDER BY b.item, b.name, material.idx
		""",
		(TARGET_ITEM_LIKE[0], TARGET_ITEM_LIKE[1], TARGET_ITEM_LENGTH),
		as_dict=True,
	)


def _get_invalid_child_bom_links():
	return frappe.db.sql(
		"""
		SELECT
			b.item,
			b.name AS bom_no,
			material.name AS row_name,
			material.idx,
			material.item_code,
			material.bom_no AS child_bom_no,
			component.default_bom AS expected_bom_no
		FROM `tabBOM` b
		INNER JOIN `tabItem` finished_item ON finished_item.name = b.item
		INNER JOIN `tabBOM Item` material ON material.parent = b.name
		INNER JOIN `tabItem` component ON component.name = material.item_code
		LEFT JOIN `tabBOM` child_bom ON child_bom.name = material.bom_no
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		  AND finished_item.disabled = 0
		  AND b.docstatus = 1
		  AND b.is_active = 1
		  AND IFNULL(material.bom_no, '') != ''
		  AND (
			child_bom.name IS NULL
			OR child_bom.item != material.item_code
			OR child_bom.docstatus != 1
			OR child_bom.is_active != 1
		  )
		ORDER BY b.item, b.name, material.idx
		""",
		(TARGET_ITEM_LIKE[0], TARGET_ITEM_LIKE[1], TARGET_ITEM_LENGTH),
		as_dict=True,
	)


def _get_rvm_direct_rows():
	return frappe.db.sql(
		"""
		SELECT
			b.item,
			b.name AS bom_no,
			material.name AS row_name,
			material.idx,
			material.qty,
			material.stock_qty,
			material.amount,
			material.base_amount
		FROM `tabBOM` b
		INNER JOIN `tabBOM Item` material ON material.parent = b.name
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		  AND material.item_code = %s
		ORDER BY b.item, b.name, material.idx
		""",
		(TARGET_ITEM_LIKE[0], TARGET_ITEM_LIKE[1], TARGET_ITEM_LENGTH, DISABLED_COMPONENT),
		as_dict=True,
	)


def _get_rvm_exploded_rows():
	return frappe.db.sql(
		"""
		SELECT
			b.item,
			b.name AS bom_no,
			exploded.name AS row_name,
			exploded.idx,
			exploded.stock_qty
		FROM `tabBOM` b
		INNER JOIN `tabBOM Explosion Item` exploded ON exploded.parent = b.name
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		  AND exploded.item_code = %s
		ORDER BY b.item, b.name, exploded.idx
		""",
		(TARGET_ITEM_LIKE[0], TARGET_ITEM_LIKE[1], TARGET_ITEM_LENGTH, DISABLED_COMPONENT),
		as_dict=True,
	)


def _get_rvm_scrap_rows():
	return frappe.db.sql(
		"""
		SELECT b.item, b.name AS bom_no, scrap.name AS row_name, scrap.idx, scrap.stock_qty
		FROM `tabBOM` b
		INNER JOIN `tabBOM Scrap Item` scrap ON scrap.parent = b.name
		WHERE (b.item LIKE %s OR b.item LIKE %s)
		  AND LENGTH(b.item) = %s
		  AND scrap.item_code = %s
		ORDER BY b.item, b.name, scrap.idx
		""",
		(TARGET_ITEM_LIKE[0], TARGET_ITEM_LIKE[1], TARGET_ITEM_LENGTH, DISABLED_COMPONENT),
		as_dict=True,
	)


def _validate_audit_scope(audit):
	if audit["rvm_scrap_rows"]:
		frappe.throw("Unexpected {0} scrap rows found".format(DISABLED_COMPONENT))

	direct_boms = set(row.bom_no for row in audit["rvm_direct_rows"])
	exploded_boms = set(row.bom_no for row in audit["rvm_exploded_rows"])
	if direct_boms != exploded_boms:
		frappe.throw("Direct and exploded {0} BOM sets do not match".format(DISABLED_COMPONENT))

	unexpected_disabled = [
		row for row in audit["disabled_direct_links"] if row.item_code != DISABLED_COMPONENT
	]
	if unexpected_disabled:
		frappe.throw("Unexpected disabled components found: {0}".format(unexpected_disabled))

	parents = []
	if direct_boms:
		parents = frappe.db.sql_list(
			"""
			SELECT DISTINCT parent
			FROM `tabBOM Item`
			WHERE bom_no IN %(boms)s
			""",
			{"boms": tuple(direct_boms)},
		)
	if parents:
		frappe.throw("Stale {0} BOMs are referenced by parent BOMs: {1}".format(
			DISABLED_COMPONENT,
			", ".join(sorted(parents)),
		))

	rows_by_item = {}
	for row in audit["assembly_special_rows"]:
		rows_by_item.setdefault(row.item_code, []).append(row)

	replacement_rows = rows_by_item.get(REPLACEMENT_COMPONENT, [])
	inherited_rows = rows_by_item.get(INHERITED_COMPONENT, [])
	child_rows = rows_by_item.get(CHILD_ASSEMBLY_ITEM, [])

	already_repaired = (
		len(replacement_rows) == 1
		and abs(flt(replacement_rows[0].qty) - 2) < 0.000001
		and not inherited_rows
	)
	needs_repair = (
		len(replacement_rows) == 1
		and abs(flt(replacement_rows[0].qty) - 1) < 0.000001
		and len(inherited_rows) == 1
		and abs(flt(inherited_rows[0].qty) - 2) < 0.000001
	)
	if not already_repaired and not needs_repair:
		frappe.throw("Unexpected {0} component layout in {1}".format(
			ASSEMBLY_ITEM,
			audit["assembly_bom"],
		))

	if len(child_rows) != 1 or not child_rows[0].bom_no:
		frappe.throw("{0} must contain one exploded {1} child BOM".format(
			audit["assembly_bom"],
			CHILD_ASSEMBLY_ITEM,
		))
	child_spl_qty = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(stock_qty), 0)
		FROM `tabBOM Explosion Item`
		WHERE parent = %s AND item_code = %s
		""",
		(child_rows[0].bom_no, INHERITED_COMPONENT),
	)[0][0]
	if abs(flt(child_spl_qty) - 2) > 0.000001:
		frappe.throw("{0} does not inherit {1} x2 from {2}".format(
			audit["assembly_bom"],
			INHERITED_COMPONENT,
			child_rows[0].bom_no,
		))


def _repair_shared_assembly():
	bom_no = _get_active_default_bom(ASSEMBLY_ITEM)
	doc = frappe.get_doc("BOM", bom_no)
	replacement_rows = [row for row in doc.items if row.item_code == REPLACEMENT_COMPONENT]
	inherited_rows = [row for row in doc.items if row.item_code == INHERITED_COMPONENT]

	already_repaired = (
		len(replacement_rows) == 1
		and abs(flt(replacement_rows[0].qty) - 2) < 0.000001
		and not inherited_rows
	)
	if not already_repaired:
		if len(replacement_rows) != 1 or abs(flt(replacement_rows[0].qty) - 1) > 0.000001:
			frappe.throw("Expected one {0} x1 row in {1}".format(REPLACEMENT_COMPONENT, bom_no))
		if len(inherited_rows) != 1 or abs(flt(inherited_rows[0].qty) - 2) > 0.000001:
			frappe.throw("Expected one {0} x2 row in {1}".format(INHERITED_COMPONENT, bom_no))

		frappe.db.sql(
			"""
			UPDATE `tabBOM Item`
			SET qty = 2,
				stock_qty = conversion_factor * 2,
				amount = rate * 2,
				base_amount = base_rate * 2,
				qty_consumed_per_unit = (conversion_factor * 2) / %s
			WHERE name = %s
			""",
			(doc.quantity, replacement_rows[0].name),
		)
		frappe.db.sql("DELETE FROM `tabBOM Item` WHERE name = %s", inherited_rows[0].name)
		frappe.db.sql(
			"UPDATE `tabBOM Item` SET idx = idx - 1 WHERE parent = %s AND idx > %s",
			(bom_no, inherited_rows[0].idx),
		)
	else:
		# Complete a previously interrupted submitted-child update, if necessary.
		frappe.db.sql(
			"""
			UPDATE `tabBOM Item`
			SET stock_qty = conversion_factor * qty,
				amount = rate * qty,
				base_amount = base_rate * qty,
				qty_consumed_per_unit = (conversion_factor * qty) / %s
			WHERE name = %s
			""",
			(doc.quantity, replacement_rows[0].name),
		)

	chain = get_boms_in_bottom_up_order(bom_no)
	before_docs = {name: frappe.get_doc("BOM", name) for name in chain}
	before_docs[bom_no] = doc
	for chain_bom in chain:
		_refresh_bom_totals_and_explosion(chain_bom)
		_propagate_bom_unit_cost(chain_bom, chain)

	for chain_bom in chain:
		frappe.clear_document_cache("BOM", chain_bom)
		after = frappe.get_doc("BOM", chain_bom)
		after._doc_before_save = before_docs[chain_bom]
		after.save_version()

	return {
		"bom_no": bom_no,
		"direct_rows_already_repaired": already_repaired,
		"replacement_qty": 2,
		"removed_item_code": INHERITED_COMPONENT,
		"updated_ancestor_boms": chain[1:],
	}


def _repair_invalid_child_bom_links():
	invalid_rows = _get_invalid_child_bom_links()
	affected_boms = sorted(set(row.bom_no for row in invalid_rows))
	if not affected_boms:
		return {
			"affected_boms": [],
			"updated_rows": [],
		}

	parent_refs = frappe.db.sql_list(
		"""
		SELECT DISTINCT parent
		FROM `tabBOM Item`
		WHERE bom_no IN %(affected_boms)s
		""",
		{"affected_boms": tuple(affected_boms)},
	)
	if parent_refs:
		frappe.throw("Corrupted target BOMs are referenced by parent BOMs: {0}".format(
			", ".join(sorted(parent_refs)),
		))

	before_docs = {bom_no: frappe.get_doc("BOM", bom_no) for bom_no in affected_boms}
	material_rows = frappe.db.sql(
		"""
		SELECT
			material.name,
			material.parent,
			material.idx,
			material.item_code,
			material.bom_no,
			component.default_bom,
			default_bom.item AS default_bom_item,
			default_bom.docstatus AS default_bom_docstatus,
			default_bom.is_active AS default_bom_is_active
		FROM `tabBOM Item` material
		INNER JOIN `tabItem` component ON component.name = material.item_code
		LEFT JOIN `tabBOM` default_bom ON default_bom.name = component.default_bom
		WHERE material.parent IN %(affected_boms)s
		ORDER BY material.parent, material.idx
		""",
		{"affected_boms": tuple(affected_boms)},
		as_dict=True,
	)

	updated_rows = []
	for row in material_rows:
		expected_bom_no = None
		if (
			row.default_bom
			and row.default_bom_item == row.item_code
			and cint(row.default_bom_docstatus) == 1
			and cint(row.default_bom_is_active) == 1
		):
			expected_bom_no = row.default_bom

		if (row.bom_no or None) == expected_bom_no:
			continue
		frappe.db.sql(
			"UPDATE `tabBOM Item` SET bom_no = %s WHERE name = %s",
			(expected_bom_no, row.name),
		)
		updated_rows.append({
			"bom_no": row.parent,
			"row": row.idx,
			"item_code": row.item_code,
			"old_child_bom": row.bom_no,
			"new_child_bom": expected_bom_no,
		})

	for bom_no in affected_boms:
		_refresh_bom_totals_and_explosion(bom_no)
		frappe.clear_document_cache("BOM", bom_no)
		after = frappe.get_doc("BOM", bom_no)
		after._doc_before_save = before_docs[bom_no]
		after.save_version()

	return {
		"affected_boms": affected_boms,
		"updated_rows": updated_rows,
	}


def _refresh_bom_totals_and_explosion(bom_no):
	header = frappe.db.get_value(
		"BOM",
		bom_no,
		[
			"operating_cost",
			"base_operating_cost",
			"scrap_material_cost",
			"base_scrap_material_cost",
		],
		as_dict=True,
	)
	item_totals = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(amount), 0), COALESCE(SUM(base_amount), 0)
		FROM `tabBOM Item`
		WHERE parent = %s
		""",
		(bom_no,),
	)[0]
	raw_material_cost = flt(item_totals[0])
	base_raw_material_cost = flt(item_totals[1])
	total_cost = flt(header.operating_cost) + raw_material_cost - flt(header.scrap_material_cost)
	base_total_cost = (
		flt(header.base_operating_cost)
		+ base_raw_material_cost
		- flt(header.base_scrap_material_cost)
	)
	frappe.db.sql(
		"""
		UPDATE `tabBOM`
		SET raw_material_cost = %s,
			base_raw_material_cost = %s,
			total_cost = %s,
			base_total_cost = %s,
			modified = %s,
			modified_by = %s
		WHERE name = %s
		""",
		(
			raw_material_cost,
			base_raw_material_cost,
			total_cost,
			base_total_cost,
			now(),
			frappe.session.user or "Administrator",
			bom_no,
		),
	)
	frappe.clear_document_cache("BOM", bom_no)
	frappe.get_doc("BOM", bom_no).update_exploded_items()


def _propagate_bom_unit_cost(bom_no, parent_boms):
	bom = frappe.db.get_value(
		"BOM",
		bom_no,
		["quantity", "total_cost", "base_total_cost"],
		as_dict=True,
	)
	quantity = flt(bom.quantity) or 1
	unit_cost = flt(bom.total_cost) / quantity
	base_unit_cost = flt(bom.base_total_cost) / quantity
	frappe.db.sql(
		"""
		UPDATE `tabBOM Item`
		SET rate = %(unit_cost)s,
			base_rate = %(base_unit_cost)s,
			amount = stock_qty * %(unit_cost)s,
			base_amount = stock_qty * %(base_unit_cost)s
		WHERE bom_no = %(bom_no)s
		  AND parent IN %(parent_boms)s
		  AND docstatus < 2
		  AND parenttype = 'BOM'
		""",
		{
			"unit_cost": unit_cost,
			"base_unit_cost": base_unit_cost,
			"bom_no": bom_no,
			"parent_boms": tuple(parent_boms),
		},
	)


def _remove_stale_disabled_links():
	removed = []
	for row in _get_rvm_direct_rows():
		before = frappe.get_doc("BOM", row.bom_no)
		header = frappe.db.get_value(
			"BOM",
			row.bom_no,
			[
				"raw_material_cost",
				"base_raw_material_cost",
				"total_cost",
				"base_total_cost",
			],
			as_dict=True,
		)
		exploded_rows = frappe.db.sql(
			"""
			SELECT name, idx
			FROM `tabBOM Explosion Item`
			WHERE parent = %s AND item_code = %s
			""",
			(row.bom_no, DISABLED_COMPONENT),
			as_dict=True,
		)
		if len(exploded_rows) != 1:
			frappe.throw("Expected one exploded {0} row in {1}".format(
				DISABLED_COMPONENT,
				row.bom_no,
			))

		frappe.db.sql("DELETE FROM `tabBOM Item` WHERE name = %s", row.row_name)
		frappe.db.sql(
			"UPDATE `tabBOM Item` SET idx = idx - 1 WHERE parent = %s AND idx > %s",
			(row.bom_no, row.idx),
		)
		frappe.db.sql("DELETE FROM `tabBOM Explosion Item` WHERE name = %s", exploded_rows[0].name)
		frappe.db.sql(
			"UPDATE `tabBOM Explosion Item` SET idx = idx - 1 WHERE parent = %s AND idx > %s",
			(row.bom_no, exploded_rows[0].idx),
		)

		frappe.db.sql(
			"""
			UPDATE `tabBOM`
			SET raw_material_cost = %s,
				base_raw_material_cost = %s,
				total_cost = %s,
				base_total_cost = %s,
				modified = %s,
				modified_by = %s
			WHERE name = %s
			""",
			(
				flt(header.raw_material_cost) - flt(row.amount),
				flt(header.base_raw_material_cost) - flt(row.base_amount),
				flt(header.total_cost) - flt(row.amount),
				flt(header.base_total_cost) - flt(row.base_amount),
				now(),
				frappe.session.user or "Administrator",
				row.bom_no,
			),
		)

		frappe.clear_document_cache("BOM", row.bom_no)
		after = frappe.get_doc("BOM", row.bom_no)
		after._doc_before_save = before
		after.save_version()

		removed.append({
			"item": row.item,
			"bom_no": row.bom_no,
			"direct_row": row.row_name,
			"exploded_row": exploded_rows[0].name,
		})

	return removed


def _validate_final_state(audit):
	if audit["rvm_direct_rows"] or audit["rvm_exploded_rows"] or audit["rvm_scrap_rows"]:
		frappe.throw("{0} links remain after repair".format(DISABLED_COMPONENT))
	if audit["disabled_direct_links"]:
		frappe.throw("Disabled direct components remain after repair")
	if audit["invalid_child_bom_links"]:
		frappe.throw("Invalid child BOM links remain after repair: {0}".format(
			audit["invalid_child_bom_links"],
		))
	if audit["bad_default_quantities"]:
		frappe.throw("Enabled default BOM quantities remain incoherent: {0}".format(
			audit["bad_default_quantities"],
		))

	rows_by_item = {}
	for row in audit["assembly_special_rows"]:
		rows_by_item.setdefault(row.item_code, []).append(row)
	if len(rows_by_item.get(REPLACEMENT_COMPONENT, [])) != 1:
		frappe.throw("Expected one {0} row after repair".format(REPLACEMENT_COMPONENT))
	if abs(flt(rows_by_item[REPLACEMENT_COMPONENT][0].qty) - 2) > 0.000001:
		frappe.throw("{0} quantity is not 2 after repair".format(REPLACEMENT_COMPONENT))
	if rows_by_item.get(INHERITED_COMPONENT):
		frappe.throw("Direct {0} row remains after repair".format(INHERITED_COMPONENT))


def main():
	import json
	import os

	site = os.environ.get("FRAPPE_SITE", "site1.local")
	dry_run = cint(os.environ.get("DRY_RUN", "1"))
	frappe.init(site=site, sites_path="/home/libracore/frappe-bench/sites")
	frappe.connect()
	frappe.set_user("Administrator")
	try:
		result = repair_bom_family_coherence(dry_run=dry_run, commit=True)
		print(json.dumps(result, indent=2, default=str))
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
