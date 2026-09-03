from __future__ import unicode_literals

import json

import frappe
from frappe import _
from frappe.utils import flt, now


WRONG_RECEIPT = "PREC-02960"
CORRECT_RECEIPT = "PREC-02868"
OVERFLOW_RECEIPT = "PREC-02979"

ITEM_CODE = "RVM.3300"
MAIN_WAREHOUSE = "Main Stock - AMF21"
WIP_WAREHOUSE = "Work In Progress - AMF21"

WRONG_BATCH = "20260413144307 RVM.3300 RC2 ELECTRONIQUE SA PO-02459"
CORRECT_BATCH = "20260422151806 RVM.3300 RC2 ELECTRONIQUE SA PO-02459"
OVERFLOW_BATCH = "P02LG9 RCE"

TRANSFER_SPLIT_DETAIL = "prec02960-transfer-split"
MANUFACTURE_SPLIT_DETAIL = "prec02960-manufacture-split"

# Rows which consumed or moved the duplicate receipt batch.  Every one of these
# rows belongs to the physical delivery recorded by PREC-02868.
WRONG_BATCH_USAGE = {
	"8f929c4004": ("STE-14542", 200.0),
	"95fbf45af0": ("STE-14777", 154.0),
	"2ca8cdaad8": ("STE-15132", 46.0),
	"f598107212": ("STE-16535", 100.0),
	"5593fa0b92": ("STE-16547", 100.0),
}

# By 13 July, PREC-02868 had only 100 units left.  The existing 167-unit
# transfer/manufacture rows therefore have to be split: 100 units remain on the
# correct receipt batch and 67 units came from the next valid receipt.
TRANSFER_DETAIL = "5f09001ddc"
MANUFACTURE_DETAIL = "c3762abce5"
SPLIT_KEEP_QTY = 100.0
SPLIT_OVERFLOW_QTY = 67.0


def execute(dry_run=True, commit=False):
	"""Correct the duplicate receipt and its downstream batch allocations.

	The function is deliberately site-specific and guarded by exact document,
	row, quantity and batch assertions.  It is safe to leave in ``patches.txt``:
	a later migrate becomes a no-op after the duplicate receipt has been removed.
	"""
	if not frappe.db.exists("Purchase Receipt", WRONG_RECEIPT):
		return _already_completed_summary()

	_validate_source_documents()
	_validate_stock_usage()

	summary = _build_summary(dry_run=dry_run)
	if dry_run:
		return summary

	try:
		_reassign_duplicate_batch_usage()
		_split_later_transfer_and_consumption()
		_normalize_wip_ledger_after_split()
		_cancel_and_delete_duplicate_receipt()
		_delete_obsolete_batch()
		_verify_completed_state()
		if commit:
			frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		raise

	summary.update(_completed_state())
	summary["status"] = "completed"
	return summary


def _already_completed_summary():
	state = _completed_state()
	if state["wrong_receipt_exists"]:
		frappe.throw(_("Unexpected state while checking {0}").format(WRONG_RECEIPT))

	return {
		"status": "already_completed",
		"dry_run": False,
		"wrong_receipt": WRONG_RECEIPT,
		"correct_receipt": CORRECT_RECEIPT,
		"overflow_receipt": OVERFLOW_RECEIPT,
		"item_code": ITEM_CODE,
		**state
	}


def _validate_source_documents():
	wrong = frappe.get_doc("Purchase Receipt", WRONG_RECEIPT)
	correct = frappe.get_doc("Purchase Receipt", CORRECT_RECEIPT)
	overflow = frappe.get_doc("Purchase Receipt", OVERFLOW_RECEIPT)

	_assert(wrong.docstatus == 1, "{0} must be submitted".format(WRONG_RECEIPT))
	_assert(correct.docstatus == 1, "{0} must be submitted".format(CORRECT_RECEIPT))
	_assert(overflow.docstatus == 1, "{0} must be submitted".format(OVERFLOW_RECEIPT))

	_validate_receipt_item(wrong, WRONG_BATCH, 400.0)
	_validate_receipt_item(correct, CORRECT_BATCH, 400.0)
	_validate_receipt_item(overflow, OVERFLOW_BATCH, 100.0)

	_assert(wrong.supplier == correct.supplier, "Receipt suppliers do not match")
	_assert(wrong.company == correct.company, "Receipt companies do not match")
	_assert(flt(wrong.grand_total) == flt(correct.grand_total), "Receipt totals do not match")

	invoice_links = frappe.db.sql(
		"""
		SELECT pii.parent
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pi.docstatus = 1 AND pii.purchase_receipt = %s
		""",
		WRONG_RECEIPT,
	)
	_assert(not invoice_links, "{0} has a submitted Purchase Invoice".format(WRONG_RECEIPT))

	landed_cost_links = frappe.db.sql(
		"""
		SELECT lcpr.parent
		FROM `tabLanded Cost Purchase Receipt` lcpr
		INNER JOIN `tabLanded Cost Voucher` lcv ON lcv.name = lcpr.parent
		WHERE lcv.docstatus = 1
		  AND lcpr.receipt_document_type = 'Purchase Receipt'
		  AND lcpr.receipt_document = %s
		""",
		WRONG_RECEIPT,
	)
	_assert(not landed_cost_links, "{0} has a submitted Landed Cost Voucher".format(WRONG_RECEIPT))

	returns = frappe.get_all(
		"Purchase Receipt",
		filters={"return_against": WRONG_RECEIPT, "docstatus": 1},
		fields=["name"],
	)
	_assert(not returns, "{0} has a submitted return".format(WRONG_RECEIPT))


def _validate_receipt_item(receipt, batch_no, qty):
	_assert(len(receipt.items) == 1, "{0} must have exactly one item row".format(receipt.name))
	row = receipt.items[0]
	_assert(row.item_code == ITEM_CODE, "Unexpected item on {0}".format(receipt.name))
	_assert(row.warehouse == MAIN_WAREHOUSE, "Unexpected warehouse on {0}".format(receipt.name))
	_assert(row.batch_no == batch_no, "Unexpected batch on {0}".format(receipt.name))
	_assert(flt(row.qty) == flt(qty), "Unexpected quantity on {0}".format(receipt.name))


def _validate_stock_usage():
	old_rows = frappe.get_all(
		"Stock Entry Detail",
		filters={"batch_no": WRONG_BATCH},
		fields=["name", "parent", "qty", "transfer_qty"],
	)
	_assert(
		set(row.name for row in old_rows) == set(WRONG_BATCH_USAGE),
		"The stock rows using the duplicate batch have changed",
	)

	for row in old_rows:
		expected_parent, expected_qty = WRONG_BATCH_USAGE[row.name]
		_assert(row.parent == expected_parent, "Unexpected parent for row {0}".format(row.name))
		_assert(flt(row.qty) == expected_qty, "Unexpected quantity for row {0}".format(row.name))
		_assert(flt(row.transfer_qty) == expected_qty, "Unexpected stock quantity for row {0}".format(row.name))
		_assert(
			frappe.db.get_value("Stock Entry", row.parent, "docstatus") == 1,
			"Stock Entry {0} must be submitted".format(row.parent),
		)

	_validate_split_row(TRANSFER_DETAIL, "STE-16546", 167.0, CORRECT_BATCH)
	_validate_split_row(MANUFACTURE_DETAIL, "STE-16547", 167.0, CORRECT_BATCH)

	_assert(
		not frappe.db.exists("Stock Entry Detail", TRANSFER_SPLIT_DETAIL),
		"Transfer split row already exists while the duplicate receipt is still present",
	)
	_assert(
		not frappe.db.exists("Stock Entry Detail", MANUFACTURE_SPLIT_DETAIL),
		"Manufacture split row already exists while the duplicate receipt is still present",
	)

	old_sle_pairs = set(
		frappe.db.sql(
			"""
			SELECT voucher_no, voucher_detail_no
			FROM `tabStock Ledger Entry`
			WHERE batch_no = %s AND is_cancelled = 'No'
			""",
			WRONG_BATCH,
		)
	)
	expected_pairs = {(WRONG_RECEIPT, frappe.db.get_value("Purchase Receipt Item", {"parent": WRONG_RECEIPT}, "name"))}
	expected_pairs.update((parent, detail) for detail, (parent, unused_qty) in WRONG_BATCH_USAGE.items())
	_assert(old_sle_pairs == expected_pairs, "The Stock Ledger Entries for the duplicate batch have changed")


def _validate_split_row(detail_name, parent, qty, batch_no):
	row = frappe.db.get_value(
		"Stock Entry Detail",
		detail_name,
		["parent", "item_code", "qty", "transfer_qty", "batch_no"],
		as_dict=True,
	)
	_assert(row, "Missing Stock Entry Detail {0}".format(detail_name))
	_assert(row.parent == parent, "Unexpected parent for row {0}".format(detail_name))
	_assert(row.item_code == ITEM_CODE, "Unexpected item for row {0}".format(detail_name))
	_assert(flt(row.qty) == qty, "Unexpected quantity for row {0}".format(detail_name))
	_assert(flt(row.transfer_qty) == qty, "Unexpected stock quantity for row {0}".format(detail_name))
	_assert(row.batch_no == batch_no, "Unexpected batch for row {0}".format(detail_name))


def _build_summary(dry_run):
	return {
		"status": "validated" if dry_run else "running",
		"dry_run": bool(dry_run),
		"wrong_receipt": WRONG_RECEIPT,
		"correct_receipt": CORRECT_RECEIPT,
		"overflow_receipt": OVERFLOW_RECEIPT,
		"item_code": ITEM_CODE,
		"duplicate_receipt_qty_to_remove": 400.0,
		"duplicate_batch_qty_reassigned_to_correct_batch": 300.0,
		"correct_receipt_qty_used_in_production": 400.0,
		"overflow_receipt_qty_used_in_production": 67.0,
		"expected_remaining_qty": 33.0,
		"stock_entries_updated": sorted(set(parent for parent, unused_qty in WRONG_BATCH_USAGE.values()) | {"STE-16546"}),
	}


def _reassign_duplicate_batch_usage():
	for detail_name, (parent, unused_qty) in WRONG_BATCH_USAGE.items():
		frappe.db.set_value("Stock Entry Detail", detail_name, "batch_no", CORRECT_BATCH, update_modified=False)
		frappe.db.sql(
			"""
			UPDATE `tabStock Ledger Entry`
			SET batch_no = %s, modified = %s, modified_by = %s
			WHERE voucher_type = 'Stock Entry'
			  AND voucher_no = %s
			  AND voucher_detail_no = %s
			  AND batch_no = %s
			  AND is_cancelled = 'No'
			""",
			(CORRECT_BATCH, now(), frappe.session.user, parent, detail_name, WRONG_BATCH),
		)


def _split_later_transfer_and_consumption():
	transfer_split = _split_stock_entry_detail(
		TRANSFER_DETAIL,
		TRANSFER_SPLIT_DETAIL,
		OVERFLOW_BATCH,
		SPLIT_KEEP_QTY,
		SPLIT_OVERFLOW_QTY,
	)
	manufacture_split = _split_stock_entry_detail(
		MANUFACTURE_DETAIL,
		MANUFACTURE_SPLIT_DETAIL,
		OVERFLOW_BATCH,
		SPLIT_KEEP_QTY,
		SPLIT_OVERFLOW_QTY,
	)

	_split_stock_ledger_entries(TRANSFER_DETAIL, transfer_split.name, OVERFLOW_BATCH)
	_split_stock_ledger_entries(MANUFACTURE_DETAIL, manufacture_split.name, OVERFLOW_BATCH)


def _split_stock_entry_detail(source_name, new_name, new_batch, keep_qty, split_qty):
	source = frappe.get_doc("Stock Entry Detail", source_name)
	original_qty = flt(source.transfer_qty)
	_assert(original_qty == keep_qty + split_qty, "Invalid split quantity for {0}".format(source_name))

	frappe.db.sql(
		"""
		UPDATE `tabStock Entry Detail`
		SET idx = idx + 1
		WHERE parent = %s AND idx > %s
		""",
		(source.parent, source.idx),
	)

	split = frappe.copy_doc(source)
	split.name = new_name
	split.idx = source.idx + 1
	split.batch_no = new_batch
	_set_detail_qty_and_amount(split, split_qty, original_qty)
	split.creation = None
	split.modified = None
	split.owner = frappe.session.user
	split.modified_by = frappe.session.user
	split.docstatus = source.docstatus
	split.db_insert()

	_set_detail_qty_and_amount(source, keep_qty, original_qty)
	source.db_update()
	return split


def _set_detail_qty_and_amount(row, qty, original_qty):
	ratio = flt(qty) / flt(original_qty)
	row.qty = qty
	row.transfer_qty = qty
	for fieldname in ("basic_amount", "additional_cost", "amount"):
		row.set(fieldname, flt(row.get(fieldname)) * ratio)


def _split_stock_ledger_entries(source_detail, split_detail, split_batch):
	entries = frappe.get_all(
		"Stock Ledger Entry",
		filters={
			"voucher_type": "Stock Entry",
			"voucher_detail_no": source_detail,
			"is_cancelled": "No",
		},
		fields=["name"],
		order_by="creation asc, name asc",
	)
	_assert(entries, "No Stock Ledger Entries found for {0}".format(source_detail))

	for entry_name in [entry.name for entry in entries]:
		source = frappe.get_doc("Stock Ledger Entry", entry_name)
		_assert(abs(flt(source.actual_qty)) == 167.0, "Unexpected ledger quantity on {0}".format(entry_name))

		split = frappe.copy_doc(source)
		split.name = None
		split.voucher_detail_no = split_detail
		split.batch_no = split_batch
		split.actual_qty = SPLIT_OVERFLOW_QTY if flt(source.actual_qty) > 0 else -SPLIT_OVERFLOW_QTY
		split.creation = None
		split.modified = None
		split.owner = frappe.session.user
		split.modified_by = frappe.session.user
		split.docstatus = source.docstatus
		split.db_insert()

		source.actual_qty = SPLIT_KEEP_QTY if flt(source.actual_qty) > 0 else -SPLIT_KEEP_QTY
		source.db_update()


def _normalize_wip_ledger_after_split():
	# Quantities per warehouse are unchanged, but splitting one ledger row into
	# two requires rebuilding the intermediate qty_after_transaction/stock_queue.
	from erpnext.stock.stock_ledger import update_entries_after

	update_entries_after(
		{
			"item_code": ITEM_CODE,
			"warehouse": WIP_WAREHOUSE,
			"posting_date": "2026-07-13",
			"posting_time": "07:36:01.435115",
		}
	)


def _cancel_and_delete_duplicate_receipt():
	doc = frappe.get_doc("Purchase Receipt", WRONG_RECEIPT)
	doc.flags.ignore_permissions = True
	doc.cancel()
	frappe.delete_doc("Purchase Receipt", WRONG_RECEIPT, ignore_permissions=True)


def _delete_obsolete_batch():
	_assert(
		not frappe.db.exists("Stock Entry Detail", {"batch_no": WRONG_BATCH}),
		"The obsolete batch is still linked to a Stock Entry",
	)
	_assert(
		not frappe.db.exists("Stock Ledger Entry", {"batch_no": WRONG_BATCH, "is_cancelled": "No"}),
		"The obsolete batch is still linked to an active Stock Ledger Entry",
	)
	if frappe.db.exists("Batch", WRONG_BATCH):
		frappe.delete_doc("Batch", WRONG_BATCH, ignore_permissions=True)


def _verify_completed_state():
	state = _completed_state()
	_assert(not state["wrong_receipt_exists"], "Duplicate Purchase Receipt still exists")
	_assert(not state["wrong_batch_exists"], "Obsolete Batch still exists")
	_assert(state["correct_receipt_docstatus"] == 1, "Correct Purchase Receipt is not submitted")
	_assert(state["correct_invoice_docstatus"] == 1, "Correct Purchase Invoice is not submitted")
	_assert(flt(state["main_stock_qty"]) == 33.0, "Unexpected Main Stock quantity after repair")
	_assert(flt(state["wip_stock_qty"]) == 0.0, "Unexpected WIP quantity after repair")
	_assert(flt(state["correct_batch_main_qty"]) == 0.0, "Correct receipt batch was not fully consumed")
	_assert(flt(state["overflow_batch_main_qty"]) == 33.0, "Unexpected remaining overflow batch quantity")
	_assert(flt(state["correct_batch_wip_qty"]) == 0.0, "Correct receipt batch remains in WIP")
	_assert(flt(state["overflow_batch_wip_qty"]) == 0.0, "Overflow receipt batch remains in WIP")


def _completed_state():
	return {
		"wrong_receipt_exists": bool(frappe.db.exists("Purchase Receipt", WRONG_RECEIPT)),
		"wrong_batch_exists": bool(frappe.db.exists("Batch", WRONG_BATCH)),
		"correct_receipt_docstatus": frappe.db.get_value("Purchase Receipt", CORRECT_RECEIPT, "docstatus"),
		"correct_invoice_docstatus": frappe.db.get_value("Purchase Invoice", "PINV-05886", "docstatus"),
		"main_stock_qty": _bin_qty(MAIN_WAREHOUSE),
		"wip_stock_qty": _bin_qty(WIP_WAREHOUSE),
		"correct_batch_main_qty": _batch_qty(CORRECT_BATCH, MAIN_WAREHOUSE),
		"correct_batch_wip_qty": _batch_qty(CORRECT_BATCH, WIP_WAREHOUSE),
		"overflow_batch_main_qty": _batch_qty(OVERFLOW_BATCH, MAIN_WAREHOUSE),
		"overflow_batch_wip_qty": _batch_qty(OVERFLOW_BATCH, WIP_WAREHOUSE),
	}


def _bin_qty(warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": ITEM_CODE, "warehouse": warehouse}, "actual_qty"))


def _batch_qty(batch_no, warehouse):
	return flt(
		frappe.db.sql(
			"""
			SELECT SUM(actual_qty)
			FROM `tabStock Ledger Entry`
			WHERE item_code = %s
			  AND warehouse = %s
			  AND batch_no = %s
			  AND is_cancelled = 'No'
			""",
			(ITEM_CODE, warehouse, batch_no),
		)[0][0]
	)


def _assert(condition, message):
	if not condition:
		frappe.throw(_("PREC-02960 correction aborted: {0}").format(message))


def print_summary(dry_run=True, commit=False):
	"""Bench-friendly wrapper which prints JSON instead of a Python dict."""
	result = execute(dry_run=dry_run, commit=commit)
	print(json.dumps(result, indent=2, sort_keys=True, default=str))
	return result
