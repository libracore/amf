from __future__ import unicode_literals

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, now_datetime

from amf.amf.utils.batch_naming import (
	make_internal_production_batch_id,
	make_supplier_receipt_batch_id,
)


TARGET_ITEM_PREFIXES = ("10", "11", "20", "21", "30")
TARGET_ITEM_GROUPS = ("Plug", "Valve Seat", "Valve Head")
RECEIPT_BATCH_ITEM_CODES = ("70E000",)
TARGET_ITEM_CODE_PATTERN = r"^({0})[0-9]{{4}}$".format("|".join(TARGET_ITEM_PREFIXES))
TARGET_ITEM_CODE_RE = re.compile(TARGET_ITEM_CODE_PATTERN)


def apply_batch_tracking_rule(doc, method=None):
	"""Keep AMF machined/spare item codes batch tracked at Item validation time."""
	if not _doc_matches_batch_rule(doc):
		return

	_doc_set(doc, "has_batch_no", 1)
	if is_receipt_batch_item_code(_doc_get(doc, "item_code") or _doc_get(doc, "name")):
		_doc_set(doc, "create_new_batch", 1)


def ensure_default_batch_for_item(doc, method=None):
	"""Create one starter Batch record for matching items that have none."""
	if not _doc_matches_batch_rule(doc):
		return None

	if cint(_doc_get(doc, "disabled")):
		return None

	item_name = _doc_get(doc, "name") or _doc_get(doc, "item_code")
	if not item_name or _get_existing_batch(item_name):
		return None

	return _create_batch_for_item(
		item_name=item_name,
		item_code=_doc_get(doc, "item_code") or item_name,
		reference_doctype="Item",
		reference_name=item_name,
	).name


@frappe.whitelist()
def repair_target_item_batch_setup(
	item_codes=None,
	dry_run=True,
	commit=True,
	include_disabled=False,
):
	"""
	Ensure matching Item masters have batch tracking and one Batch master.

	Examples:
	bench execute amf.amf.utils.item_batch_setup.repair_target_item_batch_setup
	bench execute amf.amf.utils.item_batch_setup.repair_target_item_batch_setup --kwargs "{'dry_run': 0}"
	"""
	dry_run = cint(dry_run)
	commit = cint(commit)
	include_disabled = cint(include_disabled)

	try:
		summary = _repair_target_item_batch_setup(
			item_codes=parse_item_codes(item_codes),
			dry_run=dry_run,
			include_disabled=include_disabled,
		)

		if dry_run or not commit:
			frappe.db.rollback()
		else:
			frappe.db.commit()

		return summary
	except Exception:
		frappe.db.rollback()
		raise


def repair_target_item_batch_setup_for_patch():
	"""Run from patches.txt without an explicit commit in this helper."""
	return _repair_target_item_batch_setup(dry_run=False)


def activate_receipt_batching_for_70e000():
	"""Enable batch tracking and per-receipt Batch creation for item 70E000."""
	return activate_receipt_batching_for_items(RECEIPT_BATCH_ITEM_CODES)


def activate_receipt_batching_for_items(item_codes):
	item_codes = tuple(item_codes or [])
	if not item_codes:
		return {"updated_items": [], "missing_items": [], "skipped_non_stock": []}

	rows = frappe.get_all(
		"Item",
		filters={"name": ["in", item_codes]},
		fields=["name", "item_code", "item_name", "is_stock_item", "has_batch_no", "create_new_batch"],
	)
	rows_by_name = {row.name: row for row in rows}
	missing_items = [item_code for item_code in item_codes if item_code not in rows_by_name]
	skipped_non_stock = []
	updated_items = []

	for item_code in item_codes:
		row = rows_by_name.get(item_code)
		if not row:
			continue

		if not cint(row.is_stock_item):
			skipped_non_stock.append(_receipt_batch_item_summary(row))
			continue

		updated_items.append(_receipt_batch_item_summary(row))
		if not cint(row.has_batch_no) or not cint(row.create_new_batch):
			frappe.db.set_value(
				"Item",
				row.name,
				{
					"has_batch_no": 1,
					"create_new_batch": 1,
				},
				update_modified=False,
			)

	return {
		"updated_items": updated_items,
		"missing_items": missing_items,
		"skipped_non_stock": skipped_non_stock,
	}


@frappe.whitelist()
def repair_70e000_purchase_receipt_batches(dry_run=True, commit=True):
	"""
	Create receipt-specific Batches for submitted Purchase Receipts of item 70E000.

	Examples:
	bench execute amf.amf.utils.item_batch_setup.repair_70e000_purchase_receipt_batches
	bench execute amf.amf.utils.item_batch_setup.repair_70e000_purchase_receipt_batches --kwargs "{'dry_run': 0}"
	"""
	dry_run = cint(dry_run)
	commit = cint(commit)

	try:
		summary = retrofit_purchase_receipt_batches_for_item(
			item_code="70E000",
			dry_run=dry_run,
		)

		if dry_run or not commit:
			frappe.db.rollback()
		else:
			frappe.db.commit()

		return summary
	except Exception:
		frappe.db.rollback()
		raise


def repair_70e000_purchase_receipt_batches_for_patch():
	"""Run from patches.txt without an explicit commit in this helper."""
	return retrofit_purchase_receipt_batches_for_item(
		item_code="70E000",
		dry_run=False,
	)


def retrofit_purchase_receipt_batches_for_item(item_code, dry_run=True):
	item_code = cstr(item_code).strip()
	item = _get_receipt_batch_item(item_code)
	if not item:
		frappe.throw(_("Missing Item: {0}").format(item_code))
	if not cint(item.is_stock_item):
		frappe.throw(_("Item {0} is not a stock item.").format(item_code))
	if cint(item.disabled):
		frappe.throw(_("Item {0} is disabled.").format(item_code))

	if not dry_run:
		activate_receipt_batching_for_items((item_code,))

	receipt_rows = get_purchase_receipt_rows_missing_batches(item_code)
	detail_names = [row.name for row in receipt_rows]
	sle_by_detail = _get_purchase_receipt_sles_by_detail(item_code, detail_names)
	missing_sle_rows = [
		_purchase_receipt_row_summary(row)
		for row in receipt_rows
		if row.name not in sle_by_detail
	]
	if missing_sle_rows:
		frappe.throw(
			_("Cannot repair 70E000 Purchase Receipt batches because some submitted rows have no Stock Ledger Entry: {0}").format(
				", ".join([row["name"] for row in missing_sle_rows])
			)
		)

	batch_by_receipt = {}
	created_batches = []
	reused_batches = []
	detail_updates = []
	sle_updates = []

	for row in receipt_rows:
		sle_rows = sle_by_detail.get(row.name, [])
		existing_sle_batches = sorted(set([
			cstr(sle.batch_no).strip()
			for sle in sle_rows
			if cstr(sle.batch_no).strip()
		]))
		if len(existing_sle_batches) > 1:
			frappe.throw(
				_("Purchase Receipt row {0} has multiple Stock Ledger Entry batches: {1}").format(
					row.name,
					", ".join(existing_sle_batches),
				)
			)

		if existing_sle_batches:
			batch_no = existing_sle_batches[0]
		else:
			batch_no = batch_by_receipt.get(row.parent)
			if not batch_no:
				batch_no, created = _get_or_create_purchase_receipt_batch(
					item_code=item_code,
					row=row,
					dry_run=dry_run,
				)
				batch_by_receipt[row.parent] = batch_no
				if created:
					created_batches.append(_batch_summary(row, batch_no))
				else:
					reused_batches.append(_batch_summary(row, batch_no))

		detail_updates.append({
			"name": row.name,
			"parent": row.parent,
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"qty": float(row.qty or 0),
			"batch_no": batch_no,
		})
		if not dry_run:
			frappe.db.set_value(
				"Purchase Receipt Item",
				row.name,
				"batch_no",
				batch_no,
				update_modified=False,
			)

		for sle in sle_rows:
			if cstr(sle.batch_no).strip() == batch_no:
				continue

			sle_updates.append({
				"name": sle.name,
				"voucher_no": sle.voucher_no,
				"voucher_detail_no": sle.voucher_detail_no,
				"item_code": sle.item_code,
				"warehouse": sle.warehouse,
				"actual_qty": float(sle.actual_qty or 0),
				"batch_no": batch_no,
			})
			if not dry_run:
				frappe.db.set_value(
					"Stock Ledger Entry",
					sle.name,
					"batch_no",
					batch_no,
					update_modified=False,
				)

	return {
		"dry_run": bool(dry_run),
		"item_code": item_code,
		"item_name": item.item_name,
		"receipt_rows_missing_batch": len(receipt_rows),
		"created_or_planned_batches": created_batches,
		"reused_batches": reused_batches,
		"detail_updates": detail_updates,
		"sle_updates": sle_updates,
		"missing_after": get_70e000_purchase_receipt_batch_missing_counts(item_code=item_code, dry_run=dry_run),
	}


def get_purchase_receipt_rows_missing_batches(item_code):
	select_supplier_batch = "'' AS supplier_batch"
	if frappe.get_meta("Purchase Receipt Item").get_field("supplier_batch"):
		select_supplier_batch = "IFNULL(pri.supplier_batch, '') AS supplier_batch"

	return frappe.db.sql(
		"""
		SELECT
			pri.name,
			pri.parent,
			pri.idx,
			pri.item_code,
			pri.item_name,
			pri.qty,
			pri.warehouse,
			IFNULL(pri.batch_no, '') AS batch_no,
			{select_supplier_batch},
			pr.posting_date,
			pr.posting_time,
			pr.supplier,
			IFNULL(pr.is_return, 0) AS is_return
		FROM `tabPurchase Receipt Item` pri
		INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.item_code = %(item_code)s
		  AND pr.docstatus = 1
		  AND IFNULL(pr.is_return, 0) = 0
		  AND IFNULL(pri.batch_no, '') = ''
		  AND IFNULL(pri.warehouse, '') != ''
		ORDER BY pr.posting_date, pr.posting_time, pri.parent, pri.idx
		""".format(select_supplier_batch=select_supplier_batch),
		{"item_code": item_code},
		as_dict=True,
	)


def get_70e000_purchase_receipt_batch_missing_counts(item_code="70E000", dry_run=False):
	if dry_run:
		return {
			"purchase_receipt_items_missing_batch": 0,
			"stock_ledger_entries_missing_batch": 0,
		}

	return {
		"purchase_receipt_items_missing_batch": frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.item_code = %(item_code)s
			  AND pr.docstatus = 1
			  AND IFNULL(pr.is_return, 0) = 0
			  AND IFNULL(pri.batch_no, '') = ''
			  AND IFNULL(pri.warehouse, '') != ''
			""",
			{"item_code": item_code},
		)[0][0],
		"stock_ledger_entries_missing_batch": frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM `tabStock Ledger Entry`
			WHERE item_code = %(item_code)s
			  AND voucher_type = 'Purchase Receipt'
			  AND docstatus = 1
			  AND IFNULL(is_cancelled, 'No') = 'No'
			  AND IFNULL(batch_no, '') = ''
			""",
			{"item_code": item_code},
		)[0][0],
	}


def _get_receipt_batch_item(item_code):
	return frappe.db.get_value(
		"Item",
		item_code,
		[
			"name",
			"item_code",
			"item_name",
			"is_stock_item",
			"disabled",
			"has_batch_no",
			"create_new_batch",
		],
		as_dict=True,
	)


def _get_purchase_receipt_sles_by_detail(item_code, detail_names):
	detail_names = tuple([name for name in detail_names if name])
	if not detail_names:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT
			name,
			item_code,
			voucher_no,
			voucher_detail_no,
			warehouse,
			actual_qty,
			IFNULL(batch_no, '') AS batch_no
		FROM `tabStock Ledger Entry`
		WHERE item_code = %(item_code)s
		  AND voucher_type = 'Purchase Receipt'
		  AND docstatus = 1
		  AND IFNULL(is_cancelled, 'No') = 'No'
		  AND voucher_detail_no IN %(detail_names)s
		ORDER BY posting_date, posting_time, creation, name
		""",
		{
			"item_code": item_code,
			"detail_names": detail_names,
		},
		as_dict=True,
	)

	by_detail = {}
	for row in rows:
		by_detail.setdefault(row.voucher_detail_no, []).append(row)

	return by_detail


def _get_or_create_purchase_receipt_batch(item_code, row, dry_run=True):
	existing = frappe.db.get_value(
		"Batch",
		{
			"item": item_code,
			"reference_doctype": "Purchase Receipt",
			"reference_name": row.parent,
		},
		"name",
	)
	if existing:
		return existing, False

	if dry_run:
		return "DRY-RUN-BATCH-{0}".format(row.parent), True

	batch_values = {
		"doctype": "Batch",
		"item": item_code,
		"batch_id": make_supplier_receipt_batch_id(row.supplier),
		"supplier": row.supplier,
		"reference_doctype": "Purchase Receipt",
		"reference_name": row.parent,
		"description": (
			"Retroactive AMF Purchase Receipt batch for item {item}; created {now} "
			"from {purchase_receipt} row {row_name}."
		).format(
			item=item_code,
			now=now_datetime(),
			purchase_receipt=row.parent,
			row_name=row.name,
		),
	}
	if frappe.get_meta("Batch").get_field("supplier_batch"):
		batch_values["supplier_batch"] = cstr(row.supplier_batch).strip()

	batch = frappe.get_doc(batch_values).insert(ignore_permissions=True)
	return batch.name, True


def _batch_summary(row, batch_no):
	return {
		"purchase_receipt": row.parent,
		"posting_date": row.posting_date,
		"supplier": row.supplier,
		"item_code": row.item_code,
		"warehouse": row.warehouse,
		"batch_no": batch_no,
	}


def _purchase_receipt_row_summary(row):
	return {
		"name": row.name,
		"parent": row.parent,
		"idx": row.idx,
		"item_code": row.item_code,
		"warehouse": row.warehouse,
		"qty": float(row.qty or 0),
	}


def _repair_target_item_batch_setup(item_codes=None, dry_run=True, include_disabled=False):
	items = get_target_item_batch_rows(item_codes=item_codes)
	_validate_requested_items_exist(item_codes, items)

	skipped_disabled = [
		_item_summary(row) for row in items
		if cint(row.disabled) and not include_disabled
	]
	skipped_non_stock = [
		_item_summary(row) for row in items
		if not cint(row.is_stock_item)
	]
	eligible = [
		row for row in items
		if cint(row.is_stock_item) and (include_disabled or not cint(row.disabled))
	]

	items_missing_has_batch_no = [
		row for row in eligible
		if not cint(row.has_batch_no)
	]
	items_missing_batch = [
		row for row in eligible
		if not cint(row.batch_count)
	]

	updated_items = []
	for row in items_missing_has_batch_no:
		updated_items.append(_item_summary(row))
		if not dry_run:
			frappe.db.set_value(
				"Item",
				row.name,
				"has_batch_no",
				1,
				update_modified=False,
			)

	created_batches = []
	for row in items_missing_batch:
		if dry_run:
			created_batches.append({
				"item_code": row.item_code,
				"item_name": row.item_name,
				"batch_no": "DRY-RUN-BATCH-{0}".format(row.item_code),
			})
			continue

		batch = _create_batch_for_item(
			item_name=row.name,
			item_code=row.item_code,
			reference_doctype="Item",
			reference_name=row.name,
		)
		created_batches.append({
			"item_code": row.item_code,
			"item_name": row.item_name,
			"batch_no": batch.name,
		})

	return {
		"dry_run": bool(dry_run),
		"target_pattern": TARGET_ITEM_CODE_PATTERN,
		"target_item_count": len(items),
		"eligible_item_count": len(eligible),
		"skipped_disabled": skipped_disabled,
		"skipped_non_stock": skipped_non_stock,
		"items_missing_has_batch_no": [_item_summary(row) for row in items_missing_has_batch_no],
		"items_missing_batch": [_item_summary(row) for row in items_missing_batch],
		"updated_items": updated_items,
		"created_batches": created_batches,
	}


def get_target_item_batch_rows(item_codes=None):
	conditions = ["item.item_code REGEXP %(target_pattern)s"]
	params = {"target_pattern": TARGET_ITEM_CODE_PATTERN}

	if item_codes:
		conditions.append("item.item_code IN %(item_codes)s")
		params["item_codes"] = tuple(item_codes)

	return frappe.db.sql(
		"""
		SELECT
			item.name,
			item.item_code,
			item.item_name,
			item.is_stock_item,
			item.disabled,
			item.has_batch_no,
			IFNULL(batch_counts.batch_count, 0) AS batch_count
		FROM `tabItem` item
		LEFT JOIN (
			SELECT item, COUNT(*) AS batch_count
			FROM `tabBatch`
			GROUP BY item
		) batch_counts ON batch_counts.item = item.name
		WHERE {conditions}
		ORDER BY item.item_code
		""".format(conditions=" AND ".join(conditions)),
		params,
		as_dict=True,
	)


def parse_item_codes(item_codes=None):
	if not item_codes:
		return None

	if isinstance(item_codes, str):
		item_codes = item_codes.strip()
		if not item_codes:
			return None
		if item_codes[0] == "[":
			item_codes = json.loads(item_codes)
		else:
			item_codes = item_codes.replace(",", " ").split()

	parsed = []
	seen = set()
	for item_code in item_codes:
		item_code = cstr(item_code).strip()
		if not item_code or item_code in seen:
			continue
		if not is_target_item_code(item_code):
			frappe.throw(
				_("Item code {0} is not a 6 digit AMF batch-tracked code starting with {1}.").format(
					frappe.bold(item_code),
					", ".join(TARGET_ITEM_PREFIXES),
				)
			)
		seen.add(item_code)
		parsed.append(item_code)

	return parsed or None


def is_target_item_code(item_code):
	return bool(TARGET_ITEM_CODE_RE.match(cstr(item_code).strip()))


def is_receipt_batch_item_code(item_code):
	return cstr(item_code).strip().upper() in RECEIPT_BATCH_ITEM_CODES


def _validate_requested_items_exist(item_codes, rows):
	if not item_codes:
		return

	found = set([row.item_code for row in rows])
	missing = [item_code for item_code in item_codes if item_code not in found]
	if missing:
		frappe.throw(_("Missing Item(s): {0}").format(", ".join(missing)))


def _doc_matches_batch_rule(doc):
	item_code = _doc_get(doc, "item_code") or _doc_get(doc, "name")
	item_group = cstr(_doc_get(doc, "item_group")).strip()
	return (
		is_target_item_code(item_code)
		or is_receipt_batch_item_code(item_code)
		or item_group in TARGET_ITEM_GROUPS
	) and cint(_doc_get(doc, "is_stock_item"))


def _create_batch_for_item(item_name, item_code=None, reference_doctype=None, reference_name=None):
	batch = frappe.get_doc({
		"doctype": "Batch",
		"item": item_name,
		"batch_id": make_internal_production_batch_id(),
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"description": (
			"AMF automatic starter batch for item {0}; created {1} because "
			"the item code matches {2} and no Batch existed."
		).format(item_code or item_name, now_datetime(), TARGET_ITEM_CODE_PATTERN),
	})
	batch.insert(ignore_permissions=True)
	return batch


def _get_existing_batch(item_name):
	return frappe.db.get_value("Batch", {"item": item_name}, "name")


def _item_summary(row):
	return {
		"item_code": row.item_code,
		"item_name": row.item_name,
		"has_batch_no": cint(row.has_batch_no),
		"batch_count": cint(row.batch_count),
	}


def _receipt_batch_item_summary(row):
	return {
		"item_code": row.item_code,
		"item_name": row.item_name,
		"has_batch_no": cint(row.has_batch_no),
		"create_new_batch": cint(row.create_new_batch),
	}


def _doc_get(doc, fieldname):
	if hasattr(doc, "get"):
		return doc.get(fieldname)
	return getattr(doc, fieldname, None)


def _doc_set(doc, fieldname, value):
	if hasattr(doc, "set"):
		doc.set(fieldname, value)
	else:
		setattr(doc, fieldname, value)
