# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
from contextlib import contextmanager

import frappe
from frappe.desk.form.load import run_onload
from frappe.desk.form.save import savedocs as core_savedocs
from frappe.desk.form.save import send_updated_docs, set_local_name
from frappe.utils import cint, cstr, flt
from six import string_types


DELIVERY_NOTE_SAVE_ACTIONS = ("Save", "Update")
DELIVERY_NOTE_BATCH_CHECK_FIELDS = ("item_code", "warehouse", "batch_no", "qty", "stock_qty")
SKIP_BATCH_CHECK_ROWS_FLAG = "amf_skip_delivery_note_batch_check_rows"


@frappe.whitelist(methods=["POST", "PUT"])
def savedocs(doc, action):
	"""
	Save Delivery Notes that reference already-disabled linked records.

	Frappe v12 validates linked documents before Delivery Note hooks run. If a
	draft or submitted Delivery Note already contains a linked document that is now
	disabled, a normal Save/Update fails before the user can change unrelated
	fields. For Delivery Note Save/Update only, temporarily enable unchanged
	disabled links while the core save endpoint runs, then restore their state.
	"""
	payload = _load_doc_payload(doc)

	if _should_save_delivery_note_with_disabled_links(payload, action):
		return _save_delivery_note_doc(payload, action)

	return core_savedocs(doc, action)


def _load_doc_payload(doc):
	if isinstance(doc, string_types):
		return json.loads(doc)

	return doc or {}


def _should_save_delivery_note_with_disabled_links(payload, action):
	return (
		isinstance(payload, dict)
		and payload.get("doctype") == "Delivery Note"
		and cstr(action) in DELIVERY_NOTE_SAVE_ACTIONS
	)


def _save_delivery_note_doc(payload, action):
	_install_delivery_note_batch_check_wrapper()

	try:
		doc = frappe.get_doc(payload)
		set_local_name(doc)

		doc.docstatus = {"Save": 0, "Submit": 1, "Update": 1, "Cancel": 2}[action]
		disabled_links = _get_unchanged_disabled_links(doc)
		_set_delivery_note_batch_check_skip_rows(doc, action, disabled_links.get("Batch"))

		with _temporarily_enable_disabled_links(disabled_links):
			if doc.docstatus == 1:
				doc.submit()
			else:
				try:
					doc.save()
				except frappe.NameError as e:
					doctype, name, original_exception = e if isinstance(e, tuple) else (doc.doctype or "", doc.name or "", None)
					frappe.msgprint(frappe._("{0} {1} already exists").format(doctype, name))
					raise

		run_onload(doc)
		send_updated_docs(doc)
	except Exception:
		frappe.errprint(frappe.utils.get_traceback())
		raise


def _install_delivery_note_batch_check_wrapper():
	import erpnext.stock.doctype.delivery_note.delivery_note as delivery_note_module

	current = delivery_note_module.set_batch_nos
	if getattr(current, "_amf_delivery_note_wrapper", False):
		return

	original_set_batch_nos = current

	def amf_delivery_note_set_batch_nos(doc, warehouse_field, throw=False):
		skip_rows = set(doc.flags.get(SKIP_BATCH_CHECK_ROWS_FLAG) or [])
		if doc.doctype == "Delivery Note" and skip_rows:
			original_items = doc.items
			doc.items = [row for row in original_items if row.name not in skip_rows]
			try:
				return original_set_batch_nos(doc, warehouse_field, throw)
			finally:
				doc.items = original_items

		return original_set_batch_nos(doc, warehouse_field, throw)

	amf_delivery_note_set_batch_nos._amf_delivery_note_wrapper = True
	amf_delivery_note_set_batch_nos._amf_original_set_batch_nos = original_set_batch_nos
	delivery_note_module.set_batch_nos = amf_delivery_note_set_batch_nos


@contextmanager
def _temporarily_enable_disabled_links(disabled_links):
	for doctype, names in disabled_links.items():
		for name in names:
			frappe.db.set_value(doctype, name, "disabled", 0, update_modified=False)

	try:
		yield
	finally:
		for doctype, names in disabled_links.items():
			for name in names:
				frappe.db.set_value(doctype, name, "disabled", 1, update_modified=False)


def _get_unchanged_disabled_links(doc):
	if doc.is_new():
		return {}

	candidates = {}
	_collect_unchanged_disabled_link_candidates(doc, candidates)

	for table_field in doc.meta.get_table_fields():
		for child in doc.get(table_field.fieldname) or []:
			if child.name and not child.is_new():
				_collect_unchanged_disabled_link_candidates(child, candidates)

	disabled_links = {}
	for doctype, names in candidates.items():
		if not names:
			continue

		rows = frappe.get_all(
			doctype,
			filters={
				"name": ["in", sorted(names)],
				"disabled": 1,
			},
			fields=["name"],
		)
		if rows:
			disabled_links[doctype] = sorted(row.name for row in rows)

	return disabled_links


def _collect_unchanged_disabled_link_candidates(doc, candidates):
	link_fields = _get_link_fields_with_disabled_targets(doc.doctype)
	if not link_fields:
		return

	fieldnames = [field.fieldname for field in link_fields]
	db_values = frappe.db.get_value(doc.doctype, doc.name, fieldnames, as_dict=True)
	if not db_values:
		return

	for field in link_fields:
		value = cstr(doc.get(field.fieldname)).strip()
		if not value:
			continue

		if value != cstr(db_values.get(field.fieldname)).strip():
			continue

		candidates.setdefault(field.options, set()).add(value)


def _get_link_fields_with_disabled_targets(doctype):
	fields = []
	for field in frappe.get_meta(doctype).get_link_fields():
		if field.options and frappe.get_meta(field.options).has_field("disabled"):
			fields.append(field)

	return fields


def _set_delivery_note_batch_check_skip_rows(doc, action, disabled_batch_nos):
	if cstr(action) != "Save" or cint(doc.get("docstatus")) != 0 or doc.is_new():
		return

	skip_rows = _get_unchanged_disabled_batch_item_row_names(doc, disabled_batch_nos)
	if skip_rows:
		doc.flags[SKIP_BATCH_CHECK_ROWS_FLAG] = skip_rows


def _get_unchanged_disabled_batch_item_row_names(doc, disabled_batch_nos):
	disabled_batch_nos = set(disabled_batch_nos or [])
	if not disabled_batch_nos:
		return []

	db_rows = frappe.get_all(
		"Delivery Note Item",
		filters={"parent": doc.name},
		fields=["name"] + list(DELIVERY_NOTE_BATCH_CHECK_FIELDS),
	)
	db_rows_by_name = {row.name: row for row in db_rows}

	skip_rows = []
	for row in doc.get("items") or []:
		if not row.name or cstr(row.get("batch_no")).strip() not in disabled_batch_nos:
			continue

		db_row = db_rows_by_name.get(row.name)
		if db_row and _batch_check_fields_are_unchanged(row, db_row):
			skip_rows.append(row.name)

	return skip_rows


def _batch_check_fields_are_unchanged(row, db_row):
	for fieldname in DELIVERY_NOTE_BATCH_CHECK_FIELDS:
		if fieldname in ("qty", "stock_qty"):
			if flt(row.get(fieldname)) != flt(db_row.get(fieldname)):
				return False
		elif cstr(row.get(fieldname)).strip() != cstr(db_row.get(fieldname)).strip():
			return False

	return True
