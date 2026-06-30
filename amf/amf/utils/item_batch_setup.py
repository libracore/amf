from __future__ import unicode_literals

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, now_datetime

from amf.amf.utils.batch_naming import make_internal_production_batch_id


TARGET_ITEM_PREFIXES = ("10", "11", "20", "21", "30")
TARGET_ITEM_CODE_PATTERN = r"^({0})[0-9]{{4}}$".format("|".join(TARGET_ITEM_PREFIXES))
TARGET_ITEM_CODE_RE = re.compile(TARGET_ITEM_CODE_PATTERN)


def apply_batch_tracking_rule(doc, method=None):
	"""Keep AMF machined/spare item codes batch tracked at Item validation time."""
	if not _doc_matches_batch_rule(doc):
		return

	_doc_set(doc, "has_batch_no", 1)


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


def _validate_requested_items_exist(item_codes, rows):
	if not item_codes:
		return

	found = set([row.item_code for row in rows])
	missing = [item_code for item_code in item_codes if item_code not in found]
	if missing:
		frappe.throw(_("Missing Item(s): {0}").format(", ".join(missing)))


def _doc_matches_batch_rule(doc):
	item_code = _doc_get(doc, "item_code") or _doc_get(doc, "name")
	return is_target_item_code(item_code) and cint(_doc_get(doc, "is_stock_item"))


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


def _doc_get(doc, fieldname):
	if hasattr(doc, "get"):
		return doc.get(fieldname)
	return getattr(doc, fieldname, None)


def _doc_set(doc, fieldname, value):
	if hasattr(doc, "set"):
		doc.set(fieldname, value)
	else:
		setattr(doc, fieldname, value)
