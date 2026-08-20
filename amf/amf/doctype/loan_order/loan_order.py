# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import json

import erpnext
import frappe
from erpnext.stock import get_warehouse_account_map
from erpnext.stock.get_item_details import (
	get_conversion_factor,
	get_item_price,
	get_price_list_currency,
	get_price_list_uom_dependant,
)
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display, get_default_address
from frappe.contacts.doctype.contact.contact import get_default_contact
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, getdate, nowdate, nowtime
from six import string_types


LOAN_MOVEMENT_OUTWARD = "Outward"
LOAN_MOVEMENT_RETURN = "Return"
LOAN_DN_OBJECT = "Loan (temporary export)"
LOAN_BILLING_PENDING = "Pending"
LOAN_BILLING_SPARES = "Spare Parts Only"
LOAN_BILLING_PURCHASE = "Full Product Purchase"
LOAN_BILLING_DECISIONS = (LOAN_BILLING_SPARES, LOAN_BILLING_PURCHASE)
LOAN_PRODUCT_ROLE = "Product"
LOAN_SPARE_ROLE = "Spare Part"
LOAN_OTHER_ROLE = "Other Item"
LOAN_EXCLUDED_ROLE = "Do Not Invoice"
LOAN_AUTO_ROLE = "Auto"
LOAN_DELIVERY_COMPONENT_GROUPS = ("Body", "Valve Head", "Syringe")
LOAN_SPARE_COMPONENT_GROUPS = ("Valve Head", "Syringe")
LOAN_CLIENT_SITE_WAREHOUSE = "Client Site - AMF21"
LOAN_SETTLEMENT_FULL_SALE = "Full Product Sale"
LOAN_SETTLEMENT_SPARE_SALE = "Spare Parts Sale"
LOAN_SETTLEMENT_RETURN = "Remaining Items Return"
LOAN_SETTLEMENT_REPACK = "Dismantle Product"


def get_loan_order_print_contact(contact_name, fallback_email=None):
	if not contact_name or not frappe.db.exists("Contact", contact_name):
		return frappe._dict(email=fallback_email or "")

	contact = frappe.get_cached_doc("Contact", contact_name)
	return frappe._dict(
		name=contact.full_name or " ".join(
			part for part in (contact.first_name, contact.last_name) if part
		),
		designation=contact.designation or "",
		email=fallback_email or contact.email_id or "",
		phone=contact.phone or contact.mobile_no or "",
	)


class LoanOrder(Document):
	def before_print(self):
		"""Prepare customer-facing address and contact details for print formats."""
		party_address = get_default_address(self.party_type, self.party, "is_shipping_address")
		contact_name = self.contact_person or get_default_contact(self.party_type, self.party)
		item_codes = list(set(row.item_code for row in self.items if row.item_code))
		client_descriptions = {
			item.name: item.description
			for item in frappe.get_all(
				"Item",
				filters={"name": ("in", item_codes)},
				fields=["name", "description"],
			)
			if item.description
		} if item_codes else {}

		self.print_party_address = get_address_display(party_address) or ""
		self.print_contact = get_loan_order_print_contact(contact_name, self.contact_email)
		self.print_loan_duration = (
			date_diff(self.expected_return_date, self.transaction_date)
			if self.transaction_date and self.expected_return_date
			else None
		)
		for row in self.items:
			row.print_description = client_descriptions.get(row.item_code) or row.description or row.item_name

	def onload(self):
		currency = self.currency or frappe.db.get_value("Company", self.company, "default_currency")
		self.set_onload(
			"default_selling_price_list",
			get_default_selling_price_list(self.party if self.party_type == "Customer" else None, currency),
		)

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
		if not self.get("billing_status"):
			self.billing_status = LOAN_BILLING_PENDING
		if not self.get("billing_decision"):
			self.billing_decision = LOAN_BILLING_PENDING

		if self.company and not self.currency:
			self.currency = frappe.db.get_value("Company", self.company, "default_currency")
		if self.party_type == "Customer" and self.party and not self.get("selling_price_list"):
			self.selling_price_list = get_default_selling_price_list(self.party, self.currency)

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
				["item_name", "description", "stock_uom", "is_stock_item", "item_group", "item_type"],
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
			self.set_item_billing_details(row, item)

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

	def set_item_billing_details(self, row, item):
		role = get_commercial_role(row, item)
		if role != LOAN_PRODUCT_ROLE:
			row.component_summary = None
			return

		if row.get("billing_bom"):
			validate_product_bom(row.item_code, row.billing_bom, row.idx)
		else:
			row.billing_bom = get_default_product_bom(row.item_code)

		row.component_summary = get_delivery_component_summary(row)

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
		elif self.is_commercially_settled():
			self.status = "Closed"
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

	def is_commercially_settled(self):
		if self.get("billing_status") != "Invoiced":
			return False
		if not is_submitted_document("Delivery Note", self.get("settlement_delivery_note")):
			return False
		if self.get("billing_decision") == LOAN_BILLING_PURCHASE:
			return True
		if self.get("billing_decision") == LOAN_BILLING_SPARES:
			return (
				is_submitted_document("Stock Entry", self.get("settlement_stock_entry"))
				and is_submitted_document("Delivery Note", self.get("settlement_return_delivery_note"))
			)
		return False

	def get_status_from_quantities(self, total_qty, total_loaned, total_returned, outstanding_qty):
		if total_loaned <= 0:
			return "Submitted"
		if outstanding_qty <= 0:
			return "Returned"
		if total_returned > 0:
			return "Partly Returned"
		if self.expected_return_date and getdate(nowdate()) > getdate(self.expected_return_date):
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

		if self.get("sales_invoice") and frappe.db.exists("Sales Invoice", self.sales_invoice):
			if cint(frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus")) == 1:
				links.append("{0} {1}".format("Sales Invoice", self.sales_invoice))

		for fieldname, doctype in (
			("settlement_stock_entry", "Stock Entry"),
			("settlement_delivery_note", "Delivery Note"),
			("settlement_return_delivery_note", "Delivery Note"),
		):
			name = self.get(fieldname)
			if is_submitted_document(doctype, name):
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
	validate_no_settlement_in_progress(loan_order)

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
	validate_no_settlement_in_progress(loan_order)

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
	validate_no_settlement_in_progress(loan_order)

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
	validate_no_settlement_in_progress(loan_order)

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
def make_outward_delivery_note_for_mapping(source_name, target_doc=None):
	return make_delivery_note_for_mapping(source_name, target_doc, LOAN_MOVEMENT_OUTWARD)


@frappe.whitelist()
def make_return_delivery_note_for_mapping(source_name, target_doc=None):
	return make_delivery_note_for_mapping(source_name, target_doc, LOAN_MOVEMENT_RETURN)


def make_delivery_note_for_mapping(source_name, target_doc, movement):
	loan_order = get_submitted_loan_order(source_name)
	validate_no_settlement_in_progress(loan_order)
	delivery_note = get_target_delivery_note(target_doc)

	validate_delivery_note_mapping_source(loan_order, movement, delivery_note)
	validate_delivery_note_mapping_target(delivery_note, loan_order, movement)

	loan_order.validate_neutral_stock_accounts(movement)
	populate_delivery_note_from_loan_order(delivery_note, loan_order, movement)
	return delivery_note


@frappe.whitelist()
def refresh_loan_order_status(source_name):
	loan_order = frappe.get_doc("Loan Order", source_name)
	loan_order.check_permission("read")
	loan_order.sync_status(update=True)
	return {"status": loan_order.status}


@frappe.whitelist()
def make_settlement_sales_invoice(source_name, billing_decision, selling_price_list=None):
	loan_order = get_submitted_loan_order(source_name)
	validate_loan_order_can_be_invoiced(loan_order, billing_decision)

	existing = get_active_linked_document(loan_order, "sales_invoice", "Sales Invoice")
	if existing:
		return existing

	price_list = selling_price_list or loan_order.selling_price_list
	validate_selling_price_list(loan_order, price_list)
	validate_settlement_warehouse(loan_order)
	loan_order.sync_status(update=False)
	lines = build_loan_billing_plan(loan_order, billing_decision, price_list)
	if not lines:
		frappe.throw(_("The selected billing decision does not produce any invoice lines."))

	settlement_documents = get_reusable_settlement_stock_documents(loan_order, billing_decision)
	if not settlement_documents:
		settlement_documents = create_settlement_stock_documents(
			loan_order, billing_decision, price_list, lines
		)
	sales_invoice = build_settlement_invoice(loan_order, billing_decision, price_list, lines)
	sales_invoice.insert()

	persist_loan_billing_snapshots(loan_order)
	loan_order.db_set("selling_price_list", price_list, update_modified=False)
	loan_order.db_set("billing_decision", billing_decision, update_modified=False)
	loan_order.db_set("billing_status", "Draft Invoice", update_modified=False)
	loan_order.db_set("sales_invoice", sales_invoice.name, update_modified=False)
	for fieldname, document in settlement_documents.items():
		loan_order.db_set(fieldname, document.name, update_modified=False)
	return {
		"doctype": "Sales Invoice",
		"name": sales_invoice.name,
		"documents": [
			{"doctype": document.doctype, "name": document.name}
			for document in settlement_documents.values()
		],
	}


def create_settlement_stock_documents(loan_order, billing_decision, price_list, invoice_lines):
	if billing_decision == LOAN_BILLING_PURCHASE:
		delivery_note = build_full_purchase_delivery_note(loan_order, price_list)
		delivery_note.insert()
		return {"settlement_delivery_note": delivery_note}

	repack = build_spare_settlement_repack(loan_order)
	repack.insert()
	# Batch-controlled spares do not exist as independent stock until this
	# value-neutral dismantling is posted. Submit it first so ERPNext can validate
	# the recovered batches while creating the draft spare-parts Delivery Note.
	repack.submit()
	spare_delivery_note = build_spare_sale_delivery_note(loan_order, price_list, invoice_lines, repack)
	spare_delivery_note.insert()
	return_delivery_note = build_remaining_items_return_delivery_note(loan_order, price_list, repack)
	return_delivery_note.insert()
	return {
		"settlement_stock_entry": repack,
		"settlement_delivery_note": spare_delivery_note,
		"settlement_return_delivery_note": return_delivery_note,
	}


def get_reusable_settlement_stock_documents(loan_order, billing_decision):
	all_specs = {
		"settlement_stock_entry": ("Stock Entry", LOAN_SETTLEMENT_REPACK),
		"settlement_delivery_note": (
			"Delivery Note",
			LOAN_SETTLEMENT_FULL_SALE if billing_decision == LOAN_BILLING_PURCHASE
			else LOAN_SETTLEMENT_SPARE_SALE,
		),
		"settlement_return_delivery_note": ("Delivery Note", LOAN_SETTLEMENT_RETURN),
	}
	expected_fields = {"settlement_delivery_note"}
	if billing_decision == LOAN_BILLING_SPARES:
		expected_fields.update({"settlement_stock_entry", "settlement_return_delivery_note"})

	active = {}
	for fieldname, (doctype, settlement_type) in all_specs.items():
		existing = get_active_linked_document(loan_order, fieldname, doctype)
		if not existing:
			continue
		document = frappe.get_doc(doctype, existing["name"])
		active[fieldname] = document
		if fieldname not in expected_fields or document.get("loan_order_settlement_type") != settlement_type:
			frappe.throw(
				_("Existing settlement document {0} {1} belongs to another billing decision. Cancel it before changing the decision.").format(
					doctype, document.name
				)
			)

	if not active:
		return None
	missing = expected_fields.difference(active)
	if missing:
		frappe.throw(
			_("The existing settlement is incomplete. Cancel its stock documents before recreating it.")
		)
	if billing_decision == LOAN_BILLING_SPARES:
		product_by_row = {
			row.name: row.item_code
			for row in loan_order.items
			if get_commercial_role(row) == LOAN_PRODUCT_ROLE
		}
		legacy_rows = [
			row.item_code
			for row in active["settlement_stock_entry"].items
			if row.t_warehouse and product_by_row.get(row.loan_order_item) == row.item_code
		]
		if legacy_rows:
			frappe.throw(
				_("The existing Repack still outputs the full product ({0}). Cancel the settlement documents and recreate them to expose the BOM components.").format(
					", ".join(sorted(set(legacy_rows)))
				)
			)
	return {fieldname: active[fieldname] for fieldname in expected_fields}


def validate_settlement_warehouse(loan_order):
	warehouse = frappe.db.get_value(
		"Warehouse", LOAN_CLIENT_SITE_WAREHOUSE, ["company", "is_group"], as_dict=True
	)
	if not warehouse:
		frappe.throw(_("Warehouse {0} does not exist.").format(LOAN_CLIENT_SITE_WAREHOUSE))
	if warehouse.company != loan_order.company:
		frappe.throw(
			_("Warehouse {0} does not belong to Company {1}.").format(
				LOAN_CLIENT_SITE_WAREHOUSE, loan_order.company
			)
		)
	if cint(warehouse.is_group):
		frappe.throw(_("Warehouse {0} cannot be a group warehouse.").format(LOAN_CLIENT_SITE_WAREHOUSE))


def build_spare_settlement_repack(loan_order):
	repack = frappe.new_doc("Stock Entry")
	repack.company = loan_order.company
	repack.purpose = "Repack"
	repack.posting_date = nowdate()
	repack.posting_time = nowtime()
	repack.set_posting_time = 1
	repack.from_warehouse = LOAN_CLIENT_SITE_WAREHOUSE
	repack.to_warehouse = LOAN_CLIENT_SITE_WAREHOUSE
	repack.remarks = _("Dismantle loan products for spare-parts settlement {0}").format(loan_order.name)
	set_if_has_field(repack, "loan_order", loan_order.name)
	set_if_has_field(repack, "loan_order_movement", None)
	set_if_has_field(repack, "loan_order_settlement_type", LOAN_SETTLEMENT_REPACK)
	set_if_has_field(repack, "ignore_rate_calculation", 1)
	if hasattr(repack, "set_stock_entry_type"):
		repack.set_stock_entry_type()

	allocations = []
	for row in loan_order.items:
		if get_commercial_role(row) != LOAN_PRODUCT_ROLE:
			continue
		product_qty = max(flt(row.remaining_qty), 0)
		if product_qty <= 0:
			continue
		product_stock_qty = product_qty * (flt(row.conversion_factor) or 1)
		validate_client_site_stock(row.item_code, product_stock_qty)
		valuation_rate = flt(frappe.db.get_value(
			"Bin",
			{"item_code": row.item_code, "warehouse": LOAN_CLIENT_SITE_WAREHOUSE},
			"valuation_rate",
		))
		if valuation_rate <= 0:
			frappe.throw(
				_("Item {0} has no positive valuation rate in {1}.").format(
					row.item_code, LOAN_CLIENT_SITE_WAREHOUSE
				)
			)

		input_row = repack.append("items", {
			"item_code": row.item_code,
			"item_name": row.item_name,
			"description": row.description,
			"s_warehouse": LOAN_CLIENT_SITE_WAREHOUSE,
			"qty": product_qty,
			"uom": row.uom,
			"stock_uom": row.stock_uom,
			"conversion_factor": row.conversion_factor,
			"transfer_qty": product_stock_qty,
			"basic_rate": valuation_rate,
			"basic_amount": product_stock_qty * valuation_rate,
			"serial_no": row.serial_no,
			"batch_no": row.batch_no,
		})
		set_if_has_field(input_row, "loan_order_item", row.name)

		bom_name = row.billing_bom or get_default_product_bom(row.item_code)
		components = get_direct_bom_components(bom_name)
		component_weight = sum(
			flt(component.valuation_weight_per_stock_unit) for component in components
		)
		if component_weight <= 0:
			frappe.throw(_("BOM {0} has no positive component value.").format(bom_name))

		for component in components:
			component_qty = product_stock_qty * flt(component.qty_per_stock_unit)
			component_stock_qty = product_stock_qty * flt(component.stock_qty_per_stock_unit)
			if component_qty <= 0 or component_stock_qty <= 0:
				continue
			batch_no = get_or_create_recovery_batch(loan_order.name, component.item_code)
			serial_no = get_recovery_serial_nos(
				loan_order.name,
				row.name,
				component.item_code,
				component_stock_qty,
			)
			allocations.append(frappe._dict({
				"item_code": component.item_code,
				"item_name": component.item_name,
				"description": append_description_note(
					component.description,
					_("Recovered from loan product {0}.").format(row.item_code),
				),
				"qty": component_qty,
				"uom": component.uom,
				"stock_uom": component.stock_uom,
				"conversion_factor": component.conversion_factor,
				"transfer_qty": component_stock_qty,
				"allocated_amount": (
					product_stock_qty * valuation_rate
					* flt(component.valuation_weight_per_stock_unit)
					/ component_weight
				),
				"loan_order_item": row.name,
				"serial_no": serial_no,
				"batch_no": batch_no,
			}))

	if not allocations:
		frappe.throw(_("There are no outstanding product quantities to dismantle."))

	total_allocated = sum(flt(row.allocated_amount) for row in allocations)
	for allocation in allocations:
		share = flt(allocation.allocated_amount) / total_allocated
		basic_rate = flt(allocation.allocated_amount) / flt(allocation.transfer_qty)
		child = repack.append("items", {
			"item_code": allocation.item_code,
			"item_name": allocation.item_name,
			"description": allocation.description,
			"t_warehouse": LOAN_CLIENT_SITE_WAREHOUSE,
			"qty": allocation.qty,
			"uom": allocation.uom,
			"stock_uom": allocation.stock_uom,
			"conversion_factor": allocation.conversion_factor,
			"transfer_qty": allocation.transfer_qty,
			"basic_rate": basic_rate,
			"basic_amount": allocation.allocated_amount,
			"valuation_rate": basic_rate,
			"serial_no": allocation.serial_no,
			"batch_no": allocation.batch_no,
		})
		set_if_has_field(child, "loan_order_item", allocation.loan_order_item)
		set_if_has_field(child, "loan_settlement_valuation_share", share)

	prepare_loan_settlement_repack(repack)
	return repack


def validate_client_site_stock(item_code, required_qty):
	actual_qty = flt(frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": LOAN_CLIENT_SITE_WAREHOUSE}, "actual_qty"
	))
	if actual_qty < required_qty:
		frappe.throw(
			_("{0} has only {1} in {2}; {3} is required for settlement.").format(
				item_code, actual_qty, LOAN_CLIENT_SITE_WAREHOUSE, required_qty
			)
		)


def get_or_create_recovery_batch(loan_order_name, item_code):
	if not cint(frappe.db.get_value("Item", item_code, "has_batch_no")):
		return None
	batch_id = "REC-{0}-{1}".format(loan_order_name, item_code)
	if not frappe.db.exists("Batch", batch_id):
		frappe.get_doc({
			"doctype": "Batch",
			"batch_id": batch_id,
			"item": item_code,
		}).insert()
	return batch_id


def get_recovery_serial_nos(loan_order_name, loan_order_item, item_code, stock_qty):
	if not cint(frappe.db.get_value("Item", item_code, "has_serial_no")):
		return None

	serial_count = cint(stock_qty)
	if abs(flt(stock_qty) - serial_count) > 0.000001:
		frappe.throw(
			_("Serial-controlled BOM component {0} requires a whole-number quantity, not {1}.").format(
				item_code, stock_qty
			)
		)

	row_key = (loan_order_item or "ROW")[-8:]
	serial_nos = []
	for index in range(1, serial_count + 1):
		serial_no = "REC-{0}-{1}-{2}-{3:03d}".format(
			loan_order_name, row_key, item_code, index
		)
		existing = frappe.db.get_value(
			"Serial No", serial_no, ["item_code", "warehouse"], as_dict=True
		)
		if existing and existing.item_code != item_code:
			frappe.throw(
				_("Recovered Serial No {0} already belongs to Item {1}.").format(
					serial_no, existing.item_code
				)
			)
		if existing and existing.warehouse:
			frappe.throw(
				_("Recovered Serial No {0} is already in Warehouse {1}.").format(
					serial_no, existing.warehouse
				)
			)
		serial_nos.append(serial_no)
	return "\n".join(serial_nos)


def prepare_loan_settlement_repack(doc, method=None):
	if doc.get("loan_order_settlement_type") != LOAN_SETTLEMENT_REPACK:
		return

	outgoing_rows = [row for row in doc.items if row.s_warehouse and not row.t_warehouse]
	incoming_rows = [row for row in doc.items if row.t_warehouse and not row.s_warehouse]
	total_outgoing = sum(flt(row.basic_amount) for row in outgoing_rows)
	if total_outgoing <= 0 or not incoming_rows:
		frappe.throw(_("Loan settlement Repack requires valued outgoing products and incoming items."))

	total_share = sum(flt(row.get("loan_settlement_valuation_share")) for row in incoming_rows)
	if abs(total_share - 1) > 0.0001:
		frappe.throw(_("Loan settlement Repack valuation shares must total 100%."))

	allocated = 0
	for index, row in enumerate(incoming_rows):
		if index == len(incoming_rows) - 1:
			basic_amount = total_outgoing - allocated
		else:
			basic_amount = total_outgoing * flt(row.loan_settlement_valuation_share)
			allocated += basic_amount
		row.basic_amount = basic_amount
		row.basic_rate = basic_amount / (flt(row.transfer_qty) or 1)
		row.valuation_rate = row.basic_rate
		row.amount = basic_amount
		row.additional_cost = 0

	doc.total_outgoing_value = total_outgoing
	doc.total_incoming_value = sum(flt(row.basic_amount) for row in incoming_rows)
	doc.value_difference = doc.total_incoming_value - doc.total_outgoing_value
	doc.total_amount = sum(flt(row.amount) for row in doc.items)


def persist_loan_billing_snapshots(loan_order):
	for row in loan_order.items:
		if not row.billing_bom and not row.component_summary:
			continue
		frappe.db.set_value(
			"Loan Order Item",
			row.name,
			{
				"billing_bom": row.billing_bom,
				"component_summary": row.component_summary,
			},
			update_modified=False,
		)


def validate_loan_order_can_be_invoiced(loan_order, billing_decision):
	if loan_order.party_type != "Customer":
		frappe.throw(_("Only customer Loan Orders can create a Sales Invoice."))
	if billing_decision not in LOAN_BILLING_DECISIONS:
		frappe.throw(_("Select Spare Parts Only or Full Product Purchase."))
	if not any(flt(row.loaned_qty) > 0 for row in loan_order.items):
		frappe.throw(_("Submit an outward stock movement before creating the settlement invoice."))
	for fieldname, doctype in (
		("return_stock_entry", "Stock Entry"),
		("return_delivery_note", "Delivery Note"),
	):
		name = loan_order.get(fieldname)
		if name and frappe.db.exists(doctype, name):
			if cint(frappe.db.get_value(doctype, name, "docstatus")) == 0:
				frappe.throw(
					_("Submit or cancel draft {0} {1} before creating the settlement.").format(
						doctype, name
					)
				)


def validate_selling_price_list(loan_order, price_list):
	if not price_list:
		frappe.throw(_("Select a Selling Price List before creating the settlement invoice."))

	price_list_details = frappe.db.get_value(
		"Price List", price_list, ["enabled", "selling", "currency"], as_dict=True
	)
	if not price_list_details or not cint(price_list_details.enabled) or not cint(price_list_details.selling):
		frappe.throw(_("Price List {0} must be an enabled selling price list.").format(price_list))
	if price_list_details.currency != loan_order.currency:
		frappe.throw(
			_("Price List {0} uses {1}, but Loan Order {2} uses {3}.").format(
				price_list, price_list_details.currency, loan_order.name, loan_order.currency
			)
		)


def build_loan_billing_plan(loan_order, billing_decision, price_list):
	lines = []
	remaining_lines = []
	missing_prices = []
	transaction_date = nowdate()

	for row in loan_order.items:
		role = get_commercial_role(row)
		if role == LOAN_EXCLUDED_ROLE:
			continue

		if role == LOAN_PRODUCT_ROLE:
			product_lines, product_missing = build_product_billing_lines(
				loan_order, row, billing_decision, price_list, transaction_date
			)
			lines.extend(product_lines)
			missing_prices.extend(product_missing)
			continue

		if role == LOAN_SPARE_ROLE:
			qty = get_direct_item_billing_qty(row, billing_decision)
			if qty > 0:
				line, missing = make_priced_billing_line(
					loan_order, row.item_code, qty, row.uom, price_list, transaction_date,
					row.name, LOAN_SPARE_ROLE, row.description
				)
				if line:
					lines.append(line)
				if missing:
					missing_prices.append(missing)
			continue

		if role == LOAN_OTHER_ROLE and billing_decision == LOAN_BILLING_PURCHASE:
			qty = max(flt(row.remaining_qty), 0)
			if qty > 0:
				line, missing = make_priced_billing_line(
					loan_order, row.item_code, qty, row.uom, price_list, transaction_date,
					row.name, LOAN_OTHER_ROLE, row.description
				)
				if line:
					remaining_lines.append(line)
				if missing:
					missing_prices.append(missing)

	if missing_prices:
		frappe.throw(
			_("Add a positive Item Price in {0} for: {1}").format(
				price_list, ", ".join(sorted(set(missing_prices)))
			)
		)

	if billing_decision == LOAN_BILLING_PURCHASE:
		if not any(line.billing_role == LOAN_PRODUCT_ROLE for line in lines):
			frappe.throw(_("There is no outstanding product quantity to sell on this Loan Order."))

	lines.extend(remaining_lines)
	return lines


def build_product_billing_lines(loan_order, row, billing_decision, price_list, transaction_date):
	product_qty = get_product_billing_qty(row, billing_decision)
	if product_qty <= 0:
		return [], []

	bom_name = row.billing_bom or get_default_product_bom(row.item_code)
	if not bom_name:
		frappe.throw(
			_("Row {0}: Product {1} needs an active submitted BOM for loan billing.").format(
				row.idx, row.item_code
			)
		)

	components = get_direct_bom_components(bom_name, LOAN_SPARE_COMPONENT_GROUPS)
	component_lines = []
	missing_prices = []
	spare_value_per_product_uom = 0
	product_conversion_factor = flt(row.conversion_factor) or 1

	for component in components:
		component_qty = product_qty * product_conversion_factor * flt(component.qty_per_stock_unit)
		component_rate = get_selling_rate(
			component.item_code,
			component.uom,
			component_qty,
			price_list,
			loan_order.party,
			transaction_date,
		)
		if component_rate is None:
			missing_prices.append(component.item_code)
			continue

		spare_value_per_product_uom += (
			product_conversion_factor * flt(component.qty_per_stock_unit) * component_rate
		)
		component_lines.append(
			make_billing_line(
				component.item_code,
				component.item_name,
				component.description,
				component_qty,
				component.uom,
				component.conversion_factor,
				component_rate,
				row.name,
				LOAN_SPARE_ROLE,
			)
		)

	if billing_decision == LOAN_BILLING_SPARES:
		return component_lines, missing_prices

	product_rate = get_selling_rate(
		row.item_code, row.uom, product_qty, price_list, loan_order.party, transaction_date
	)
	if product_rate is None:
		missing_prices.append(row.item_code)
		return component_lines, missing_prices

	residual_rate = get_product_residual_rate(product_rate, spare_value_per_product_uom, row.item_code)
	product_description = append_description_note(
		row.description,
		_("Product price excluding the spare parts itemized below."),
	)
	product_line = make_billing_line(
		row.item_code,
		row.item_name,
		product_description,
		product_qty,
		row.uom,
		row.conversion_factor,
		residual_rate,
		row.name,
		LOAN_PRODUCT_ROLE,
		price_list_rate=product_rate,
		discount_amount=spare_value_per_product_uom,
	)
	return [product_line] + component_lines, missing_prices


def get_product_residual_rate(product_rate, spare_value, item_code):
	residual_rate = flt(product_rate) - flt(spare_value)
	if residual_rate < 0:
		frappe.throw(
			_("The spare-parts price {0} exceeds the full price {1} for product {2}.").format(
				frappe.format_value(spare_value, {"fieldtype": "Currency"}),
				frappe.format_value(product_rate, {"fieldtype": "Currency"}),
				item_code,
			)
		)
	return residual_rate


def get_product_billing_qty(row, billing_decision):
	return max(flt(row.remaining_qty), 0)


def get_direct_item_billing_qty(row, billing_decision):
	return max(flt(row.remaining_qty), 0)


def make_priced_billing_line(loan_order, item_code, qty, uom, price_list, transaction_date,
		loan_order_item, billing_role, description=None):
	rate = get_selling_rate(item_code, uom, qty, price_list, loan_order.party, transaction_date)
	if rate is None:
		return None, item_code

	item = frappe.db.get_value(
		"Item", item_code, ["item_name", "description", "stock_uom"], as_dict=True
	)
	conversion_factor = get_conversion_factor(item_code, uom).get("conversion_factor") or 1
	return make_billing_line(
		item_code,
		item.item_name,
		description or item.description,
		qty,
		uom or item.stock_uom,
		conversion_factor,
		rate,
		loan_order_item,
		billing_role,
	), None


def make_billing_line(item_code, item_name, description, qty, uom, conversion_factor, rate,
		loan_order_item, billing_role, price_list_rate=None, discount_amount=0):
	return frappe._dict({
		"item_code": item_code,
		"item_name": item_name,
		"description": description,
		"qty": qty,
		"uom": uom,
		"conversion_factor": flt(conversion_factor) or 1,
		"rate": rate,
		"price_list_rate": price_list_rate if price_list_rate is not None else rate,
		"discount_amount": discount_amount,
		"loan_order_item": loan_order_item,
		"billing_role": billing_role,
	})


def get_selling_rate(item_code, uom, qty, price_list, customer, transaction_date):
	prices = get_item_price(
		{
			"price_list": price_list,
			"customer": customer,
			"uom": uom,
			"min_qty": qty,
			"transaction_date": transaction_date,
		},
		item_code,
	)
	for price in prices or []:
		if flt(price[1]) > 0:
			rate = flt(price[1])
			if price[2] != uom and not get_price_list_uom_dependant(price_list):
				rate *= flt(get_conversion_factor(item_code, uom).get("conversion_factor")) or 1
			return rate
	return None


def build_settlement_invoice(loan_order, billing_decision, price_list, lines):
	sales_invoice = frappe.new_doc("Sales Invoice")
	sales_invoice.company = loan_order.company
	sales_invoice.customer = loan_order.party
	sales_invoice.posting_date = nowdate()
	sales_invoice.currency = loan_order.currency
	sales_invoice.selling_price_list = price_list
	sales_invoice.price_list_currency = get_price_list_currency(price_list)
	sales_invoice.ignore_pricing_rule = 1
	sales_invoice.update_stock = 0
	sales_invoice.remarks = _("Loan settlement for {0}: {1}").format(loan_order.name, billing_decision)
	if meta_has_field("Customer", "accounting_email"):
		set_if_has_field(
			sales_invoice,
			"accounting_email_invoice",
			frappe.db.get_value("Customer", loan_order.party, "accounting_email"),
		)
	set_if_has_field(sales_invoice, "loan_order", loan_order.name)
	set_if_has_field(sales_invoice, "loan_order_billing_decision", billing_decision)

	invoice_rows = []
	for line in lines:
		child = sales_invoice.append("items", {
			"item_code": line.item_code,
			"item_name": line.item_name,
			"description": line.description,
			"qty": line.qty,
			"uom": line.uom,
			"conversion_factor": line.conversion_factor,
			"rate": line.rate,
			"price_list_rate": line.price_list_rate,
			"discount_amount": line.discount_amount,
		})
		set_if_has_field(child, "loan_order_item", line.loan_order_item)
		set_if_has_field(child, "loan_order_billing_role", line.billing_role)
		invoice_rows.append((child, line))

	sales_invoice.run_method("set_missing_values")
	for child, line in invoice_rows:
		# Preserve the deliberate product/spare split after ERPNext has populated accounts and taxes.
		child.rate = line.rate
		child.price_list_rate = line.price_list_rate
		child.discount_percentage = 0
		child.discount_amount = line.discount_amount
	sales_invoice.run_method("calculate_taxes_and_totals")
	return sales_invoice


def build_full_purchase_delivery_note(loan_order, price_list):
	rows = []
	missing_prices = []
	for row in loan_order.items:
		role = get_commercial_role(row)
		qty = max(flt(row.remaining_qty), 0)
		if qty <= 0 or role == LOAN_EXCLUDED_ROLE:
			continue

		rate = get_selling_rate(row.item_code, row.uom, qty, price_list, loan_order.party, nowdate())
		if rate is None:
			missing_prices.append(row.item_code)
			continue
		description = row.description
		if role == LOAN_PRODUCT_ROLE:
			description = append_delivery_component_summary(
				description, row.component_summary or get_delivery_component_summary(row)
			)
		rows.append(make_settlement_stock_line(
			row.item_code,
			row.item_name,
			description,
			qty,
			row.uom,
			row.conversion_factor,
			rate,
			row.name,
			serial_no=row.serial_no,
			batch_no=row.batch_no,
		))

	throw_for_missing_prices(price_list, missing_prices)
	if not rows:
		frappe.throw(_("There are no outstanding items to deliver for this Loan Order."))
	return build_settlement_delivery_note(
		loan_order, price_list, rows, LOAN_SETTLEMENT_FULL_SALE, is_return=False
	)


def build_spare_sale_delivery_note(loan_order, price_list, invoice_lines, repack):
	recovered_map = {
		(row.loan_order_item, row.item_code): row
		for row in repack.items
		if row.t_warehouse
	}
	rows = []
	for line in invoice_lines:
		if line.billing_role != LOAN_SPARE_ROLE:
			continue
		loan_row = get_loan_order_row(loan_order, line.loan_order_item)
		recovered_row = recovered_map.get((line.loan_order_item, line.item_code))
		batch_no = recovered_row.batch_no if recovered_row else None
		serial_no = recovered_row.serial_no if recovered_row else None
		if loan_row and loan_row.item_code == line.item_code:
			batch_no = batch_no or loan_row.batch_no
			serial_no = serial_no or loan_row.serial_no
		rows.append(make_settlement_stock_line(
			line.item_code,
			line.item_name,
			line.description,
			line.qty,
			line.uom,
			line.conversion_factor,
			line.rate,
			line.loan_order_item,
			serial_no=serial_no,
			batch_no=batch_no,
		))

	if not rows:
		frappe.throw(_("The BOMs do not contain any Valve Head or Syringe items to deliver."))
	return build_settlement_delivery_note(
		loan_order, price_list, rows, LOAN_SETTLEMENT_SPARE_SALE, is_return=False
	)


def build_remaining_items_return_delivery_note(loan_order, price_list, repack):
	rows = []
	for row in loan_order.items:
		role = get_commercial_role(row)
		qty = max(flt(row.remaining_qty), 0)
		if qty <= 0 or role in (LOAN_EXCLUDED_ROLE, LOAN_SPARE_ROLE):
			continue

		if role == LOAN_PRODUCT_ROLE:
			component_rows = [
				component for component in repack.items
				if component.t_warehouse
				and component.loan_order_item == row.name
				and not is_spare_component_item(component.item_code)
			]
			if not component_rows:
				frappe.throw(
					_("Repack {0} has no returnable BOM components for product {1}.").format(
						repack.name, row.item_code
					)
				)

			product_rate = get_selling_rate(
				row.item_code, row.uom, qty, price_list, loan_order.party, nowdate()
			)
			spare_value = get_product_spare_selling_value_per_uom(loan_order, row, price_list)
			if product_rate is None:
				product_rate = flt(row.declared_rate) + spare_value
			residual_rate = get_product_residual_rate(product_rate, spare_value, row.item_code)
			remaining_component_value = sum(flt(component.basic_amount) for component in component_rows)
			if remaining_component_value <= 0:
				frappe.throw(
					_("Returnable BOM components for product {0} have no valuation.").format(row.item_code)
				)

			residual_amount = qty * residual_rate
			allocated_amount = 0
			for index, component in enumerate(component_rows):
				if index == len(component_rows) - 1:
					component_amount = residual_amount - allocated_amount
				else:
					component_amount = (
						residual_amount * flt(component.basic_amount) / remaining_component_value
					)
					allocated_amount += component_amount
				component_rate = component_amount / (flt(component.qty) or 1)
				rows.append(make_settlement_stock_line(
					component.item_code,
					component.item_name,
					component.description,
					component.qty,
					component.uom,
					component.conversion_factor,
					component_rate,
					row.name,
					serial_no=component.serial_no,
					batch_no=component.batch_no,
					return_warehouse=row.return_warehouse,
				))
			continue

		rate = get_selling_rate(row.item_code, row.uom, qty, price_list, loan_order.party, nowdate())
		if rate is None:
			# This is a physical, non-commercial return, so the original declared
			# value is a safe fallback for an accessory without a current Item Price.
			rate = flt(row.declared_rate)
		rows.append(make_settlement_stock_line(
			row.item_code,
			row.item_name,
			row.description,
			qty,
			row.uom,
			row.conversion_factor,
			rate,
			row.name,
			serial_no=row.serial_no,
			batch_no=row.batch_no,
			return_warehouse=row.return_warehouse,
		))

	if not rows:
		frappe.throw(_("There are no product or accessory quantities to return."))
	return build_settlement_delivery_note(
		loan_order, price_list, rows, LOAN_SETTLEMENT_RETURN, is_return=True
	)


def is_spare_component_item(item_code):
	return frappe.db.get_value("Item", item_code, "item_group") in LOAN_SPARE_COMPONENT_GROUPS


def prepare_loan_settlement_delivery_note_validation(doc, method=None):
	if doc.get("loan_order_settlement_type") != LOAN_SETTLEMENT_RETURN:
		return

	# ERPNext V12's SellingController rejects any non-sales Item on a Delivery
	# Note. An internal loan return must be able to transfer BOM bodies, screws,
	# and other recovered stock items without changing their global Item masters.
	doc.validate_items = lambda: None


def build_settlement_delivery_note(loan_order, price_list, rows, settlement_type, is_return=False):
	delivery_note = frappe.new_doc("Delivery Note")
	delivery_note.company = loan_order.company
	delivery_note.customer = loan_order.party
	delivery_note.currency = loan_order.currency
	delivery_note.selling_price_list = price_list
	delivery_note.posting_date = nowdate()
	delivery_note.posting_time = nowtime()
	delivery_note.set_posting_time = 1
	delivery_note.ignore_pricing_rule = 1
	# For the settlement return, use a positive warehouse transfer DN. ERPNext V12
	# assigns a negative Return DN's incoming value from the destination warehouse
	# when return_against is empty, which can create false COGS. A positive transfer
	# carries the exact Client Site valuation into the return warehouse instead.
	delivery_note.is_return = 0
	delivery_note.issue_credit_note = 0
	delivery_note.remarks = _("Loan settlement for {0}: {1}").format(loan_order.name, settlement_type)
	set_if_has_field(delivery_note, "loan_order", loan_order.name)
	set_if_has_field(delivery_note, "loan_order_movement", None)
	set_if_has_field(delivery_note, "loan_order_settlement_type", settlement_type)
	set_if_has_field(delivery_note, "object", LOAN_DN_OBJECT)

	delivery_rows = []
	for line in rows:
		qty = flt(line.qty)
		warehouse = LOAN_CLIENT_SITE_WAREHOUSE
		target_warehouse = None
		if is_return:
			warehouse = LOAN_CLIENT_SITE_WAREHOUSE
			target_warehouse = line.return_warehouse
		child = delivery_note.append("items", {
			"item_code": line.item_code,
			"item_name": line.item_name,
			"description": line.description,
			"qty": qty,
			"uom": line.uom,
			"conversion_factor": line.conversion_factor,
			"stock_qty": qty * flt(line.conversion_factor),
			"rate": line.rate,
			"price_list_rate": line.rate,
			"warehouse": warehouse,
			"target_warehouse": target_warehouse,
			"serial_no": line.serial_no,
			"batch_no": line.batch_no,
		})
		set_if_has_field(child, "loan_order_item", line.loan_order_item)
		delivery_rows.append((child, line))

	delivery_note.run_method("set_missing_values")
	for child, line in delivery_rows:
		child.rate = line.rate
		child.price_list_rate = line.rate
		child.discount_percentage = 0
		child.discount_amount = 0
	delivery_note.run_method("calculate_taxes_and_totals")
	return delivery_note


def make_settlement_stock_line(item_code, item_name, description, qty, uom, conversion_factor,
		rate, loan_order_item, serial_no=None, batch_no=None, return_warehouse=None):
	return frappe._dict({
		"item_code": item_code,
		"item_name": item_name,
		"description": description,
		"qty": qty,
		"uom": uom,
		"conversion_factor": flt(conversion_factor) or 1,
		"rate": rate,
		"loan_order_item": loan_order_item,
		"serial_no": serial_no,
		"batch_no": batch_no,
		"return_warehouse": return_warehouse,
	})


def get_product_spare_selling_value_per_uom(loan_order, row, price_list):
	bom_name = row.billing_bom or get_default_product_bom(row.item_code)
	components = get_direct_bom_components(bom_name, LOAN_SPARE_COMPONENT_GROUPS)
	product_conversion_factor = flt(row.conversion_factor) or 1
	spare_value = 0
	missing_prices = []
	for component in components:
		component_rate = get_selling_rate(
			component.item_code,
			component.uom,
			product_conversion_factor * flt(component.qty_per_stock_unit),
			price_list,
			loan_order.party,
			nowdate(),
		)
		if component_rate is None:
			missing_prices.append(component.item_code)
			continue
		spare_value += product_conversion_factor * flt(component.qty_per_stock_unit) * component_rate
	throw_for_missing_prices(price_list, missing_prices)
	return spare_value


def throw_for_missing_prices(price_list, item_codes):
	if item_codes:
		frappe.throw(
			_("Add a positive Item Price in {0} for: {1}").format(
				price_list, ", ".join(sorted(set(item_codes)))
			)
		)


def get_loan_order_row(loan_order, row_name):
	for row in loan_order.items:
		if row.name == row_name:
			return row
	return None


def validate_loan_order_sales_invoice(doc, method=None):
	loan_order_name = doc.get("loan_order")
	if not loan_order_name:
		return
	if not frappe.db.exists("Loan Order", loan_order_name):
		frappe.throw(_("Loan Order {0} does not exist.").format(loan_order_name))

	loan_order = frappe.get_doc("Loan Order", loan_order_name)
	if loan_order.docstatus != 1:
		frappe.throw(_("Loan Order {0} must be submitted.").format(loan_order_name))
	if loan_order.party_type != "Customer" or loan_order.party != doc.customer:
		frappe.throw(_("Sales Invoice customer must match Loan Order {0}.").format(loan_order_name))
	if loan_order.company != doc.company:
		frappe.throw(_("Sales Invoice company must match Loan Order {0}.").format(loan_order_name))

	existing = get_active_linked_document(loan_order, "sales_invoice", "Sales Invoice")
	if existing and existing.get("name") != doc.name:
		frappe.throw(_("Sales Invoice {0} is already linked to this Loan Order.").format(existing["name"]))

	if getattr(doc, "_action", None) == "submit":
		required_documents = [
			("Delivery Note", loan_order.get("settlement_delivery_note"), _("settlement Delivery Note")),
		]
		if loan_order.get("billing_decision") == LOAN_BILLING_SPARES:
			required_documents.extend([
				("Stock Entry", loan_order.get("settlement_stock_entry"), _("product dismantling Stock Entry")),
				("Delivery Note", loan_order.get("settlement_return_delivery_note"), _("remaining-items return Delivery Note")),
			])
		for doctype, name, label in required_documents:
			if not is_submitted_document(doctype, name):
				frappe.throw(
					_("Submit the {0} before submitting this Sales Invoice.").format(label)
				)


def update_linked_loan_order_invoice(doc, method=None):
	loan_order_name = doc.get("loan_order")
	if not loan_order_name or not frappe.db.exists("Loan Order", loan_order_name):
		return

	loan_order = frappe.get_doc("Loan Order", loan_order_name)
	if method in ("on_cancel", "on_trash") or cint(doc.docstatus) == 2:
		if loan_order.sales_invoice == doc.name:
			frappe.db.set_value(
				"Loan Order",
				loan_order.name,
				{
					"sales_invoice": None,
					"billing_decision": LOAN_BILLING_PENDING,
					"billing_status": LOAN_BILLING_PENDING,
				},
				update_modified=False,
			)
			loan_order.set("sales_invoice", None)
			loan_order.set("billing_decision", LOAN_BILLING_PENDING)
			loan_order.set("billing_status", LOAN_BILLING_PENDING)
			loan_order.sync_status(update=True)
		return

	decision = doc.get("loan_order_billing_decision") or loan_order.billing_decision
	status = "Invoiced" if cint(doc.docstatus) == 1 else "Draft Invoice"
	frappe.db.set_value(
		"Loan Order",
		loan_order.name,
		{
			"sales_invoice": doc.name,
			"billing_decision": decision,
			"billing_status": status,
		},
		update_modified=False,
	)
	loan_order.set("sales_invoice", doc.name)
	loan_order.set("billing_decision", decision)
	loan_order.set("billing_status", status)
	loan_order.sync_status(update=True)


def update_linked_loan_order(doc, method=None):
	if method in ("on_cancel", "on_trash") or cint(doc.docstatus) == 2:
		unlink_generated_document_from_all_loan_orders(doc)
		return

	loan_order_name = doc.get("loan_order")
	if not loan_order_name or not frappe.db.exists("Loan Order", loan_order_name):
		return

	loan_order = frappe.get_doc("Loan Order", loan_order_name)
	update_loan_order_delivery_note_link(doc, loan_order)
	loan_order.sync_status(update=True)


def get_loan_order_link_fields_for_document(doctype):
	return {
		"Delivery Note": (
			"outward_delivery_note",
			"return_delivery_note",
			"settlement_delivery_note",
			"settlement_return_delivery_note",
		),
		"Stock Entry": (
			"outward_stock_entry",
			"return_stock_entry",
			"settlement_stock_entry",
		),
	}.get(doctype, ())


def unlink_generated_document_from_all_loan_orders(doc):
	"""Find legacy or current backlinks and release them during cancel/delete."""
	loan_order_names = set()
	if doc.get("loan_order") and frappe.db.exists("Loan Order", doc.loan_order):
		loan_order_names.add(doc.loan_order)

	for fieldname in get_loan_order_link_fields_for_document(doc.doctype):
		if not frappe.db.has_column("Loan Order", fieldname):
			continue
		loan_order_names.update(
			row.name
			for row in frappe.get_all(
				"Loan Order", filters={fieldname: doc.name}, fields=["name"]
			)
		)

	for loan_order_name in loan_order_names:
		loan_order = frappe.get_doc("Loan Order", loan_order_name)
		if unlink_generated_document_from_loan_order(doc, loan_order):
			loan_order.sync_status(update=True)


def unlink_generated_document_from_loan_order(doc, loan_order):
	"""Release exact backlinks before Frappe performs its cancel/delete link check."""
	updates = {
		fieldname: None
		for fieldname in get_loan_order_link_fields_for_document(doc.doctype)
		if loan_order.meta.has_field(fieldname) and loan_order.get(fieldname) == doc.name
	}
	if not updates:
		return False

	frappe.db.set_value(
		"Loan Order", loan_order.name, updates, update_modified=False
	)
	for fieldname in updates:
		loan_order.set(fieldname, None)
	return True


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


def is_submitted_document(doctype, name):
	return bool(
		name
		and frappe.db.exists(doctype, name)
		and cint(frappe.db.get_value(doctype, name, "docstatus")) == 1
	)


def validate_no_settlement_in_progress(loan_order):
	for fieldname, doctype in (
		("sales_invoice", "Sales Invoice"),
		("settlement_stock_entry", "Stock Entry"),
		("settlement_delivery_note", "Delivery Note"),
		("settlement_return_delivery_note", "Delivery Note"),
	):
		existing = get_active_linked_document(loan_order, fieldname, doctype)
		if existing:
			frappe.throw(
				_("Loan settlement is already in progress through {0} {1}; no further loan movement can be created.").format(
					existing["doctype"], existing["name"]
				)
			)


def ensure_no_active_alternative(loan_order, fieldname, doctype):
	existing = get_active_linked_document(loan_order, fieldname, doctype)
	if existing:
		frappe.throw(_("{0} {1} is already linked to this Loan Order.").format(existing["doctype"], existing["name"]))


def get_delivery_note_link_field(movement):
	if movement == LOAN_MOVEMENT_OUTWARD:
		return "outward_delivery_note"
	if movement == LOAN_MOVEMENT_RETURN:
		return "return_delivery_note"
	return None


def update_loan_order_delivery_note_link(delivery_note, loan_order):
	if delivery_note.doctype != "Delivery Note" or cint(delivery_note.docstatus) == 2:
		return

	link_field = get_delivery_note_link_field(delivery_note.get("loan_order_movement"))
	if not link_field:
		return

	current = loan_order.get(link_field)
	if current == delivery_note.name:
		return

	if current:
		current_docstatus = frappe.db.get_value("Delivery Note", current, "docstatus")
		if current_docstatus is not None and cint(current_docstatus) != 2:
			frappe.throw(_("Delivery Note {0} is already linked to this Loan Order.").format(current))

	loan_order.db_set(link_field, delivery_note.name, update_modified=False)
	loan_order.set(link_field, delivery_note.name)


def get_target_delivery_note(target_doc=None):
	if not target_doc:
		return frappe.new_doc("Delivery Note")
	if isinstance(target_doc, string_types):
		target_doc = json.loads(target_doc)
	return frappe.get_doc(target_doc)


def validate_delivery_note_mapping_source(loan_order, movement, delivery_note):
	if movement == LOAN_MOVEMENT_OUTWARD:
		ensure_no_active_alternative(loan_order, "outward_stock_entry", "Stock Entry")
	elif movement == LOAN_MOVEMENT_RETURN:
		ensure_no_active_alternative(loan_order, "return_stock_entry", "Stock Entry")
		loan_order.sync_status(update=True)

		if not loan_order.outward_delivery_note or not frappe.db.exists("Delivery Note", loan_order.outward_delivery_note):
			frappe.throw(_("A return Delivery Note can only be created after an outward Delivery Note."))

		if cint(frappe.db.get_value("Delivery Note", loan_order.outward_delivery_note, "docstatus")) != 1:
			frappe.throw(_("Submit the outward Delivery Note before creating the return Delivery Note."))
	else:
		frappe.throw(_("Unsupported Loan Order movement {0}.").format(movement))

	existing = get_active_linked_document(loan_order, get_delivery_note_link_field(movement), "Delivery Note")
	if existing and existing.get("name") != delivery_note.get("name"):
		frappe.throw(_("Delivery Note {0} is already linked to this Loan Order.").format(existing["name"]))


def validate_delivery_note_mapping_target(delivery_note, loan_order, movement):
	if delivery_note.doctype != "Delivery Note":
		frappe.throw(_("Target document must be a Delivery Note."))

	if cint(delivery_note.docstatus) != 0:
		frappe.throw(_("Items can only be fetched into a draft Delivery Note."))

	if delivery_note.get("loan_order") and delivery_note.get("loan_order") != loan_order.name:
		frappe.throw(_("This Delivery Note is already linked to Loan Order {0}.").format(delivery_note.loan_order))

	if delivery_note.get("loan_order_movement") and delivery_note.get("loan_order_movement") != movement:
		frappe.throw(_("This Delivery Note is already marked as a {0} Loan Order movement.").format(delivery_note.loan_order_movement))

	for row in delivery_note.get("items"):
		if row.get("item_code"):
			frappe.throw(_("Select only one Loan Order per Delivery Note. Use a new Delivery Note for another source."))

	delivery_note.set("items", [])


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
	delivery_note = frappe.new_doc("Delivery Note")
	populate_delivery_note_from_loan_order(delivery_note, loan_order, movement)
	return delivery_note


def populate_delivery_note_from_loan_order(delivery_note, loan_order, movement):
	rows = get_transfer_rows(loan_order, movement)
	if not rows:
		frappe.throw(_("There are no quantities to transfer."))

	customer = get_delivery_note_customer(loan_order)
	delivery_note.company = loan_order.company
	delivery_note.customer = customer
	delivery_note.currency = loan_order.currency
	delivery_note.posting_date = delivery_note.posting_date or nowdate()
	delivery_note.posting_time = delivery_note.posting_time or nowtime()
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
	else:
		delivery_note.is_return = 0
		delivery_note.return_against = None

	for row in rows:
		source, target = get_transfer_warehouses(row, movement)
		qty = row.transfer_qty if movement == LOAN_MOVEMENT_OUTWARD else -1 * row.transfer_qty
		description = row.description
		if get_commercial_role(row) == LOAN_PRODUCT_ROLE:
			component_summary = row.component_summary or get_delivery_component_summary(row)
			description = append_delivery_component_summary(description, component_summary)
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
			"description": description,
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


def get_default_selling_price_list(customer, currency):
	candidates = [frappe.db.get_single_value("Selling Settings", "selling_price_list")]
	if customer:
		candidates.append(frappe.db.get_value("Customer", customer, "default_price_list"))

	for price_list in candidates:
		if not price_list:
			continue
		details = frappe.db.get_value(
			"Price List", price_list, ["enabled", "selling", "currency"], as_dict=True
		)
		if details and cint(details.enabled) and cint(details.selling) and details.currency == currency:
			return price_list

	price_lists = frappe.get_all(
		"Price List",
		filters={"enabled": 1, "selling": 1, "currency": currency},
		fields=["name"],
		order_by="modified desc",
		limit_page_length=1,
	)
	return price_lists[0].name if price_lists else None


def get_commercial_role(row, item=None):
	configured_role = row.get("commercial_role") or LOAN_AUTO_ROLE
	if configured_role != LOAN_AUTO_ROLE:
		return configured_role

	if item is None:
		item = frappe.db.get_value(
			"Item", row.item_code, ["item_group", "item_type"], as_dict=True
		) or frappe._dict()

	if item.item_group == "Product" or item.item_type == "Finished Good":
		return LOAN_PRODUCT_ROLE
	if item.item_group in LOAN_SPARE_COMPONENT_GROUPS:
		return LOAN_SPARE_ROLE
	return LOAN_OTHER_ROLE


def get_default_product_bom(item_code):
	boms = frappe.get_all(
		"BOM",
		filters={"item": item_code, "docstatus": 1, "is_active": 1},
		fields=["name"],
		order_by="is_default desc, modified desc",
		limit_page_length=1,
	)
	return boms[0].name if boms else None


def validate_product_bom(item_code, bom_name, row_idx=None):
	bom = frappe.db.get_value(
		"BOM", bom_name, ["item", "docstatus", "is_active"], as_dict=True
	)
	if not bom or bom.item != item_code or cint(bom.docstatus) != 1 or not cint(bom.is_active):
		prefix = _("Row {0}: ").format(row_idx) if row_idx else ""
		frappe.throw(
			_("{0}BOM {1} must be active, submitted, and made for product {2}.").format(
				prefix, bom_name, item_code
			)
		)


def get_direct_bom_components(bom_name, included_groups=None):
	"""Return the BOM rows that physically emerge when the finished product is dismantled."""
	bom = frappe.db.get_value(
		"BOM", bom_name, ["quantity", "docstatus", "is_active"], as_dict=True
	)
	if not bom or cint(bom.docstatus) != 1 or not cint(bom.is_active):
		frappe.throw(_("BOM {0} must be active and submitted.").format(bom_name))

	output_qty = flt(bom.quantity) or 1
	components = []
	rows = frappe.get_all(
		"BOM Item",
		filters={"parent": bom_name},
		fields=[
			"item_code", "item_name", "description", "qty", "stock_qty", "uom",
			"stock_uom", "conversion_factor", "rate", "amount", "idx",
		],
		order_by="idx asc",
	)
	for row in rows:
		item = frappe.db.get_value(
			"Item",
			row.item_code,
			["item_name", "description", "item_group", "stock_uom"],
			as_dict=True,
		) or frappe._dict()
		if included_groups and item.item_group not in included_groups:
			continue
		components.append(frappe._dict({
			"item_code": row.item_code,
			"item_name": row.item_name or item.item_name or row.item_code,
			"description": row.description or item.description,
			"item_group": item.item_group,
			"qty_per_stock_unit": flt(row.qty) / output_qty,
			"stock_qty_per_stock_unit": flt(row.stock_qty or row.qty) / output_qty,
			"valuation_weight_per_stock_unit": flt(row.amount) / output_qty,
			"uom": row.uom or item.stock_uom,
			"stock_uom": row.stock_uom or item.stock_uom,
			"conversion_factor": flt(row.conversion_factor) or 1,
		}))

	return combine_bom_components(components)


def get_relevant_bom_components(bom_name, included_groups, multiplier=1, visited=None):
	visited = set(visited or [])
	if bom_name in visited:
		frappe.throw(_("Circular BOM reference found at {0}.").format(bom_name))
	visited.add(bom_name)

	bom = frappe.db.get_value(
		"BOM", bom_name, ["quantity", "docstatus", "is_active"], as_dict=True
	)
	if not bom or cint(bom.docstatus) != 1 or not cint(bom.is_active):
		frappe.throw(_("BOM {0} must be active and submitted.").format(bom_name))

	output_qty = flt(bom.quantity) or 1
	components = []
	rows = frappe.get_all(
		"BOM Item",
		filters={"parent": bom_name},
		fields=[
			"item_code", "item_name", "description", "qty", "stock_qty", "uom",
			"stock_uom", "conversion_factor", "rate", "amount", "bom_no", "idx",
		],
		order_by="idx asc",
	)
	for row in rows:
		item = frappe.db.get_value(
			"Item", row.item_code, ["item_name", "description", "item_group", "stock_uom"], as_dict=True
		) or frappe._dict()
		qty_per_stock_unit = multiplier * flt(row.qty) / output_qty
		if item.item_group in included_groups:
			components.append(frappe._dict({
				"item_code": row.item_code,
				"item_name": row.item_name or item.item_name or row.item_code,
				"description": row.description or item.description,
				"item_group": item.item_group,
				"qty_per_stock_unit": qty_per_stock_unit,
				"stock_qty_per_stock_unit": multiplier * flt(row.stock_qty or row.qty) / output_qty,
				"valuation_weight_per_stock_unit": (
					multiplier * flt(row.stock_qty or row.qty) * flt(row.rate) / output_qty
				),
				"uom": row.uom or item.stock_uom,
				"stock_uom": row.stock_uom or item.stock_uom,
				"conversion_factor": flt(row.conversion_factor) or 1,
			}))
		elif row.bom_no:
			nested_multiplier = multiplier * flt(row.stock_qty or row.qty) / output_qty
			components.extend(
				get_relevant_bom_components(row.bom_no, included_groups, nested_multiplier, visited)
			)

	return combine_bom_components(components)


def combine_bom_components(components):
	combined = []
	by_key = {}
	for component in components:
		key = (component.item_code, component.uom)
		if key in by_key:
			by_key[key].qty_per_stock_unit = (
				flt(by_key[key].qty_per_stock_unit) + flt(component.qty_per_stock_unit)
			)
			by_key[key].stock_qty_per_stock_unit = (
				flt(by_key[key].stock_qty_per_stock_unit)
				+ flt(component.stock_qty_per_stock_unit)
			)
			by_key[key].valuation_weight_per_stock_unit = (
				flt(by_key[key].valuation_weight_per_stock_unit)
				+ flt(component.valuation_weight_per_stock_unit)
			)
		else:
			copy = frappe._dict(component.copy())
			by_key[key] = copy
			combined.append(copy)
	return combined


def get_delivery_component_summary(row):
	bom_name = row.get("billing_bom") or get_default_product_bom(row.item_code)
	if not bom_name:
		return None
	components = get_direct_bom_components(bom_name, LOAN_DELIVERY_COMPONENT_GROUPS)
	return "\n".join(
		"{0:g} x {1} ({2})".format(
			flt(component.qty_per_stock_unit), component.item_name, component.item_code
		)
		for component in components
	)


def append_description_note(description, note):
	if not note:
		return description
	if description:
		return "{0}<br><br><strong>{1}</strong>".format(description, note)
	return note


def append_delivery_component_summary(description, component_summary):
	if not component_summary:
		return description
	formatted_summary = "<br>".join(component_summary.splitlines())
	return append_description_note(
		description,
		"{0}<br>{1}".format(_("Included components per product unit"), formatted_summary),
	)


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
