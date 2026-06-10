from __future__ import unicode_literals

import os
import sys
from collections import defaultdict

import frappe
from frappe.utils import cint, cstr, flt, now_datetime

from amf.amf.utils.batch_naming import make_internal_production_batch_id


SITE = os.environ.get("SITE", "site1.local")
SITES_PATH = os.environ.get("SITES_PATH", "/home/libracore/frappe-bench/sites")
DEFAULT_ITEM_CODES = ("200071", "200076", "100076", "100071")
ITEM_CODES = DEFAULT_ITEM_CODES


def main():
	global ITEM_CODES

	ITEM_CODES = parse_item_codes([arg for arg in sys.argv[1:] if not arg.startswith("--")])

	dry_run = not (
		os.environ.get("APPLY") == "1"
		or os.environ.get("DRY_RUN") == "0"
		or "--apply" in sys.argv
	)

	frappe.init(site=SITE, sites_path=SITES_PATH)
	frappe.connect()

	try:
		summary = repair_missing_batches(dry_run=dry_run)
		print_summary(summary, dry_run=dry_run)
		if dry_run:
			frappe.db.rollback()
		else:
			frappe.db.commit()
	finally:
		frappe.destroy()


@frappe.whitelist()
def repair_missing_batches_for_items(item_codes=None, dry_run=True, commit=False):
	"""Run the repair from a Frappe context, for example via bench execute."""
	global ITEM_CODES

	ITEM_CODES = parse_item_codes(item_codes)
	dry_run = cint(dry_run)
	commit = cint(commit)

	summary = repair_missing_batches(dry_run=dry_run)
	if dry_run or not commit:
		frappe.db.rollback()
	else:
		frappe.db.commit()

	return summary


def parse_item_codes(item_codes=None):
	if not item_codes:
		return DEFAULT_ITEM_CODES

	if isinstance(item_codes, str):
		item_codes = item_codes.replace(",", " ").split()

	codes = tuple([cstr(code).strip() for code in item_codes if cstr(code).strip()])
	return codes or DEFAULT_ITEM_CODES


def repair_missing_batches(dry_run=True):
	items = get_items()
	validate_items(items)

	root_rows = get_root_incoming_rows()
	all_missing_details = get_missing_stock_entry_details()
	all_missing_sles = get_missing_stock_ledger_entries()

	if not all_missing_details and not all_missing_sles:
		return {
			"items": items,
			"batches": {},
			"root_rows": root_rows,
			"detail_updates": [],
			"sle_updates": [],
			"balances": get_batch_balances(),
			"missing_after": get_missing_counts(),
			"already_clean": True,
		}

	batch_by_item = plan_batches(root_rows)
	validate_sle_coverage(all_missing_sles, batch_by_item)
	validate_batch_replay(batch_by_item)

	batches = {}
	for item_code, root in sorted(batch_by_item.items()):
		if not dry_run and cint(items[item_code].has_batch_no) != 1:
			frappe.db.set_value(
				"Item",
				item_code,
				"has_batch_no",
				1,
				update_modified=False,
			)

		batches[item_code] = get_or_create_batch(item_code, root, dry_run=dry_run)

	detail_updates = []
	for row in all_missing_details:
		batch_no = batches[row.item_code]
		detail_updates.append({
			"name": row.name,
			"parent": row.parent,
			"item_code": row.item_code,
			"batch_no": batch_no,
		})
		if not dry_run:
			frappe.db.set_value(
				"Stock Entry Detail",
				row.name,
				"batch_no",
				batch_no,
				update_modified=False,
			)

	sle_updates = []
	for row in all_missing_sles:
		batch_no = batches[row.item_code]
		sle_updates.append({
			"name": row.name,
			"voucher_no": row.voucher_no,
			"voucher_detail_no": row.voucher_detail_no,
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"actual_qty": flt(row.actual_qty),
			"batch_no": batch_no,
		})
		if not dry_run:
			frappe.db.set_value(
				"Stock Ledger Entry",
				row.name,
				"batch_no",
				batch_no,
				update_modified=False,
			)

	return {
		"items": items,
		"batches": batches,
		"root_rows": root_rows,
		"detail_updates": detail_updates,
		"sle_updates": sle_updates,
		"balances": get_batch_balances(batch_by_item=batches),
		"missing_after": get_missing_counts(batch_by_item=batches, dry_run=dry_run),
		"already_clean": False,
	}


def get_items():
	rows = frappe.db.sql(
		"""
		SELECT name, item_code, item_name, item_group, has_batch_no, is_stock_item, disabled
		FROM tabItem
		WHERE name IN %(items)s OR item_code IN %(items)s
		ORDER BY item_code
		""",
		{"items": ITEM_CODES},
		as_dict=True,
	)
	return {row.item_code: row for row in rows}


def validate_items(items):
	missing = sorted(set(ITEM_CODES) - set(items))
	if missing:
		raise Exception("Missing Item(s): {0}".format(", ".join(missing)))

	not_stock = sorted([code for code, row in items.items() if not cint(row.is_stock_item)])
	if not_stock:
		raise Exception("Not stock Item(s): {0}".format(", ".join(not_stock)))

	disabled = sorted([code for code, row in items.items() if cint(row.disabled)])
	if disabled:
		raise Exception("Disabled Item(s): {0}".format(", ".join(disabled)))


def get_root_incoming_rows():
	rows = frappe.db.sql(
		"""
		SELECT
			sed.name,
			sed.parent,
			se.purpose,
			se.posting_date,
			se.posting_time,
			se.work_order,
			sed.idx,
			sed.item_code,
			sed.qty,
			sed.t_warehouse
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE sed.item_code IN %(items)s
		  AND se.docstatus = 1
		  AND IFNULL(sed.batch_no, '') = ''
		  AND IFNULL(sed.s_warehouse, '') = ''
		  AND IFNULL(sed.t_warehouse, '') != ''
		  AND IFNULL(sed.qty, 0) > 0
		ORDER BY se.posting_date, se.posting_time, sed.parent, sed.idx
		""",
		{"items": ITEM_CODES},
		as_dict=True,
	)
	return rows


def get_missing_stock_entry_details():
	return frappe.db.sql(
		"""
		SELECT
			sed.name,
			sed.parent,
			se.purpose,
			se.posting_date,
			se.posting_time,
			sed.idx,
			sed.item_code,
			sed.qty,
			sed.s_warehouse,
			sed.t_warehouse
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE sed.item_code IN %(items)s
		  AND se.docstatus = 1
		  AND IFNULL(sed.batch_no, '') = ''
		ORDER BY se.posting_date, se.posting_time, sed.parent, sed.idx
		""",
		{"items": ITEM_CODES},
		as_dict=True,
	)


def get_missing_stock_ledger_entries():
	return frappe.db.sql(
		"""
		SELECT
			name,
			item_code,
			posting_date,
			posting_time,
			voucher_type,
			voucher_no,
			voucher_detail_no,
			warehouse,
			actual_qty
		FROM `tabStock Ledger Entry`
		WHERE item_code IN %(items)s
		  AND docstatus = 1
		  AND IFNULL(is_cancelled, 'No') = 'No'
		  AND IFNULL(batch_no, '') = ''
		ORDER BY posting_date, posting_time, creation, name
		""",
		{"items": ITEM_CODES},
		as_dict=True,
	)


def plan_batches(root_rows):
	roots_by_item = defaultdict(list)
	for row in root_rows:
		roots_by_item[row.item_code].append(row)

	planned = {}
	for item_code in ITEM_CODES:
		roots = roots_by_item.get(item_code, [])
		if len(roots) != 1:
			raise Exception(
				"Expected exactly one root incoming Stock Entry row for {0}, found {1}".format(
					item_code,
					len(roots),
				)
			)
		planned[item_code] = roots[0]

	return planned


def validate_sle_coverage(sle_rows, batch_by_item):
	uncovered = [
		row.name
		for row in sle_rows
		if row.voucher_type != "Stock Entry" or row.item_code not in batch_by_item
	]
	if uncovered:
		raise Exception(
			"Missing-batch SLE rows outside the repair plan: {0}".format(
				", ".join(uncovered)
			)
		)


def validate_batch_replay(batch_by_item):
	rows = frappe.db.sql(
		"""
		SELECT
			name,
			item_code,
			warehouse,
			IFNULL(batch_no, '') AS batch_no,
			actual_qty,
			posting_date,
			posting_time
		FROM `tabStock Ledger Entry`
		WHERE item_code IN %(items)s
		  AND docstatus = 1
		  AND IFNULL(is_cancelled, 'No') = 'No'
		ORDER BY posting_date, posting_time, creation, name
		""",
		{"items": ITEM_CODES},
		as_dict=True,
	)

	balances = defaultdict(float)
	negative = []
	for row in rows:
		batch_no = cstr(row.batch_no).strip() or "planned::{0}".format(row.item_code)
		if row.item_code not in batch_by_item:
			continue
		key = (batch_no, row.warehouse)
		balances[key] += flt(row.actual_qty)
		if balances[key] < -0.00001:
			negative.append((row.name, row.item_code, row.warehouse, balances[key]))

	if negative:
		raise Exception("Planned batch assignment creates negative stock: {0}".format(negative))


def get_or_create_batch(item_code, root, dry_run=True):
	existing = frappe.db.get_value(
		"Batch",
		{
			"item": item_code,
			"reference_doctype": "Stock Entry",
			"reference_name": root.parent,
		},
		"name",
	)
	if existing:
		return existing

	if dry_run:
		return "DRY-RUN-BATCH-{0}".format(item_code)

	batch_id = make_internal_production_batch_id()
	batch = frappe.get_doc(
		{
			"doctype": "Batch",
			"item": item_code,
			"batch_id": batch_id,
			"manufacturing_date": root.posting_date,
			"reference_doctype": "Stock Entry",
			"reference_name": root.parent,
			"description": (
				"Retroactive batch repair for {item}; created {now} from "
				"{stock_entry} row {row_name}."
			).format(
				item=item_code,
				now=now_datetime(),
				stock_entry=root.parent,
				row_name=root.name,
			),
		}
	).insert(ignore_permissions=True)
	return batch.name


def get_batch_balances(batch_by_item=None):
	if not batch_by_item:
		return frappe.db.sql(
			"""
			SELECT sle.item_code, sle.batch_no, sle.warehouse, SUM(sle.actual_qty) AS qty
			FROM `tabStock Ledger Entry` sle
			WHERE sle.item_code IN %(items)s
			  AND sle.docstatus = 1
			  AND IFNULL(sle.is_cancelled, 'No') = 'No'
			  AND IFNULL(sle.batch_no, '') != ''
			GROUP BY sle.item_code, sle.batch_no, sle.warehouse
			HAVING ABS(qty) > 0.00001
			ORDER BY sle.item_code, sle.batch_no, sle.warehouse
			""",
			{"items": ITEM_CODES},
			as_dict=True,
		)

	rows = frappe.db.sql(
		"""
		SELECT item_code, warehouse, actual_qty
		FROM `tabStock Ledger Entry`
		WHERE item_code IN %(items)s
		  AND docstatus = 1
		  AND IFNULL(is_cancelled, 'No') = 'No'
		ORDER BY posting_date, posting_time, creation, name
		""",
		{"items": ITEM_CODES},
		as_dict=True,
	)
	balances = defaultdict(float)
	for row in rows:
		batch_no = batch_by_item.get(row.item_code)
		if not batch_no:
			continue
		balances[(row.item_code, batch_no, row.warehouse)] += flt(row.actual_qty)

	return [
		{
			"item_code": item_code,
			"batch_no": batch_no,
			"warehouse": warehouse,
			"qty": qty,
		}
		for (item_code, batch_no, warehouse), qty in sorted(balances.items())
		if abs(qty) > 0.00001
	]


def get_missing_counts(batch_by_item=None, dry_run=False):
	if dry_run:
		return {
			"items_with_has_batch_no_0": 0,
			"stock_entry_details_missing_batch": 0,
			"stock_ledger_entries_missing_batch": 0,
		}

	return {
		"items_with_has_batch_no_0": frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM tabItem
			WHERE item_code IN %(items)s AND IFNULL(has_batch_no, 0) = 0
			""",
			{"items": ITEM_CODES},
		)[0][0],
		"stock_entry_details_missing_batch": frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE sed.item_code IN %(items)s
			  AND se.docstatus = 1
			  AND IFNULL(sed.batch_no, '') = ''
			""",
			{"items": ITEM_CODES},
		)[0][0],
		"stock_ledger_entries_missing_batch": frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM `tabStock Ledger Entry`
			WHERE item_code IN %(items)s
			  AND docstatus = 1
			  AND IFNULL(is_cancelled, 'No') = 'No'
			  AND IFNULL(batch_no, '') = ''
			""",
			{"items": ITEM_CODES},
		)[0][0],
	}


def print_summary(summary, dry_run=True):
	mode = "DRY RUN" if dry_run else "APPLIED"
	print("{0}: retroactive batch repair for {1}".format(mode, ", ".join(ITEM_CODES)))

	if summary.get("already_clean"):
		print("Nothing to update; affected items already have complete batch assignments.")
		return

	print("")
	print("Items:")
	for item_code in ITEM_CODES:
		item = summary["items"][item_code]
		print(
			"  - {0}: {1}, has_batch_no={2}".format(
				item_code,
				item.item_name,
				item.has_batch_no,
			)
		)

	print("")
	print("Root incoming rows:")
	for row in summary["root_rows"]:
		print(
			"  - {0}: {1} row {2}, qty {3}, target {4}, WO {5}".format(
				row.item_code,
				row.parent,
				row.name,
				flt(row.qty),
				row.t_warehouse,
				row.work_order or "",
			)
		)

	print("")
	print("Batches:")
	for item_code, batch_no in sorted(summary["batches"].items()):
		print("  - {0}: {1}".format(item_code, batch_no))

	print("")
	print("Updates:")
	print("  - Stock Entry Detail rows: {0}".format(len(summary["detail_updates"])))
	print("  - Stock Ledger Entry rows: {0}".format(len(summary["sle_updates"])))

	print("")
	print("Non-zero batch balances after repair:")
	for row in summary["balances"]:
		print(
			"  - {0} / {1} / {2}: {3}".format(
				row["item_code"],
				row["batch_no"],
				row["warehouse"],
				flt(row["qty"]),
			)
		)

	print("")
	print("Missing after repair:")
	for key, value in sorted(summary["missing_after"].items()):
		print("  - {0}: {1}".format(key, value))


if __name__ == "__main__":
	try:
		main()
	except Exception as exc:
		try:
			frappe.db.rollback()
		except Exception:
			pass
		print("ERROR: {0}".format(exc))
		sys.exit(1)
