# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


AUTO_DISABLED_FIELD = "amf_auto_disabled_no_stock"
QTY_PRECISION = 6


def sync_batch_auto_disable_custom_fields():
	"""Install the marker field used to distinguish automatic disables."""
	create_custom_fields(
		{
			"Batch": [
				{
					"fieldname": AUTO_DISABLED_FIELD,
					"fieldtype": "Check",
					"label": "AMF Auto Disabled: No Stock",
					"insert_after": "disabled",
					"read_only": 1,
					"no_copy": 1,
					"print_hide": 1,
					"hidden": 1,
				}
			]
		},
		update=True,
	)


def queue_batch_disabled_state_sync(doc, method=None):
	"""Queue a post-commit sync for the batch touched by a Stock Ledger Entry."""
	batch_no = (doc.get("batch_no") or "").strip()
	if not batch_no:
		return

	frappe.enqueue(
		"amf.amf.utils.batch_auto_disable.sync_batch_disabled_state",
		queue="short",
		timeout=300,
		enqueue_after_commit=True,
		batch_no=batch_no,
	)


@frappe.whitelist()
def sync_batch_disabled_state(batch_no):
	"""
	Disable a batch when no warehouse has positive stock.

	If this automation disabled the batch before, it will re-enable the batch when
	positive stock appears again. Manually disabled batches are left untouched.
	"""
	batch_no = (batch_no or "").strip()
	if not batch_no or not frappe.db.exists("Batch", batch_no):
		return {"status": "skipped", "reason": "missing_batch", "batch_no": batch_no}

	has_marker = _has_auto_disabled_marker()
	fields = ["disabled"]
	if has_marker:
		fields.append(AUTO_DISABLED_FIELD)

	batch = frappe.db.get_value("Batch", batch_no, fields, as_dict=True)
	if not batch:
		return {"status": "skipped", "reason": "missing_batch", "batch_no": batch_no}

	has_positive_stock = _batch_has_positive_stock(batch_no)
	auto_disabled = bool(batch.get(AUTO_DISABLED_FIELD)) if has_marker else False
	disabled = bool(batch.get("disabled"))

	if has_positive_stock:
		if disabled and auto_disabled:
			_set_batch_state(batch_no, disabled=0, auto_disabled=0, has_marker=has_marker)
			return {"status": "enabled", "batch_no": batch_no}

		if not disabled and auto_disabled:
			_set_batch_auto_marker(batch_no, 0)

		return {"status": "unchanged", "batch_no": batch_no}

	if _batch_has_pending_stock_reference(batch_no):
		return {"status": "skipped", "reason": "pending_stock_document", "batch_no": batch_no}

	if not disabled:
		_set_batch_state(batch_no, disabled=1, auto_disabled=1, has_marker=has_marker)
		return {"status": "disabled", "batch_no": batch_no}

	return {"status": "unchanged", "batch_no": batch_no}


@frappe.whitelist()
def sync_all_batch_disabled_states(limit=None):
	"""
	Catch up all Batch disabled states.

	This is intended for the scheduler and for the existing manual button. It keeps
	user-disabled batches disabled unless they carry the AMF auto-disabled marker.
	"""
	limit = int(limit or 0)
	has_marker = _has_auto_disabled_marker()
	enabled = _enable_auto_disabled_batches_with_stock(has_marker=has_marker)
	disabled, skipped_pending = _disable_batches_without_stock(
		has_marker=has_marker,
		limit=limit,
	)

	return {
		"enabled": enabled,
		"disabled": disabled,
		"skipped_pending": skipped_pending,
	}


def _has_auto_disabled_marker():
	try:
		return frappe.db.has_column("Batch", AUTO_DISABLED_FIELD)
	except Exception:
		return False


def _batch_has_positive_stock(batch_no):
	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM `tabStock Ledger Entry`
			WHERE IFNULL(batch_no, '') = %(batch_no)s
			GROUP BY warehouse
			HAVING ROUND(SUM(actual_qty), {precision}) > 0
			LIMIT 1
			""".format(precision=QTY_PRECISION),
			{"batch_no": batch_no},
		)
	)


def _batch_has_pending_stock_reference(batch_no):
	return batch_no in _get_pending_stock_batch_refs([batch_no])


def _enable_auto_disabled_batches_with_stock(has_marker=None):
	if has_marker is None:
		has_marker = _has_auto_disabled_marker()
	if not has_marker:
		return []

	batches = frappe.db.sql(
		"""
		SELECT DISTINCT b.name
		FROM `tabBatch` b
		INNER JOIN (
			SELECT batch_no
			FROM `tabStock Ledger Entry`
			WHERE IFNULL(batch_no, '') != ''
			GROUP BY batch_no, warehouse
			HAVING ROUND(SUM(actual_qty), {precision}) > 0
		) stock ON stock.batch_no = b.name
		WHERE IFNULL(b.disabled, 0) = 1
		  AND IFNULL(b.`{marker}`, 0) = 1
		""".format(precision=QTY_PRECISION, marker=AUTO_DISABLED_FIELD),
		as_dict=True,
	)

	enabled = []
	for row in batches:
		_set_batch_state(row.name, disabled=0, auto_disabled=0, has_marker=has_marker)
		enabled.append(row.name)

	return enabled


def _disable_batches_without_stock(has_marker=None, limit=None):
	if has_marker is None:
		has_marker = _has_auto_disabled_marker()

	limit_clause = ""
	if limit:
		limit_clause = " LIMIT {0}".format(int(limit))

	candidates = frappe.db.sql(
		"""
		SELECT b.name
		FROM `tabBatch` b
		LEFT JOIN (
			SELECT batch_no
			FROM `tabStock Ledger Entry`
			WHERE IFNULL(batch_no, '') != ''
			GROUP BY batch_no, warehouse
			HAVING ROUND(SUM(actual_qty), {precision}) > 0
		) stock ON stock.batch_no = b.name
		WHERE IFNULL(b.disabled, 0) = 0
		  AND stock.batch_no IS NULL
		GROUP BY b.name
		{limit_clause}
		""".format(precision=QTY_PRECISION, limit_clause=limit_clause),
		as_dict=True,
	)
	batch_nos = [row.name for row in candidates]
	pending_refs = _get_pending_stock_batch_refs(batch_nos)

	disabled = []
	for batch_no in batch_nos:
		if batch_no in pending_refs:
			continue

		_set_batch_state(batch_no, disabled=1, auto_disabled=1, has_marker=has_marker)
		disabled.append(batch_no)

	return disabled, sorted(pending_refs)


def _set_batch_state(batch_no, disabled, auto_disabled, has_marker=None):
	values = {"disabled": int(disabled)}
	if has_marker is None:
		has_marker = _has_auto_disabled_marker()
	if has_marker:
		values[AUTO_DISABLED_FIELD] = int(auto_disabled)

	frappe.db.set_value("Batch", batch_no, values, update_modified=False)


def _set_batch_auto_marker(batch_no, auto_disabled):
	if not _has_auto_disabled_marker():
		return
	frappe.db.set_value(
		"Batch",
		batch_no,
		AUTO_DISABLED_FIELD,
		int(auto_disabled),
		update_modified=False,
	)


def _get_pending_stock_batch_refs(batch_nos):
	batch_nos = sorted(set([batch_no for batch_no in (batch_nos or []) if batch_no]))
	if not batch_nos:
		return set()

	pending_refs = set()
	for chunk in _chunks(batch_nos, 500):
		placeholders = ", ".join(["%s"] * len(chunk))
		query = """
			SELECT DISTINCT batch_no
			FROM (
				SELECT sed.batch_no
				FROM `tabStock Entry Detail` sed
				INNER JOIN `tabStock Entry` se ON se.name = sed.parent
				WHERE se.docstatus = 0
				  AND IFNULL(sed.batch_no, '') != ''
				  AND sed.batch_no IN ({placeholders})

				UNION

				SELECT pri.batch_no
				FROM `tabPurchase Receipt Item` pri
				INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
				WHERE pr.docstatus = 0
				  AND IFNULL(pri.batch_no, '') != ''
				  AND pri.batch_no IN ({placeholders})

				UNION

				SELECT dni.batch_no
				FROM `tabDelivery Note Item` dni
				INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
				WHERE dn.docstatus = 0
				  AND IFNULL(dni.batch_no, '') != ''
				  AND dni.batch_no IN ({placeholders})

				UNION

				SELECT sri.batch_no
				FROM `tabStock Reconciliation Item` sri
				INNER JOIN `tabStock Reconciliation` sr ON sr.name = sri.parent
				WHERE sr.docstatus = 0
				  AND IFNULL(sri.batch_no, '') != ''
				  AND sri.batch_no IN ({placeholders})

				UNION

				SELECT sii.batch_no
				FROM `tabSales Invoice Item` sii
				INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
				WHERE si.docstatus = 0
				  AND IFNULL(si.update_stock, 0) = 1
				  AND IFNULL(sii.batch_no, '') != ''
				  AND sii.batch_no IN ({placeholders})

				UNION

				SELECT pii.batch_no
				FROM `tabPurchase Invoice Item` pii
				INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
				WHERE pi.docstatus = 0
				  AND IFNULL(pi.update_stock, 0) = 1
				  AND IFNULL(pii.batch_no, '') != ''
				  AND pii.batch_no IN ({placeholders})
			) pending
		""".format(placeholders=placeholders)
		values = tuple(chunk) * 6
		rows = frappe.db.sql(query, values, as_dict=True)
		pending_refs.update([row.batch_no for row in rows if row.batch_no])

	return pending_refs


def _chunks(values, size):
	for index in range(0, len(values), size):
		yield values[index:index + size]
