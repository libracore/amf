# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import erpnext
import frappe
from erpnext.stock import get_warehouse_account_map
from erpnext.stock.get_item_details import get_conversion_factor
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, nowdate, nowtime


LOAN_MOVEMENT_OUTWARD = "Outward"
LOAN_MOVEMENT_RETURN = "Return"
LOAN_DN_OBJECT = "Loan (temporary export)"


class LoanOrder(Document):
	def validate(self):
		self.set_defaults()
		self.validate_party()
		self.validate_warehouses()
		self.validate_items()
		self.sync_status(update=False)

	def before_submit(self):
		if not self.get("items"):
			frappe.throw(_("At least one item is required."))

	def on_submit(self):
		self.sync_status(update=True)

	def before_cancel(self):
		submitted_links = self.get_submitted_linked_documents()
		if submitted_links:
			frappe.throw(
				_("Cancel the submitted stock documents linked to this Loan Order first: {0}")
				.format(", ".join(submitted_links))
			)

	def on_cancel(self):
		self.status = "Cancelled"

	def on_update_after_submit(self):
		self.set_defaults()
		self.validate_party()
		self.validate_warehouses()
		self.validate_items()
		self.sync_status(update=True)

	def set_defaults(self):
		if not self.status:
			self.status = "Draft"

		if self.company and not self.currency:
			self.currency = frappe.db.get_value("Company", self.company, "default_currency")

		if self.source_warehouse and not self.return_warehouse:
			self.return_warehouse = self.source_warehouse

	def validate_party(self):
		if self.party_type not in ("Customer", "Supplier"):
			frappe.throw(_("Party Type must be Customer or Supplier."))

		if not self.party:
			return

		if not frappe.db.exists(self.party_type, self.party):
			frappe.throw(_("{0} {1} does not exist.").format(self.party_type, self.party))

		name_field = "customer_name" if self.party_type == "Customer" else "supplier_name"
		self.party_name = frappe.db.get_value(self.party_type, self.party, name_field) or self.party
		self.title = self.party_name

		if self.party_type == "Customer" and not self.delivery_customer:
			self.delivery_customer = self.party

	def validate_warehouses(self):
		for fieldname in ("source_warehouse", "loan_warehouse", "return_warehouse"):
			warehouse = self.get(fieldname)
			if warehouse:
				self.validate_warehouse_company(warehouse)

		if self.source_warehouse and self.loan_warehouse and self.source_warehouse == self.loan_warehouse:
			frappe.throw(_("Default Source Warehouse and Default Loan Warehouse must be different."))

		if self.loan_warehouse and self.return_warehouse and self.loan_warehouse == self.return_warehouse:
			frappe.throw(_("Default Loan Warehouse and Default Return Warehouse must be different."))

	def validate_items(self):
		if not self.get("items"):
			return

		for row in self.items:
			if not row.item_code:
				continue

			item = frappe.db.get_value(
				"Item",
				row.item_code,
				["item_name", "description", "stock_uom", "is_stock_item"],
				as_dict=True,
			)
			if not item:
				frappe.throw(_("Row {0}: Item {1} does not exist.").format(row.idx, row.item_code))

			if not cint(item.is_stock_item):
				frappe.throw(_("Row {0}: Item {1} must be a stock item for a Loan Order.").format(row.idx, row.item_code))

			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: Quantity must be greater than zero.").format(row.idx))

			row.item_name = item.item_name
			if not row.description:
				row.description = item.description
			row.stock_uom = item.stock_uom
			if not row.uom:
				row.uom = item.stock_uom
			row.conversion_factor = self.get_item_conversion_factor(row.item_code, row.uom, item.stock_uom)
			row.declared_amount = flt(row.qty) * flt(row.declared_rate)

			if not row.source_warehouse:
				row.source_warehouse = self.source_warehouse
			if not row.loan_warehouse:
				row.loan_warehouse = self.loan_warehouse
			if not row.return_warehouse:
				row.return_warehouse = self.return_warehouse or self.source_warehouse

			self.validate_item_warehouses(row)

			if self.docstatus == 0:
				row.loaned_qty = 0
				row.returned_qty = 0
				row.remaining_qty = 0

	def validate_item_warehouses(self, row):
		if not row.source_warehouse:
			frappe.throw(_("Row {0}: Source Warehouse is required.").format(row.idx))
		if not row.loan_warehouse:
			frappe.throw(_("Row {0}: Loan Warehouse is required.").format(row.idx))
		if not row.return_warehouse:
			frappe.throw(_("Row {0}: Return Warehouse is required.").format(row.idx))

		for warehouse in (row.source_warehouse, row.loan_warehouse, row.return_warehouse):
			self.validate_warehouse_company(warehouse)

		if row.source_warehouse == row.loan_warehouse:
			frappe.throw(_("Row {0}: Source Warehouse and Loan Warehouse must be different.").format(row.idx))
		if row.loan_warehouse == row.return_warehouse:
			frappe.throw(_("Row {0}: Loan Warehouse and Return Warehouse must be different.").format(row.idx))

	def validate_warehouse_company(self, warehouse):
		if not frappe.db.exists("Warehouse", warehouse):
			frappe.throw(_("Warehouse {0} does not exist.").format(warehouse))

		warehouse_company = frappe.db.get_value("Warehouse", warehouse, "company")
		if warehouse_company and self.company and warehouse_company != self.company:
			frappe.throw(_("Warehouse {0} does not belong to Company {1}.").format(warehouse, self.company))

	def get_item_conversion_factor(self, item_code, uom, stock_uom):
		if not uom or uom == stock_uom:
			return 1

		conversion = get_conversion_factor(item_code, uom)
		return flt(conversion.get("conversion_factor") if conversion else 1) or 1

	def sync_status(self, update=False):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 2:
			self.status = "Cancelled"
		else:
			quantity_map = get_loan_order_quantity_map(self.name)
			total_qty = total_loaned = total_returned = outstanding_qty = 0

			for row in self.items:
				quantities = quantity_map.get(row.name, {})
				row.loaned_qty = flt(quantities.get("loaned_qty"))
				row.returned_qty = flt(quantities.get("returned_qty"))
				row.remaining_qty = max(row.loaned_qty - row.returned_qty, 0)

				total_qty += flt(row.qty)
				total_loaned += row.loaned_qty
				total_returned += row.returned_qty
				outstanding_qty += row.remaining_qty

			self.status = self.get_status_from_quantities(total_qty, total_loaned, total_returned, outstanding_qty)

			if self.status == "Returned" and not self.actual_return_date:
				self.actual_return_date = nowdate()
			elif self.status != "Returned" and self.actual_return_date and outstanding_qty:
				self.actual_return_date = None

		if update and self.name:
			for row in self.items:
				frappe.db.set_value(
					"Loan Order Item",
					row.name,
					{
						"loaned_qty": row.loaned_qty,
						"returned_qty": row.returned_qty,
						"remaining_qty": row.remaining_qty,
					},
					update_modified=False,
				)

			self.db_set("status", self.status, update_modified=False)
			self.db_set("actual_return_date", self.actual_return_date, update_modified=False)

	def get_status_from_quantities(self, total_qty, total_loaned, total_returned, outstanding_qty):
		if total_loaned <= 0:
			return "Submitted"
		if outstanding_qty <= 0:
			return "Returned"
		if total_returned > 0:
			return "Partly Returned"
		if self.expected_return_date and nowdate() > self.expected_return_date:
			return "Overdue"
		if total_loaned < total_qty:
			return "Partly Loaned"
		return "On Loan"

	def get_submitted_linked_documents(self):
		links = []
		for fieldname, doctype in (
			("outward_stock_entry", "Stock Entry"),
			("outward_delivery_note", "Delivery Note"),
			("return_stock_entry", "Stock Entry"),
			("return_delivery_note", "Delivery Note"),
		):
			name = self.get(fieldname)
			if name and frappe.db.exists(doctype, name) and cint(frappe.db.get_value(doctype, name, "docstatus")) == 1:
				links.append("{0} {1}".format(doctype, name))
		return links

	def validate_neutral_stock_accounts(self, movement):
		if not cint(self.require_neutral_stock_accounts):
			return

		if not cint(erpnext.is_perpetual_inventory_enabled(self.company)):
			return

		warehouse_account = get_warehouse_account_map(self.company)
		for row in get_transfer_rows(self, movement):
			source, target = get_transfer_warehouses(row, movement)
			source_account = warehouse_account.get(source, {}).get("account")
			target_account = warehouse_account.get(target, {}).get("account")
			if source_account != target_account:
				frappe.throw(
					_(
						"Loan Order requires neutral stock accounts, but {0} uses {1} and {2} uses {3}. "
						"Use warehouses with the same inventory account or disable the safeguard on the Loan Order."
					).format(source, source_account, target, target_account)
				)


@frappe.whitelist()
def make_outward_stock_entry(source_name):
	loan_order = get_submitted_loan_order(source_name)
	ensure_no_active_alternative(loan_order, "outward_delivery_note", "Delivery Note")
	existing = get_active_linked_document(loan_order, "outward_stock_entry", "Stock Entry")
	if existing:
		return existing

	loan_order.validate_neutral_stock_accounts(LOAN_MOVEMENT_OUTWARD)
	stock_entry = build_stock_entry(loan_order, LOAN_MOVEMENT_OUTWARD)
	stock_entry.insert()

	loan_order.db_set("outward_stock_entry", stock_entry.name)
	loan_order.sync_status(update=True)
	return {"doctype": "Stock Entry", "name": stock_entry.name}


@frappe.whitelist()
def make_return_stock_entry(source_name):
	loan_order = get_submitted_loan_order(source_name)
	ensure_no_active_alternative(loan_order, "return_delivery_note", "Delivery Note")
	existing = get_active_linked_document(loan_order, "return_stock_entry", "Stock Entry")
	if existing:
		return existing

	loan_order.sync_status(update=True)
	loan_order.validate_neutral_stock_accounts(LOAN_MOVEMENT_RETURN)
	stock_entry = build_stock_entry(loan_order, LOAN_MOVEMENT_RETURN)
	stock_entry.insert()

	loan_order.db_set("return_stock_entry", stock_entry.name)
	loan_order.sync_status(update=True)
	return {"doctype": "Stock Entry", "name": stock_entry.name}


@frappe.whitelist()
def make_outward_delivery_note(source_name):
	loan_order = get_submitted_loan_order(source_name)
	ensure_no_active_alternative(loan_order, "outward_stock_entry", "Stock Entry")
	existing = get_active_linked_document(loan_order, "outward_delivery_note", "Delivery Note")
	if existing:
		return existing

	loan_order.validate_neutral_stock_accounts(LOAN_MOVEMENT_OUTWARD)
	delivery_note = build_delivery_note(loan_order, LOAN_MOVEMENT_OUTWARD)
	delivery_note.insert()

	loan_order.db_set("outward_delivery_note", delivery_note.name)
	loan_order.sync_status(update=True)
	return {"doctype": "Delivery Note", "name": delivery_note.name}


@frappe.whitelist()
def make_return_delivery_note(source_name):
	loan_order = get_submitted_loan_order(source_name)
	ensure_no_active_alternative(loan_order, "return_stock_entry", "Stock Entry")
	existing = get_active_linked_document(loan_order, "return_delivery_note", "Delivery Note")
	if existing:
		return existing

	if not loan_order.outward_delivery_note or not frappe.db.exists("Delivery Note", loan_order.outward_delivery_note):
		frappe.throw(_("A return Delivery Note can only be created after an outward Delivery Note."))

	if cint(frappe.db.get_value("Delivery Note", loan_order.outward_delivery_note, "docstatus")) != 1:
		frappe.throw(_("Submit the outward Delivery Note before creating the return Delivery Note."))

	loan_order.sync_status(update=True)
	loan_order.validate_neutral_stock_accounts(LOAN_MOVEMENT_RETURN)
	delivery_note = build_delivery_note(loan_order, LOAN_MOVEMENT_RETURN)
	delivery_note.insert()

	loan_order.db_set("return_delivery_note", delivery_note.name)
	loan_order.sync_status(update=True)
	return {"doctype": "Delivery Note", "name": delivery_note.name}


@frappe.whitelist()
def refresh_loan_order_status(source_name):
	loan_order = frappe.get_doc("Loan Order", source_name)
	loan_order.check_permission("read")
	loan_order.sync_status(update=True)
	return {"status": loan_order.status}


def update_linked_loan_order(doc, method=None):
	loan_order_name = doc.get("loan_order")
	if not loan_order_name or not frappe.db.exists("Loan Order", loan_order_name):
		return

	loan_order = frappe.get_doc("Loan Order", loan_order_name)
	loan_order.sync_status(update=True)


def get_submitted_loan_order(source_name):
	loan_order = frappe.get_doc("Loan Order", source_name)
	loan_order.check_permission("read")

	if loan_order.docstatus != 1:
		frappe.throw(_("Submit the Loan Order before creating stock documents."))

	loan_order.set_defaults()
	loan_order.validate_party()
	loan_order.validate_warehouses()
	loan_order.validate_items()
	return loan_order


def get_active_linked_document(loan_order, fieldname, doctype):
	name = loan_order.get(fieldname)
	if name and frappe.db.exists(doctype, name) and cint(frappe.db.get_value(doctype, name, "docstatus")) != 2:
		return {"doctype": doctype, "name": name}
	return None


def ensure_no_active_alternative(loan_order, fieldname, doctype):
	existing = get_active_linked_document(loan_order, fieldname, doctype)
	if existing:
		frappe.throw(_("{0} {1} is already linked to this Loan Order.").format(existing["doctype"], existing["name"]))


def build_stock_entry(loan_order, movement):
	rows = get_transfer_rows(loan_order, movement)
	if not rows:
		frappe.throw(_("There are no quantities to transfer."))

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.company = loan_order.company
	stock_entry.purpose = "Material Transfer"
	stock_entry.posting_date = nowdate()
	stock_entry.posting_time = nowtime()
	stock_entry.set_posting_time = 1
	stock_entry.remarks = get_movement_remarks(loan_order, movement)
	set_if_has_field(stock_entry, "loan_order", loan_order.name)
	set_if_has_field(stock_entry, "loan_order_movement", movement)

	if loan_order.party_type == "Customer":
		set_if_has_field(stock_entry, "customer", loan_order.party)
	elif loan_order.party_type == "Supplier":
		set_if_has_field(stock_entry, "supplier", loan_order.party)

	if hasattr(stock_entry, "set_stock_entry_type"):
		stock_entry.set_stock_entry_type()

	default_source, default_target = get_common_transfer_warehouses(rows, movement)
	if default_source:
		stock_entry.from_warehouse = default_source
	if default_target:
		stock_entry.to_warehouse = default_target

	for row in rows:
		source, target = get_transfer_warehouses(row, movement)
		child = stock_entry.append("items", {
			"item_code": row.item_code,
			"item_name": row.item_name,
			"description": row.description,
			"s_warehouse": source,
			"t_warehouse": target,
			"qty": row.transfer_qty,
			"uom": row.uom,
			"stock_uom": row.stock_uom,
			"conversion_factor": row.conversion_factor,
			"serial_no": row.serial_no,
			"batch_no": row.batch_no,
		})
		set_if_has_field(child, "loan_order_item", row.name)

	return stock_entry


def build_delivery_note(loan_order, movement):
	rows = get_transfer_rows(loan_order, movement)
	if not rows:
		frappe.throw(_("There are no quantities to transfer."))

	customer = get_delivery_note_customer(loan_order)
	delivery_note = frappe.new_doc("Delivery Note")
	delivery_note.company = loan_order.company
	delivery_note.customer = customer
	delivery_note.currency = loan_order.currency
	delivery_note.posting_date = nowdate()
	delivery_note.posting_time = nowtime()
	delivery_note.set_posting_time = 1
	delivery_note.ignore_pricing_rule = 1
	delivery_note.remarks = get_movement_remarks(loan_order, movement)
	set_if_has_field(delivery_note, "loan_order", loan_order.name)
	set_if_has_field(delivery_note, "loan_order_movement", movement)
	set_if_has_field(delivery_note, "object", LOAN_DN_OBJECT)

	if movement == LOAN_MOVEMENT_RETURN:
		delivery_note.is_return = 1
		delivery_note.return_against = loan_order.outward_delivery_note
		delivery_note.issue_credit_note = 0

	for row in rows:
		source, target = get_transfer_warehouses(row, movement)
		qty = row.transfer_qty if movement == LOAN_MOVEMENT_OUTWARD else -1 * row.transfer_qty
		warehouse = source
		target_warehouse = target
		if movement == LOAN_MOVEMENT_RETURN:
			# ERPNext Delivery Note returns add stock back to `warehouse`
			# and remove it from `target_warehouse` when qty is negative.
			warehouse = target
			target_warehouse = source

		child = delivery_note.append("items", {
			"item_code": row.item_code,
			"item_name": row.item_name,
			"description": row.description,
			"warehouse": warehouse,
			"target_warehouse": target_warehouse,
			"qty": qty,
			"uom": row.uom,
			"stock_uom": row.stock_uom,
			"conversion_factor": row.conversion_factor,
			"stock_qty": qty * flt(row.conversion_factor),
			"rate": flt(row.declared_rate),
			"serial_no": row.serial_no,
			"batch_no": row.batch_no,
		})
		set_if_has_field(child, "loan_order_item", row.name)

	delivery_note.run_method("set_missing_values")
	delivery_note.run_method("calculate_taxes_and_totals")
	return delivery_note


def get_delivery_note_customer(loan_order):
	if loan_order.party_type == "Customer":
		return loan_order.party

	if loan_order.delivery_customer:
		return loan_order.delivery_customer

	frappe.throw(_("Set Delivery Note Customer before creating a Delivery Note for a supplier loan."))


def get_transfer_rows(loan_order, movement):
	rows = []
	for row in loan_order.items:
		transfer_qty = get_transfer_qty(row, movement)
		if transfer_qty <= 0:
			continue

		row = frappe._dict(row.as_dict())
		row.transfer_qty = transfer_qty
		rows.append(row)
	return rows


def get_transfer_qty(row, movement):
	if movement == LOAN_MOVEMENT_OUTWARD:
		return max(flt(row.qty) - flt(row.loaned_qty), 0)
	return max(flt(row.remaining_qty), 0)


def get_transfer_warehouses(row, movement):
	if movement == LOAN_MOVEMENT_OUTWARD:
		return row.source_warehouse, row.loan_warehouse
	return row.loan_warehouse, row.return_warehouse


def get_common_transfer_warehouses(rows, movement):
	sources = set()
	targets = set()
	for row in rows:
		source, target = get_transfer_warehouses(row, movement)
		sources.add(source)
		targets.add(target)

	return (
		list(sources)[0] if len(sources) == 1 else None,
		list(targets)[0] if len(targets) == 1 else None,
	)


def get_movement_remarks(loan_order, movement):
	if movement == LOAN_MOVEMENT_OUTWARD:
		action = _("Temporary loan export")
	else:
		action = _("Temporary loan return")

	return "{0} {1} - {2}".format(action, loan_order.name, loan_order.party_name or loan_order.party)


def get_loan_order_quantity_map(loan_order_name):
	quantity_map = {}
	for row in frappe.get_all("Loan Order Item", filters={"parent": loan_order_name}, fields=["name"]):
		quantity_map[row.name] = {"loaned_qty": 0, "returned_qty": 0}

	add_movement_quantities(quantity_map, "Stock Entry", "Stock Entry Detail", loan_order_name, LOAN_MOVEMENT_OUTWARD, "loaned_qty")
	add_movement_quantities(quantity_map, "Delivery Note", "Delivery Note Item", loan_order_name, LOAN_MOVEMENT_OUTWARD, "loaned_qty")
	add_movement_quantities(quantity_map, "Stock Entry", "Stock Entry Detail", loan_order_name, LOAN_MOVEMENT_RETURN, "returned_qty")
	add_movement_quantities(quantity_map, "Delivery Note", "Delivery Note Item", loan_order_name, LOAN_MOVEMENT_RETURN, "returned_qty")
	return quantity_map


def add_movement_quantities(quantity_map, parent_doctype, child_doctype, loan_order_name, movement, target_field):
	if not (
		meta_has_field(parent_doctype, "loan_order")
		and meta_has_field(parent_doctype, "loan_order_movement")
		and meta_has_field(child_doctype, "loan_order_item")
	):
		return

	rows = frappe.db.sql(
		"""
		SELECT child.loan_order_item, SUM(ABS(child.qty)) AS qty
		FROM `tab{child_doctype}` child
		INNER JOIN `tab{parent_doctype}` parent ON parent.name = child.parent
		WHERE parent.docstatus = 1
		  AND parent.loan_order = %(loan_order)s
		  AND parent.loan_order_movement = %(movement)s
		  AND IFNULL(child.loan_order_item, '') != ''
		GROUP BY child.loan_order_item
		""".format(child_doctype=child_doctype, parent_doctype=parent_doctype),
		{"loan_order": loan_order_name, "movement": movement},
		as_dict=True,
	)

	for row in rows:
		if row.loan_order_item in quantity_map:
			quantity_map[row.loan_order_item][target_field] += flt(row.qty)


def set_if_has_field(doc, fieldname, value):
	if doc.meta.get_field(fieldname):
		doc.set(fieldname, value)


def meta_has_field(doctype, fieldname):
	try:
		return bool(frappe.get_meta(doctype).get_field(fieldname))
	except Exception:
		return False
