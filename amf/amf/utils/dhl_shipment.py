# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

"""Prepare, validate, and explicitly create DHL Express MyDHL shipments.

Validation uses ``validateDataOnly=true`` and creates nothing.  Creation is a
separate confirmation-gated operation which is permitted only for the exact
payload and API environment that DHL most recently validated successfully.
"""

from __future__ import unicode_literals

import base64
import binascii
import copy
import hashlib
import html
import json
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import frappe
import pytz
import requests
from frappe import _
from frappe.utils import cstr, flt, get_system_timezone, get_time, getdate, now_datetime
from frappe.utils.file_manager import save_file


DHL_API_URLS = {
	"Test": "https://express.api.dhl.com/mydhlapi/test",
	"Production": "https://express.api.dhl.com/mydhlapi",
}
DHL_CARRIER_PATTERN = re.compile(r"(?:^|[^A-Z0-9])DHL(?:$|[^A-Z0-9])", re.IGNORECASE)
DHL_INCOTERMS = {
	"EXW": "EXW (Ex Works)",
	"FCA": "FCA (Free Carrier)",
	"CPT": "CPT (Carriage Paid To)",
	"CIP": "CIP (Carriage and Insurance Paid to)",
	"DPU": "DPU (Delivered At Place Unloaded)",
	"DAP": "DAP (Delivered At Place)",
	"DDP": "DDP (Delivered Duty Paid)",
}
DHL_EXPORT_UOM = {
	"nos": "PCS",
	"no": "NO",
	"pcs": "PCS",
	"piece": "PCS",
	"pieces": "PCS",
	"unit": "EA",
	"units": "EA",
	"set": "SET",
	"sets": "SET",
	"kg": "KG",
	"kilogram": "KG",
	"kilograms": "KG",
	"gram": "GM",
	"grams": "GM",
}
DHL_WEIGHT_TO_KG = {
	"kg": 1.0,
	"kilogram": 1.0,
	"kilograms": 1.0,
	"gram": 0.001,
	"grams": 0.001,
}
DHL_CONTENT_DESCRIPTION = "OEM microfluidic pumps/rotary valves, non-medical, with accessories"
DHL_ACCOUNT_PATTERN = re.compile(r"^[A-Za-z0-9]{9}$")


def is_dhl_carrier(carrier):
	"""Return True only when the Delivery Note carrier contains the DHL token."""
	return bool(DHL_CARRIER_PATTERN.search(cstr(carrier).strip()))


def get_explicit_incoterm(value):
	"""Return the sole explicit DHL incoterm token in a source value."""
	tokens = set(re.findall(r"\b[A-Z]{3}\b", cstr(value).upper()))
	matches = sorted(tokens.intersection(DHL_INCOTERMS))
	return matches[0] if len(matches) == 1 else None


def _incoterm_from_delivery_note(delivery_note):
	"""Read the field labelled Terms and reject a contradictory rendered detail."""
	terms_value = get_explicit_incoterm(delivery_note.get("tc_name"))
	detail_value = get_explicit_incoterm(_plain_text(delivery_note.get("terms")))
	if terms_value and detail_value and terms_value != detail_value:
		return None, "conflict"
	if terms_value:
		return terms_value, None
	return None, "missing"


def _plain_text(value):
	text = re.sub(r"<[^>]+>", " ", cstr(value))
	return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _is_new_doc(doc):
	return bool(doc.is_new()) if hasattr(doc, "is_new") else bool(doc.get("__islocal"))


def _strict_delivery_note_number(value):
	"""Parse one DN packaging number without treating decimal commas as thousands."""
	value = cstr(value).strip()
	if not value or not re.match(r"^\d+(?:[.,]\d+)?$", value):
		return None
	try:
		return Decimal(value.replace(",", "."))
	except InvalidOperation:
		return None


def _delivery_note_package(delivery_note):
	"""Return the DN's single Packaging Information set as one Shipment parcel."""
	fieldnames = ("weight", "length", "width", "height")
	missing = [fieldname for fieldname in fieldnames if not cstr(delivery_note.get(fieldname)).strip()]
	if missing:
		return None, {
			"code": "missing_delivery_note_packaging",
			"fields": missing,
			"message": _("Delivery Note {0} Packaging Information is missing: {1}.").format(
				delivery_note.get("name") or _("unsaved"), ", ".join(missing)
			),
		}

	values = {fieldname: _strict_delivery_note_number(delivery_note.get(fieldname)) for fieldname in fieldnames}
	invalid = [fieldname for fieldname, value in values.items() if value is None or value <= 0]
	if invalid:
		return None, {
			"code": "invalid_delivery_note_packaging",
			"fields": invalid,
			"message": _("Delivery Note {0} Packaging Information has invalid positive numbers: {1}.").format(
				delivery_note.get("name") or _("unsaved"), ", ".join(invalid)
			),
		}

	fractional_dimensions = [
		fieldname for fieldname in ("length", "width", "height")
		if values[fieldname] != values[fieldname].to_integral_value()
	]
	if fractional_dimensions:
		return None, {
			"code": "fractional_delivery_note_dimensions",
			"fields": fractional_dimensions,
			"message": _("Delivery Note {0} dimensions must be whole centimetres for ERPNext Shipment Parcel: {1}.").format(
				delivery_note.get("name") or _("unsaved"), ", ".join(fractional_dimensions)
			),
		}

	return {
		"weight": float(values["weight"]),
		"length": int(values["length"]),
		"width": int(values["width"]),
		"height": int(values["height"]),
		# One DN section contains one measurement set and no count field.
		"count": 1,
	}, None


def _normalized_country_name(value):
	return re.sub(r"[^a-z0-9]+", " ", cstr(value).casefold()).strip()


def _bundled_iso_country_code(country):
	"""Resolve an exact country name through Frappe/Babel's bundled ISO data."""
	from babel import Locale
	from frappe.geo.country_info import get_all

	normalized_country = _normalized_country_name(country)
	if not normalized_country:
		return None
	candidates = set()
	for country_name, country_data in get_all().items():
		code = cstr((country_data or {}).get("code")).strip().upper()
		if (
			len(code) == 2
			and code.isalpha()
			and _normalized_country_name(country_name) == normalized_country
		):
			candidates.add(code)
	for code, country_name in Locale.parse("en").territories.items():
		code = cstr(code).strip().upper()
		if (
			len(code) == 2
			and code.isalpha()
			and _normalized_country_name(country_name) == normalized_country
		):
			candidates.add(code)
	return next(iter(candidates)) if len(candidates) == 1 else None


def _label_declares_kilograms(label):
	return bool(re.search(r"(?:\bkg\b|\bkilograms?\b)", cstr(label), re.IGNORECASE))


def _delivery_note_item_weight_kg(item, total_weight_label, unit_weight_label):
	"""Resolve actual DN-line weight using explicit UOM or an explicit kg field label."""
	weight_uom = cstr(item.get("weight_uom")).strip()
	weight_factor = DHL_WEIGHT_TO_KG.get(weight_uom.lower())
	total_weight = flt(item.get("total_weight"))
	if total_weight > 0:
		if weight_factor:
			return {
				"value": total_weight * weight_factor,
				"source_field": "total_weight/weight_uom",
				"label_based_kg": False,
				"ignored_weight_uom": "",
			}
		if _label_declares_kilograms(total_weight_label):
			return {
				"value": total_weight,
				"source_field": "total_weight ({0})".format(total_weight_label),
				"label_based_kg": True,
				"ignored_weight_uom": weight_uom,
			}

	unit_weight = flt(item.get("weight_per_unit"))
	quantity = flt(item.get("qty"))
	if unit_weight > 0 and quantity > 0:
		if weight_factor:
			return {
				"value": unit_weight * quantity * weight_factor,
				"source_field": "weight_per_unit/qty/weight_uom",
				"label_based_kg": False,
				"ignored_weight_uom": "",
			}
		if _label_declares_kilograms(unit_weight_label):
			return {
				"value": unit_weight * quantity,
				"source_field": "weight_per_unit ({0}) × qty".format(unit_weight_label),
				"label_based_kg": True,
				"ignored_weight_uom": weight_uom,
			}
	return None


@frappe.whitelist()
def make_dhl_shipment(source_name, target_doc=None):
	"""Map a submitted DHL Delivery Note to an unsaved ERPNext Shipment draft."""
	from erpnext.stock.doctype.delivery_note.delivery_note import make_shipment

	delivery_note = frappe.get_doc("Delivery Note", source_name)
	delivery_note.check_permission("read")
	if not frappe.has_permission("Shipment", "create"):
		frappe.throw(_("Not permitted to create Shipment"), frappe.PermissionError)
	if delivery_note.docstatus != 1:
		frappe.throw(_("Delivery Note {0} must be submitted.").format(source_name))
	if delivery_note.is_return:
		frappe.throw(_("Return Delivery Notes require an explicit return-shipment workflow."))
	if not is_dhl_carrier(delivery_note.carrier):
		frappe.throw(
			_("Delivery Note {0} is not a DHL shipment (Carrier: {1}).").format(
				source_name, delivery_note.carrier or _("not set")
			)
		)

	shipment = make_shipment(source_name, target_doc)
	shipment.carrier = delivery_note.carrier
	shipment.service_provider = "DHL Express"
	if not shipment.get("delivery_contact_name"):
		sales_order_names = sorted({
			cstr(item.get("against_sales_order")).strip()
			for item in delivery_note.items
			if cstr(item.get("against_sales_order")).strip()
		})
		sales_order_contacts = []
		sales_order_docs = []
		for sales_order_name in sales_order_names:
			sales_order = frappe.get_doc("Sales Order", sales_order_name)
			sales_order.check_permission("read")
			sales_order_docs.append(sales_order)
			contact_name = cstr(sales_order.get("contact_person")).strip()
			if contact_name and contact_name not in sales_order_contacts:
				sales_order_contacts.append(contact_name)
		if len(sales_order_contacts) == 1:
			contact_doc = frappe.get_doc("Contact", sales_order_contacts[0])
			shipment.delivery_contact_name = contact_doc.name
			shipment.delivery_contact_email = contact_doc.get("email_id")
			contact_display = _plain_text(contact_doc.get("full_name"))
			if not contact_display:
				sales_order_displays = sorted({
					_plain_text(sales_order.get("contact_display"))
					for sales_order in sales_order_docs
					if cstr(sales_order.get("contact_person")).strip() == contact_doc.name
					and _plain_text(sales_order.get("contact_display"))
				})
				if len(sales_order_displays) == 1:
					contact_display = sales_order_displays[0]
			phone = _plain_text(contact_doc.get("phone") or contact_doc.get("mobile_no"))
			if contact_doc.get("email_id"):
				contact_display += "<br>" + cstr(contact_doc.email_id)
			if phone:
				contact_display += "<br>" + phone
			shipment.delivery_contact = contact_display
	incoterm, unused_incoterm_error = _incoterm_from_delivery_note(delivery_note)
	if incoterm:
		shipment.incoterm = DHL_INCOTERMS[incoterm]
	else:
		# Core mapping copies same-named fields; Terms remains authoritative here.
		shipment.incoterm = None
	if not shipment.description_of_content:
		shipment.description_of_content = DHL_CONTENT_DESCRIPTION
	package, unused_error = _delivery_note_package(delivery_note)
	if package:
		shipment.append("shipment_parcel", package)
	return shipment


class DHLShipmentDraftBuilder(object):
	"""Build a partial MyDHL request and retain field-level provenance/issues."""

	def __init__(self, shipment):
		self.shipment = shipment
		self.payload = {}
		self.issues = []
		self.sources = {}
		self.delivery_notes = []
		self.sales_orders = []
		self.sales_invoices = []
		self.settings = frappe.get_single("AMF DHL Settings")

	def issue(self, severity, code, field, message):
		entry = {
			"severity": severity,
			"code": code,
			"field": field,
			"message": message,
		}
		if entry not in self.issues:
			self.issues.append(entry)

	def source(self, path, doctype, name, fieldname):
		entry = {"doctype": doctype, "name": name, "fieldname": fieldname}
		self.sources.setdefault(path, [])
		if entry not in self.sources[path]:
			self.sources[path].append(entry)

	def required_text(self, value, path, label, maximum=None):
		value = _plain_text(value)
		if not value:
			self.issue("error", "missing_required_value", path, _("{0} is required.").format(label))
			return None
		if maximum and len(value) > maximum:
			self.issue(
				"error",
				"value_too_long",
				path,
				_("{0} has {1} characters; DHL permits at most {2}.").format(
					label, len(value), maximum
				),
			)
			return None
		return value

	def dhl_account_number(self, value, path, label, required=False):
		"""Validate a DHL billing account without inferring or repairing its value."""
		value = _plain_text(value)
		if not value:
			if required:
				self.issue("error", "missing_dhl_account_number", path, _("{0} is required.").format(label))
			return None
		if not DHL_ACCOUNT_PATTERN.match(value):
			optional_instruction = _(" Leave this optional field empty if no separate DHL account applies.") if not required else ""
			self.issue(
				"error",
				"invalid_dhl_account_number",
				path,
				_("{0} must be exactly 9 alphanumeric characters; the configured value has {1} characters.").format(label, len(value)) + optional_instruction,
			)
			return None
		return value

	def build(self):
		self._load_sources()
		self._validate_source_consistency()
		self._build_header()
		self._build_parties()
		self._build_content()
		self._build_references()
		return {
			"payload": self.payload,
			"issues": self.issues,
			"sources": self.sources,
			"source_documents": {
				"delivery_notes": [doc.name for doc in self.delivery_notes],
				"sales_orders": [doc.name for doc in self.sales_orders],
				"sales_invoices": [doc.name for doc in self.sales_invoices],
				"customer_purchase_orders": self._customer_purchase_orders(),
				"customs_commodity_codes": self._customs_commodity_codes(),
			},
			"ready_for_dhl_validation": not any(
				issue["severity"] == "error" for issue in self.issues
			),
			"remote_operation": "local draft; validation and confirmed creation are separate operations",
		}

	def _load_sources(self):
		rows = self.shipment.get("shipment_delivery_note") or []
		if not rows:
			self.issue(
				"error", "missing_delivery_note", "shipment_delivery_note", _("At least one Delivery Note is required.")
			)
			return

		seen_sales_orders = set()
		seen_delivery_notes = set()
		for row in rows:
			name = cstr(row.get("delivery_note")).strip()
			if not name or name in seen_delivery_notes:
				continue
			seen_delivery_notes.add(name)
			delivery_note = frappe.get_doc("Delivery Note", name)
			delivery_note.check_permission("read")
			self.delivery_notes.append(delivery_note)
			if delivery_note.docstatus != 1:
				self.issue("error", "delivery_note_not_submitted", name, _("Delivery Note {0} is not submitted.").format(name))
			if delivery_note.is_return:
				self.issue("error", "return_not_supported", name, _("Delivery Note {0} is a return.").format(name))
			if not is_dhl_carrier(delivery_note.carrier):
				self.issue(
					"error",
					"non_dhl_carrier",
					name,
					_("Delivery Note {0} Carrier is '{1}', not DHL.").format(name, delivery_note.carrier or ""),
				)

			for item in delivery_note.items:
				sales_order_name = cstr(item.get("against_sales_order")).strip()
				if sales_order_name and sales_order_name not in seen_sales_orders:
					sales_order = frappe.get_doc("Sales Order", sales_order_name)
					sales_order.check_permission("read")
					self.sales_orders.append(sales_order)
					seen_sales_orders.add(sales_order_name)

		if not self.sales_orders:
			self.issue(
				"warning",
				"missing_sales_order_link",
				"sales_orders",
				_("No Delivery Note item is linked to a Sales Order; Sales Order and customer PO references cannot be verified."),
			)

		if self.delivery_notes:
			invoice_rows = frappe.get_all(
				"Sales Invoice Item",
				filters={"delivery_note": ["in", [doc.name for doc in self.delivery_notes]]},
				fields=["parent"],
				order_by="parent asc",
			)
			for invoice_name in sorted({row.parent for row in invoice_rows if row.parent}):
				sales_invoice = frappe.get_doc("Sales Invoice", invoice_name)
				if sales_invoice.docstatus != 1 or sales_invoice.get("is_return"):
					continue
				sales_invoice.check_permission("read")
				self.sales_invoices.append(sales_invoice)

	def _validate_source_consistency(self):
		"""Report conflicts; never silently choose among different source documents."""
		for fieldname, label in (
			("company", _("Company")),
			("customer", _("Customer")),
			("currency", _("Currency")),
		):
			values = sorted({cstr(doc.get(fieldname)).strip() for doc in self.delivery_notes if doc.get(fieldname)})
			if len(values) > 1:
				self.issue(
					"error",
					"conflicting_delivery_note_sources",
					fieldname,
					_("Linked Delivery Notes contain more than one {0}.").format(label),
				)

		shipping_addresses = sorted(
			{
				cstr(doc.get("shipping_address_name") or doc.get("customer_address")).strip()
				for doc in self.delivery_notes
				if doc.get("shipping_address_name") or doc.get("customer_address")
			}
		)
		if len(shipping_addresses) > 1:
			self.issue(
				"error",
				"conflicting_delivery_addresses",
				"delivery_address_name",
				_("Linked Delivery Notes contain more than one delivery address."),
			)
		elif shipping_addresses and cstr(self.shipment.get("delivery_address_name")) != shipping_addresses[0]:
			self.issue(
				"warning",
				"shipment_address_differs",
				"delivery_address_name",
				_("Shipment delivery address differs from the linked Delivery Note; review the explicit Shipment address."),
			)

		purchase_orders = {
			_plain_text(doc.po_no)
			for doc in self.delivery_notes + self.sales_orders
			if _plain_text(doc.po_no)
		}
		if len(purchase_orders) > 1:
			self.issue(
				"warning",
				"multiple_customer_purchase_orders",
				"customerReferences.PON",
				_("The source documents contain multiple customer PO values; all are retained as separate DHL PON references."),
			)

	def _build_header(self):
		planned = self._planned_shipping_datetime()
		if planned:
			self.payload["plannedShippingDateAndTime"] = planned
			self.source("plannedShippingDateAndTime", "Shipment", self.shipment.name, "pickup_date")
			self.source("plannedShippingDateAndTime", "Shipment", self.shipment.name, "pickup_from")

		pickup_type = cstr(self.shipment.get("pickup_type")).strip()
		if pickup_type not in ("Pickup", "Self delivery"):
			self.issue("error", "missing_pickup_type", "pickup.isRequested", _("Shipment Pickup Type must be Pickup or Self delivery."))
		else:
			pickup = {"isRequested": pickup_type == "Pickup"}
			if pickup["isRequested"] and self.shipment.get("pickup_to"):
				pickup["closeTime"] = cstr(get_time(self.shipment.pickup_to))[:5]
			self.payload["pickup"] = pickup
			self.source("pickup.isRequested", "Shipment", self.shipment.name, "pickup_type")

		product_code = self.required_text(
			self.shipment.get("dhl_product_code"),
			"productCode",
			_("DHL transport product code (global; not a customs tariff number)"),
			6,
		)
		if product_code:
			self.payload["productCode"] = product_code
			self.source("productCode", "Shipment", self.shipment.name, "dhl_product_code")

		accounts = []
		shipper_account = self.dhl_account_number(
			self.settings.get("shipper_account_number"),
			"accounts.shipper",
			_("DHL shipper account number in AMF DHL Settings"),
			required=True,
		)
		if shipper_account:
			accounts.append({"typeCode": "shipper", "number": shipper_account})
			self.source("accounts.shipper", "AMF DHL Settings", "AMF DHL Settings", "shipper_account_number")

		for fieldname, type_code, label in (
			("dhl_payer_account_number", "payer", _("DHL payer account number")),
			("dhl_duties_taxes_account_number", "duties-taxes", _("DHL duties/taxes account number")),
		):
			value = self.dhl_account_number(
				self.shipment.get(fieldname), "accounts." + type_code, label, required=False
			)
			if not value:
				continue
			accounts.append({"typeCode": type_code, "number": value})
			self.source("accounts." + type_code, "Shipment", self.shipment.name, fieldname)

		if len(accounts) > 3:
			self.issue("error", "too_many_accounts", "accounts", _("DHL permits at most three account entries."))
		elif accounts:
			self.payload["accounts"] = accounts

	def _planned_shipping_datetime(self):
		if not self.shipment.get("pickup_date") or not self.shipment.get("pickup_from"):
			self.issue(
				"error",
				"missing_shipping_datetime",
				"plannedShippingDateAndTime",
				_("Shipment Pickup Date and Pickup From time are required."),
			)
			return None
		try:
			date_value = getdate(self.shipment.pickup_date)
			time_value = get_time(self.shipment.pickup_from)
			naive = datetime.combine(date_value, time_value)
			timezone = pytz.timezone(get_system_timezone())
			localized = timezone.localize(naive, is_dst=None)
		except (TypeError, ValueError, pytz.AmbiguousTimeError, pytz.NonExistentTimeError) as error:
			self.issue("error", "invalid_shipping_datetime", "plannedShippingDateAndTime", cstr(error))
			return None

		now_value = now_datetime()
		if now_value.tzinfo is None:
			now_value = timezone.localize(now_value)
		else:
			now_value = now_value.astimezone(timezone)
		if localized <= now_value:
			self.issue("error", "shipping_datetime_in_past", "plannedShippingDateAndTime", _("DHL shipping date/time must be in the future."))
		if localized.date() > (now_value + timedelta(days=10)).date():
			self.issue("error", "shipping_datetime_too_far", "plannedShippingDateAndTime", _("DHL shipping date cannot be more than 10 days in the future."))

		offset = localized.strftime("%z")
		return "{0}GMT{1}:{2}".format(localized.strftime("%Y-%m-%dT%H:%M:%S"), offset[:3], offset[3:])

	def _build_parties(self):
		shipper = self._shipper_details()
		receiver = self._receiver_details()
		parties = {}
		if shipper:
			parties["shipperDetails"] = shipper
		if receiver:
			parties["receiverDetails"] = receiver
		if parties:
			self.payload["customerDetails"] = parties

	def _shipper_details(self):
		company = frappe.get_doc("Company", self.shipment.pickup_company) if self.shipment.get("pickup_company") else None
		company_name = self.required_text(
			(company and (company.get("company_name") or company.name)),
			"customerDetails.shipperDetails.contactInformation.companyName",
			_("Pickup company"),
			100,
		)
		if company:
			self.source("customerDetails.shipperDetails.contactInformation.companyName", "Company", company.name, "company_name")
		address = self._address(self.shipment.get("pickup_address_name"), "shipper")
		contact_doc = None
		if self.shipment.get("pickup_contact_name"):
			contact_doc = frappe.get_doc("Contact", self.shipment.pickup_contact_name)
		elif self.shipment.get("pickup_contact_person"):
			contact_doc = frappe.get_doc("User", self.shipment.pickup_contact_person)

		full_name = self.settings.get("shipper_contact_name") or (contact_doc and contact_doc.get("full_name"))
		if self.settings.get("shipper_contact_name"):
			self.source("customerDetails.shipperDetails.contactInformation.fullName", "AMF DHL Settings", "AMF DHL Settings", "shipper_contact_name")
		elif contact_doc and contact_doc.get("full_name"):
			self.source("customerDetails.shipperDetails.contactInformation.fullName", contact_doc.doctype, contact_doc.name, "full_name")
		phone = self.settings.get("shipper_contact_phone")
		phone_source = ("AMF DHL Settings", "AMF DHL Settings", "shipper_contact_phone") if phone else None
		if not phone and contact_doc:
			phone = contact_doc.get("phone") or contact_doc.get("mobile_no")
			if phone:
				phone_source = (contact_doc.doctype, contact_doc.name, "phone/mobile_no")
		if not phone and address:
			phone = frappe.db.get_value("Address", self.shipment.pickup_address_name, "phone")
			if phone:
				phone_source = ("Address", self.shipment.pickup_address_name, "phone")
		if not phone and self.shipment.get("pickup_company"):
			phone = frappe.db.get_value("Company", self.shipment.pickup_company, "phone_no")
			if phone:
				phone_source = ("Company", self.shipment.pickup_company, "phone_no")
		email = self.settings.get("shipper_contact_email") or (contact_doc and (contact_doc.get("email_id") or contact_doc.get("email")))
		if phone_source:
			self.source("customerDetails.shipperDetails.contactInformation.phone", *phone_source)

		contact = self._contact(company_name, full_name, phone, email, "shipper")
		self.source("customerDetails.shipperDetails.postalAddress", "Shipment", self.shipment.name, "pickup_address_name")
		details = {"typeCode": "business"}
		if address:
			details["postalAddress"] = address
		if contact:
			details["contactInformation"] = contact
		return details

	def _receiver_details(self):
		if cstr(self.shipment.get("delivery_to_type") or "Customer") != "Customer":
			self.issue(
				"error",
				"unsupported_receiver_type",
				"delivery_to_type",
				_("This DHL workflow supports Customer receivers only."),
			)
		customer_name = self.shipment.get("delivery_customer")
		customer = frappe.get_doc("Customer", customer_name) if customer_name else None
		company_name = customer and (customer.get("customer_name") or customer.name)
		if customer:
			self.source("customerDetails.receiverDetails.contactInformation.companyName", "Customer", customer.name, "customer_name")
		address = self._address(self.shipment.get("delivery_address_name"), "receiver")
		full_name, contact_doc = self._receiver_contact_full_name()
		phone = contact_doc and (contact_doc.get("phone") or contact_doc.get("mobile_no"))
		email = contact_doc and contact_doc.get("email_id")
		if phone:
			self.source("customerDetails.receiverDetails.contactInformation.phone", "Contact", contact_doc.name, "phone/mobile_no")
		if (not phone or not email) and self.delivery_notes:
			phone = phone or self._single_delivery_note_value("contact_phone", "contact_mobile")
			email = email or self._single_delivery_note_value("contact_email")

		contact = self._contact(company_name, full_name, phone, email, "receiver")
		details = {"typeCode": "private" if customer and customer.get("customer_type") == "Individual" else "business"}
		if address:
			details["postalAddress"] = address
		if contact:
			details["contactInformation"] = contact
		registrations = []
		tax_id = _plain_text(customer and customer.get("tax_id"))
		ein = _plain_text(customer and customer.get("ein"))
		if tax_id:
			if len(tax_id) > 35:
				self.issue("error", "organization_eori_too_long", "customerDetails.receiverDetails.registrationNumbers.EOR", _("Organization EORI exceeds DHL's 35-character limit."))
			else:
				issuer_match = re.match(r"^([A-Z]{2})[A-Z0-9]{1,33}$", tax_id.upper())
				if issuer_match:
					registrations.append({"typeCode": "EOR", "number": tax_id, "issuerCountryCode": issuer_match.group(1)})
					self.source("customerDetails.receiverDetails.registrationNumbers.EOR", "Customer", customer.name, "tax_id")
				else:
					self.issue("warning", "invalid_organization_eori", "customerDetails.receiverDetails.registrationNumbers.EOR", _("Organization EORI is not an alphanumeric value beginning with its two-letter issuer country, so it was not sent to DHL."))
		if ein:
			if len(ein) > 35:
				self.issue("error", "organization_ein_too_long", "customerDetails.receiverDetails.registrationNumbers.EIN", _("Organization EIN exceeds DHL's 35-character limit."))
			elif not re.match(r"^\d{2}-?\d{7}$", ein):
				self.issue("warning", "invalid_organization_ein", "customerDetails.receiverDetails.registrationNumbers.EIN", _("Organization EIN must contain exactly nine digits, optionally with the standard hyphen, so it was not sent to DHL."))
			else:
				registrations.append({"typeCode": "EIN", "number": ein, "issuerCountryCode": "US"})
				self.source("customerDetails.receiverDetails.registrationNumbers.EIN", "Customer", customer.name, "ein")
		if registrations:
			details["registrationNumbers"] = registrations
		self.source("customerDetails.receiverDetails.postalAddress", "Shipment", self.shipment.name, "delivery_address_name")
		return details

	def _receiver_contact_full_name(self):
		"""Resolve receiver name from DN first, then SO; never invent a person name."""
		path = "customerDetails.receiverDetails.contactInformation.fullName"
		for doctype, documents in (("Delivery Note", self.delivery_notes), ("Sales Order", self.sales_orders)):
			contact_doc = None
			contact_names = []
			for document in documents:
				contact_name = cstr(document.get("contact_person")).strip()
				if contact_name and contact_name not in contact_names:
					contact_names.append(contact_name)
			if len(contact_names) > 1:
				self.issue(
					"error",
					"conflicting_receiver_contacts",
					path,
					_("Linked {0} documents contain more than one receiver Contact Person.").format(doctype),
				)
				return None, None
			if contact_names:
				contact_doc = frappe.get_doc("Contact", contact_names[0])
				full_name = _plain_text(contact_doc.get("full_name"))
				if full_name:
					self.source(path, "Contact", contact_doc.name, "full_name")
					for document in documents:
						if cstr(document.get("contact_person")).strip() == contact_doc.name:
							self.source(path, doctype, document.name, "contact_person")
					return full_name, contact_doc

			displays = []
			for document in documents:
				display = _plain_text(document.get("contact_display"))
				if display and display not in displays:
					displays.append(display)
			if len(displays) > 1:
				self.issue(
					"error",
					"conflicting_receiver_contact_names",
					path,
					_("Linked {0} documents contain more than one receiver contact name.").format(doctype),
				)
				return None, None
			if displays:
				for document in documents:
					if _plain_text(document.get("contact_display")) == displays[0]:
						self.source(path, doctype, document.name, "contact_display")
				return displays[0], contact_doc
		return None, None

	def _address(self, address_name, role):
		path = "customerDetails.{0}Details.postalAddress".format(role)
		if not address_name:
			self.issue("error", "missing_address", path, _("{0} address is required.").format(role.title()))
			return None
		address_doc = frappe.get_doc("Address", address_name)
		country_code = self._country_code(address_doc.country, path + ".countryCode")
		values = {
			"postalCode": cstr(address_doc.pincode).strip(),
			"cityName": self.required_text(address_doc.city, path + ".cityName", _("{0} city").format(role.title()), 45),
			"countryCode": country_code,
			"addressLine1": self.required_text(address_doc.address_line1, path + ".addressLine1", _("{0} address line 1").format(role.title()), 45),
		}
		if len(values["postalCode"]) > 12:
			self.issue("error", "value_too_long", path + ".postalCode", _("{0} postal code exceeds DHL's 12-character limit.").format(role.title()))
			values["postalCode"] = None
		for fieldname, target, maximum in (
			("address_line2", "addressLine2", 45),
			("county", "countyName", 45),
			("state", "provinceName", 35),
		):
			value = _plain_text(address_doc.get(fieldname))
			if not value:
				continue
			if len(value) > maximum:
				self.issue("error", "value_too_long", path + "." + target, _("{0} exceeds DHL's {1}-character limit.").format(target, maximum))
			else:
				values[target] = value
		return {key: value for key, value in values.items() if value is not None}

	def _contact(self, company_name, full_name, phone, email, role):
		path = "customerDetails.{0}Details.contactInformation".format(role)
		values = {
			"companyName": self.required_text(company_name, path + ".companyName", _("{0} company/name").format(role.title()), 100),
			"fullName": self.required_text(full_name, path + ".fullName", _("{0} contact full name").format(role.title()), 255),
			"phone": self.required_text(phone, path + ".phone", _("{0} contact phone").format(role.title()), 70),
		}
		email = _plain_text(email)
		if email:
			if len(email) > 70:
				self.issue("error", "value_too_long", path + ".email", _("{0} email exceeds DHL's 70-character limit.").format(role.title()))
			else:
				values["email"] = email
		return {key: value for key, value in values.items() if value is not None}

	def _build_content(self):
		content = {"unitOfMeasurement": "metric"}
		for delivery_note in self.delivery_notes:
			self.source("content.unitOfMeasurement", "Delivery Note", delivery_note.name, "weight (kg), dimensions (cm)")
		packages = self._packages()
		if packages:
			content["packages"] = packages

		description = self.required_text(self.shipment.get("description_of_content"), "content.description", _("Shipment description of content"), 70)
		if description:
			content["description"] = description
			self.source("content.description", "Shipment", self.shipment.name, "description_of_content")

		declarable = cstr(self.shipment.get("dhl_customs_declarable")).strip()
		if declarable not in ("Yes", "No"):
			self.issue("error", "customs_status_not_decided", "content.isCustomsDeclarable", _("Explicitly select Yes or No for DHL Customs Declarable."))
		else:
			content["isCustomsDeclarable"] = declarable == "Yes"
			self.source("content.isCustomsDeclarable", "Shipment", self.shipment.name, "dhl_customs_declarable")

		incoterm = self._delivery_note_incoterm()
		if incoterm:
			content["incoterm"] = incoterm
			for delivery_note in self.delivery_notes:
				self.source("content.incoterm", "Delivery Note", delivery_note.name, "tc_name")

		if declarable == "Yes":
			self._add_export_declaration(content)
		self.payload["content"] = content

	def _packages(self):
		packages = []
		for delivery_note in self.delivery_notes:
			package, error = _delivery_note_package(delivery_note)
			if error:
				self.issue("error", error["code"], "content.packages", error["message"])
				continue
			packages.append({
				"weight": package["weight"],
				"dimensions": {key: package[key] for key in ("length", "width", "height")},
			})
			self.source(
				"content.packages.{0}".format(len(packages)),
				"Delivery Note",
				delivery_note.name,
				"weight/length/width/height (Packaging Information)",
			)
		if not packages and not self.delivery_notes:
			self.issue("error", "missing_packages", "content.packages", _("At least one linked Delivery Note is required for Packaging Information."))
		if len(packages) > 999:
			self.issue("error", "too_many_packages", "content.packages", _("DHL permits at most 999 packages."))
			return []
		return packages

	def _delivery_note_incoterm(self):
		values = []
		for delivery_note in self.delivery_notes:
			value, error = _incoterm_from_delivery_note(delivery_note)
			if error == "conflict":
				self.issue("error", "conflicting_delivery_note_terms", "content.incoterm", _("Delivery Note {0} selected Terms and Terms and Conditions Details contain different Incoterms.").format(delivery_note.name))
				continue
			if error:
				self.issue("error", "missing_delivery_note_incoterm", "content.incoterm", _("Delivery Note {0} field Terms must contain exactly one supported Incoterm token.").format(delivery_note.name))
				continue
			if value not in values:
				values.append(value)
		if len(values) > 1:
			self.issue("error", "conflicting_delivery_note_incoterms", "content.incoterm", _("Linked Delivery Note Terms contain conflicting Incoterms: {0}.").format(", ".join(values)))
			return None
		if not values:
			return None
		shipment_incoterm = get_explicit_incoterm(self.shipment.get("incoterm"))
		if shipment_incoterm and shipment_incoterm != values[0]:
			self.issue("warning", "shipment_incoterm_differs", "incoterm", _("Shipment Incoterm differs from Delivery Note Terms; the Delivery Note value is sent to DHL."))
		return values[0]

	def _add_export_declaration(self, content):
		currencies = {cstr(doc.currency).strip().upper() for doc in self.delivery_notes if doc.currency}
		if len(currencies) != 1:
			self.issue("error", "ambiguous_currency", "content.declaredValueCurrency", _("All Delivery Notes must have one identical three-letter currency."))
			currency = None
		else:
			currency = next(iter(currencies))
			if len(currency) != 3:
				self.issue("error", "invalid_currency", "content.declaredValueCurrency", _("DHL requires a three-letter currency code."))
				currency = None

		line_items = []
		declared_value = 0.0
		line_number = 0
		for delivery_note in self.delivery_notes:
			for item in delivery_note.items:
				line_number += 1
				line = self._export_line(delivery_note, item, line_number)
				if line:
					line_items.append(line)
					declared_value += flt(line["price"]) * line["quantity"]["value"]
		if line_items:
			export_declaration = {"lineItems": line_items}
			invoice = self._customs_invoice()
			if invoice:
				export_declaration["invoice"] = invoice
			content["exportDeclaration"] = export_declaration
		if currency:
			content["declaredValueCurrency"] = currency
		if line_items:
			content["declaredValue"] = flt(declared_value, 3)

	def _customs_invoice(self):
		"""Return an explicitly sourced MyDHL customs invoice; never invent its date."""
		date_path = "content.exportDeclaration.invoice.date"
		number_path = "content.exportDeclaration.invoice.number"
		explicit_number = _plain_text(self.shipment.get("dhl_customs_invoice_number"))
		explicit_date = self.shipment.get("dhl_customs_invoice_date")

		if explicit_number and len(explicit_number) > 35:
			self.issue(
				"error",
				"customs_invoice_number_too_long",
				number_path,
				_("Shipment DHL Customs Invoice Number has {0} characters; MyDHL permits at most 35.").format(len(explicit_number)),
			)
			explicit_number = None

		if explicit_date:
			try:
				explicit_date = getdate(explicit_date).isoformat()
			except (TypeError, ValueError):
				self.issue(
					"error",
					"invalid_customs_invoice_date",
					date_path,
					_("Shipment DHL Customs Invoice Date is not a valid date."),
				)
				explicit_date = None

		if len(self.sales_invoices) > 1:
			invoice_names = ", ".join(doc.name for doc in self.sales_invoices)
			matches = [
				doc for doc in self.sales_invoices
				if explicit_number == doc.name
				and explicit_date == getdate(doc.posting_date).isoformat()
			]
			if len(matches) != 1:
				self.issue(
					"error",
					"multiple_submitted_sales_invoices",
					"content.exportDeclaration.invoice",
					_("Linked Delivery Notes are invoiced by multiple submitted Sales Invoices ({0}). Set both Shipment DHL Customs Invoice Number and DHL Customs Invoice Date to exactly identify the invoice being declared.").format(invoice_names),
				)
				return None
			invoice_doc = matches[0]
			self.source(number_path, "Shipment", self.shipment.name, "dhl_customs_invoice_number")
			self.source(date_path, "Shipment", self.shipment.name, "dhl_customs_invoice_date")
			self.source(number_path, "Sales Invoice", invoice_doc.name, "name")
			self.source(date_path, "Sales Invoice", invoice_doc.name, "posting_date (Invoice Date)")
			return {"number": explicit_number, "date": explicit_date}

		if len(self.sales_invoices) == 1:
			invoice_doc = self.sales_invoices[0]
			invoice_number = cstr(invoice_doc.name).strip()
			invoice_date = getdate(invoice_doc.posting_date).isoformat()
			if explicit_number and explicit_number != invoice_number:
				self.issue(
					"error",
					"customs_invoice_number_conflict",
					number_path,
					_("Shipment DHL Customs Invoice Number '{0}' conflicts with submitted Sales Invoice {1}.").format(explicit_number, invoice_number),
				)
			if explicit_date and explicit_date != invoice_date:
				self.issue(
					"error",
					"customs_invoice_date_conflict",
					date_path,
					_("Shipment DHL Customs Invoice Date {0} conflicts with Invoice Date {1} on submitted Sales Invoice {2}.").format(explicit_date, invoice_date, invoice_number),
				)
			if any(
				issue["severity"] == "error" and issue["code"] in (
					"customs_invoice_number_conflict", "customs_invoice_date_conflict"
				)
				for issue in self.issues
			):
				return None
			if len(invoice_number) > 35:
				self.issue(
					"error",
					"customs_invoice_number_too_long",
					number_path,
					_("Submitted Sales Invoice {0} exceeds MyDHL's 35-character invoice-number limit.").format(invoice_number),
				)
				return None
			self.source(number_path, "Sales Invoice", invoice_doc.name, "name")
			self.source(date_path, "Sales Invoice", invoice_doc.name, "posting_date (Invoice Date)")
			return {"number": invoice_number, "date": invoice_date}

		if not explicit_date:
			self.issue(
				"error",
				"missing_customs_invoice_date",
				date_path,
				_("MyDHL requires the customs invoice issue date. No submitted Sales Invoice is linked through the Delivery Note items; set Shipment DHL Customs Invoice Date explicitly."),
			)
			return None

		invoice = {"date": explicit_date}
		self.source(date_path, "Shipment", self.shipment.name, "dhl_customs_invoice_date")
		if explicit_number:
			invoice["number"] = explicit_number
			self.source(number_path, "Shipment", self.shipment.name, "dhl_customs_invoice_number")
		return invoice

	def _export_line(self, delivery_note, item, number):
		path = "content.exportDeclaration.lineItems.{0}".format(number)
		item_source_name = item.get("name") or _("row {0}").format(item.idx)
		for target, fieldname in (
			("description", "custom_description/item_name/description"),
			("price", "net_rate"),
			("quantity", "qty/uom"),
			("manufacturerCountry", "country_of_origin"),
		):
			self.source(path + "." + target, "Delivery Note Item", item_source_name, fieldname)
		description = self.required_text(item.get("custom_description") or item.get("item_name") or item.get("description"), path + ".description", _("Customs description for row {0}").format(number), 512)
		qty = flt(item.get("qty"))
		if qty <= 0 or not qty.is_integer():
			self.issue("error", "invalid_customs_quantity", path + ".quantity.value", _("Delivery Note {0} row {1} quantity must be a positive integer for MyDHL.").format(delivery_note.name, item.idx))
			quantity = None
		else:
			quantity = int(qty)

		uom = DHL_EXPORT_UOM.get(cstr(item.get("uom")).strip().lower())
		if not uom:
			self.issue("error", "unmapped_customs_uom", path + ".quantity.unitOfMeasurement", _("Delivery Note {0} row {1} UOM '{2}' has no approved DHL mapping.").format(delivery_note.name, item.idx, item.get("uom") or ""))

		country_code = self._country_code(item.get("country_of_origin"), path + ".manufacturerCountry")
		price = flt(item.get("net_rate"), 3)
		if price < 0:
			self.issue(
				"error",
				"negative_customs_price",
				path + ".price",
				_("Delivery Note {0} row {1} has a negative net rate.").format(delivery_note.name, item.idx),
			)
		item_meta = frappe.get_meta("Delivery Note Item")
		total_weight_field = item_meta.get_field("total_weight")
		unit_weight_field = item_meta.get_field("weight_per_unit")
		weight_resolution = _delivery_note_item_weight_kg(
			item,
			cstr(total_weight_field and total_weight_field.label),
			cstr(unit_weight_field and unit_weight_field.label),
		)
		weight = flt(weight_resolution["value"], 3) if weight_resolution else None
		if not weight or weight <= 0:
			self.issue(
				"error",
				"missing_customs_weight",
				path + ".weight.netValue",
				_("Delivery Note {0} row {1} needs either a positive total/unit weight with Kg or Gram UOM, or a positive value in a field explicitly labelled as kilograms.").format(delivery_note.name, item.idx),
			)
			weight = None
		else:
			self.source(
				path + ".weight",
				"Delivery Note Item",
				item_source_name,
				weight_resolution["source_field"],
			)
			if weight_resolution["label_based_kg"] and weight_resolution["ignored_weight_uom"]:
				self.issue(
					"warning",
					"non_mass_weight_uom_ignored",
					path + ".weight.netValue",
					_("Delivery Note {0} row {1} Weight UOM '{2}' is not a supported mass unit. Because the source field is explicitly labelled in kilograms, DHL uses its resolved value {3} kg.").format(
						delivery_note.name,
						item.idx,
						weight_resolution["ignored_weight_uom"],
						weight,
					),
				)

		if not all((description, quantity, uom, country_code, weight)) or price < 0:
			return None
		line = {
			"number": number,
			"description": description,
			"price": price,
			"quantity": {"value": quantity, "unitOfMeasurement": uom},
			"manufacturerCountry": country_code,
			"weight": {"netValue": weight},
		}
		tariff = re.sub(r"\s+", "", cstr(item.get("customs_tariff_number_")).strip())
		if tariff:
			self.source(path + ".commodityCodes", "Delivery Note Item", item_source_name, "customs_tariff_number_")
			if len(tariff) > 18:
				self.issue("error", "commodity_code_too_long", path + ".commodityCodes", _("Delivery Note {0} row {1} customs tariff number exceeds 18 characters.").format(delivery_note.name, item.idx))
			else:
				line["commodityCodes"] = [{"typeCode": "outbound", "value": tariff}]
		else:
			self.issue("warning", "missing_commodity_code", path + ".commodityCodes", _("Delivery Note {0} row {1} has no customs tariff number; DHL's schema allows omission, but the lane's customs rules may not.").format(delivery_note.name, item.idx))
		return line

	def _build_references(self):
		references = []
		seen = set()

		def add(value, type_code, doctype, name, fieldname):
			value = _plain_text(value)
			key = (type_code, value)
			if not value or key in seen:
				return
			if len(value) > 35:
				self.issue("error", "reference_too_long", "customerReferences", _("{0} {1} is longer than DHL's 35-character reference limit; it was not truncated.").format(doctype, name))
				return
			seen.add(key)
			references.append({"value": value, "typeCode": type_code})
			self.source("customerReferences.{0}:{1}".format(type_code, value), doctype, name, fieldname)

		if self.shipment.name and not _is_new_doc(self.shipment):
			add(self.shipment.name, "CU", "Shipment", self.shipment.name, "name")
		for delivery_note in self.delivery_notes:
			add(delivery_note.name, "AAJ", "Delivery Note", delivery_note.name, "name")
			add(delivery_note.po_no, "PON", "Delivery Note", delivery_note.name, "po_no")
		for sales_order in self.sales_orders:
			add(sales_order.name, "OID", "Sales Order", sales_order.name, "name")
			add(sales_order.po_no, "PON", "Sales Order", sales_order.name, "po_no")
		if references:
			self.payload["customerReferences"] = references

	def _customer_purchase_orders(self):
		values = []
		for doc in self.sales_orders:
			if doc.po_no:
				values.append({"po_no": doc.po_no, "po_date": doc.po_date, "source": "Sales Order {0}".format(doc.name)})
		for doc in self.delivery_notes:
			if doc.po_no and not any(value["po_no"] == doc.po_no for value in values):
				values.append({"po_no": doc.po_no, "po_date": doc.po_date, "source": "Delivery Note {0}".format(doc.name)})
		return values

	def _customs_commodity_codes(self):
		"""Expose the exact DN-item-to-DHL-line tariff mapping for operator review."""
		values = []
		line_number = 0
		for delivery_note in self.delivery_notes:
			for item in delivery_note.items:
				line_number += 1
				raw_value = cstr(item.get("customs_tariff_number_")).strip()
				outbound_value = re.sub(r"\s+", "", raw_value) if raw_value else ""
				values.append({
					"line_number": line_number,
					"delivery_note": delivery_note.name,
					"delivery_note_item": item.get("name"),
					"item_code": item.get("item_code"),
					"source_field": "customs_tariff_number_",
					"source_value": raw_value,
					"dhl_type_code": "outbound" if outbound_value and len(outbound_value) <= 18 else None,
					"dhl_value": outbound_value if outbound_value and len(outbound_value) <= 18 else None,
				})
		return values

	def _single_delivery_note_value(self, *fieldnames):
		values = []
		for doc in self.delivery_notes:
			value = None
			for fieldname in fieldnames:
				value = _plain_text(doc.get(fieldname))
				if value:
					break
			if value and value not in values:
				values.append(value)
		if len(values) > 1:
			self.issue("error", "conflicting_delivery_note_values", "/".join(fieldnames), _("Linked Delivery Notes contain conflicting values for {0}.").format(", ".join(fieldnames)))
			return None
		return values[0] if values else None

	def _country_code(self, country, path):
		country = cstr(country).strip()
		if not country:
			self.issue("error", "missing_country", path, _("Country is required."))
			return None
		if len(country) == 2 and country.isalpha():
			return country.upper()
		code = cstr(frappe.db.get_value("Country", country, "code")).strip().upper()
		if len(code) == 2 and code.isalpha():
			return code
		bundled_code = _bundled_iso_country_code(country)
		if bundled_code:
			self.issue(
				"warning",
				"country_code_resolved_from_standard",
				path,
				_("Country {0} has no two-letter code in the ERPNext Country record. DHL code {1} was resolved from Frappe's bundled ISO territory data.").format(country, bundled_code),
			)
			return bundled_code
		self.issue(
			"error",
			"missing_country_code",
			path,
			_("Country {0} has no valid two-letter code in ERPNext and no unique exact match in Frappe's bundled ISO territory data.").format(country),
		)
		return None


def _dhl_product_query_from_draft(draft):
	"""Build the official one-piece GET /products query from a prepared draft."""
	payload = draft.get("payload") or {}
	issues = []

	def issue(code, field, message):
		issues.append({"severity": "error", "code": code, "field": field, "message": message})

	shipper_accounts = [
		account.get("number") for account in payload.get("accounts", [])
		if account.get("typeCode") == "shipper" and account.get("number")
	]
	if len(shipper_accounts) != 1:
		issue("invalid_product_lookup_shipper_account", "accounts.shipper", _("Exactly one valid DHL shipper account is required for Product lookup."))

	parties = payload.get("customerDetails") or {}
	origin = (parties.get("shipperDetails") or {}).get("postalAddress") or {}
	destination = (parties.get("receiverDetails") or {}).get("postalAddress") or {}
	for role, address in (("origin", origin), ("destination", destination)):
		for fieldname in ("countryCode", "cityName"):
			if not address.get(fieldname):
				issue("missing_product_lookup_address", "{0}.{1}".format(role, fieldname), _("DHL Product lookup requires {0} {1}.").format(role, fieldname))

	packages = ((payload.get("content") or {}).get("packages") or [])
	if len(packages) != 1:
		issue(
			"product_lookup_requires_one_package",
			"content.packages",
			_("DHL GET /products supports exactly one package; this draft has {0}. Use a multi-piece Rating workflow instead.").format(len(packages)),
		)
	package = packages[0] if len(packages) == 1 else {}
	dimensions = package.get("dimensions") or {}
	for fieldname, value in (
		("weight", package.get("weight")),
		("length", dimensions.get("length")),
		("width", dimensions.get("width")),
		("height", dimensions.get("height")),
	):
		if not value:
			issue("missing_product_lookup_package_value", "content.packages.0." + fieldname, _("DHL Product lookup requires package {0}.").format(fieldname))

	planned = cstr(payload.get("plannedShippingDateAndTime"))
	if not re.match(r"^\d{4}-\d{2}-\d{2}", planned):
		issue("missing_product_lookup_date", "plannedShippingDateAndTime", _("DHL Product lookup requires a valid planned shipping date."))

	content = payload.get("content") or {}
	if "isCustomsDeclarable" not in content:
		issue("missing_product_lookup_customs_status", "content.isCustomsDeclarable", _("DHL Product lookup requires the explicit customs-declarable decision."))

	if issues:
		return None, issues

	query = {
		"accountNumber": shipper_accounts[0],
		"originCountryCode": origin["countryCode"],
		"originCityName": origin["cityName"],
		"destinationCountryCode": destination["countryCode"],
		"destinationCityName": destination["cityName"],
		"weight": package["weight"],
		"length": dimensions["length"],
		"width": dimensions["width"],
		"height": dimensions["height"],
		"plannedShippingDate": planned[:10],
		"isCustomsDeclarable": "true" if content["isCustomsDeclarable"] else "false",
		"unitOfMeasurement": "metric",
	}
	if origin.get("postalCode"):
		query["originPostalCode"] = origin["postalCode"]
	if destination.get("postalCode"):
		query["destinationPostalCode"] = destination["postalCode"]
	return query, []


def _shipment_doc(shipment):
	if isinstance(shipment, str):
		if shipment.lstrip().startswith("{"):
			shipment = json.loads(shipment)
		else:
			doc = frappe.get_doc("Shipment", shipment)
			doc.check_permission("read")
			return doc
	if isinstance(shipment, dict):
		doc = frappe.get_doc(shipment)
		if not _is_new_doc(doc):
			doc.check_permission("read")
		elif not frappe.has_permission("Shipment", "create"):
			frappe.throw(_("Not permitted to create Shipment"), frappe.PermissionError)
		return doc
	frappe.throw(_("Shipment must be a Shipment name or document."))


@frappe.whitelist()
def prepare_dhl_shipment_draft(shipment):
	"""Return the partial payload, blockers, warnings, and source provenance."""
	doc = _shipment_doc(shipment)
	return DHLShipmentDraftBuilder(doc).build()


def _dhl_payload_hash(payload):
	"""Return a stable fingerprint of the exact JSON body sent to MyDHL."""
	canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
	return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sanitize_dhl_response_data(data):
	"""Copy a DHL response and remove every embedded base64 document body."""
	safe_data = copy.deepcopy(data)
	if not isinstance(safe_data, dict):
		return safe_data
	for document in safe_data.get("documents", []) or []:
		if isinstance(document, dict) and document.get("content"):
			document["content"] = "[base64 document omitted]"
	for package in safe_data.get("packages", []) or []:
		if not isinstance(package, dict):
			continue
		for document in package.get("documents", []) or []:
			if isinstance(document, dict) and document.get("content"):
				document["content"] = "[base64 document omitted]"
	return safe_data


def _safe_response_data(response):
	try:
		data = response.json()
	except ValueError:
		data = {"message": cstr(response.text)[:2000]}
	return _sanitize_dhl_response_data(data)


def _dhl_creation_details(data):
	"""Normalize identifiers from a successful DHL Create Shipment response."""
	if not isinstance(data, dict):
		return {
			"shipment_tracking_number": "",
			"tracking_url": "",
			"dispatch_confirmation_number": "",
			"piece_tracking_numbers": [],
		}
	piece_tracking_numbers = []
	for package in data.get("packages", []) or []:
		if not isinstance(package, dict):
			continue
		tracking_number = _plain_text(package.get("trackingNumber"))
		if tracking_number and tracking_number not in piece_tracking_numbers:
			piece_tracking_numbers.append(tracking_number)
	return {
		"shipment_tracking_number": _plain_text(data.get("shipmentTrackingNumber")),
		"tracking_url": _plain_text(data.get("trackingUrl")),
		"dispatch_confirmation_number": _plain_text(data.get("dispatchConfirmationNumber")),
		"piece_tracking_numbers": piece_tracking_numbers,
	}


def _dhl_response_documents(data):
	"""Return shipment and piece document objects with their package reference."""
	documents = []
	if not isinstance(data, dict):
		return documents
	for document in data.get("documents", []) or []:
		if isinstance(document, dict):
			documents.append(document)
	for package in data.get("packages", []) or []:
		if not isinstance(package, dict):
			continue
		package_reference = package.get("referenceNumber")
		for document in package.get("documents", []) or []:
			if not isinstance(document, dict):
				continue
			document_with_reference = dict(document)
			document_with_reference.setdefault("packageReferenceNumber", package_reference)
			documents.append(document_with_reference)
	return documents


def _attach_dhl_response_documents(shipment_name, tracking_number, data):
	"""Attach valid MyDHL response documents privately; never fail the booking."""
	format_extensions = {
		"PDF": "pdf",
		"PNG": "png",
		"JPG": "jpg",
		"JPEG": "jpg",
		"ZPL": "zpl",
		"LP2": "lp2",
		"EPL2": "epl2",
	}
	attached = []
	warnings = []
	for index, document in enumerate(_dhl_response_documents(data), 1):
		type_code = _plain_text(document.get("typeCode")) or "document"
		image_format = cstr(document.get("imageFormat")).strip().upper()
		extension = format_extensions.get(image_format)
		encoded_content = document.get("content")
		if not extension or not encoded_content:
			warnings.append(
				_("DHL document {0} was not attached because its format or content was missing/unsupported.").format(index)
			)
			continue
		try:
			content = base64.b64decode(cstr(encoded_content).encode("ascii"), validate=True)
		except (UnicodeEncodeError, TypeError, ValueError, binascii.Error):
			warnings.append(_("DHL document {0} was not attached because its base64 content was invalid.").format(index))
			continue
		if not content:
			warnings.append(_("DHL document {0} was empty and was not attached.").format(index))
			continue
		package_reference = document.get("packageReferenceNumber")
		safe_type = re.sub(r"[^A-Za-z0-9_-]+", "-", type_code).strip("-") or "document"
		piece_suffix = "-piece-{0}".format(package_reference) if package_reference else ""
		filename = "{0}-{1}-{2}{3}.{4}".format(
			shipment_name, tracking_number, safe_type, piece_suffix, extension
		)
		try:
			file_doc = save_file(filename, content, "Shipment", shipment_name, is_private=1)
			attached.append({
				"file_name": file_doc.file_name,
				"file_url": file_doc.file_url,
				"type_code": type_code,
				"package_reference_number": package_reference,
			})
		except Exception as error:
			frappe.log_error(frappe.get_traceback(), "DHL document attachment failed for {0}".format(shipment_name))
			warnings.append(
				_("DHL created the shipment, but document {0} could not be attached locally: {1}").format(index, cstr(error))
			)
	return attached, warnings


def _extract_dhl_validation_errors(data):
	"""Normalize MyDHL problem details while retaining the untouched safe response."""
	errors = []
	seen = set()
	message_keys = ("message", "msg", "detail", "description", "reason", "title")
	code_keys = ("code", "errorCode", "error_code", "statusCode")
	path_keys = ("field", "fieldName", "field_name", "path", "pointer", "instance")
	collection_keys = (
		"additionalDetails",
		"additional_details",
		"reasons",
		"errors",
		"error",
		"validationErrors",
		"validation_errors",
		"violations",
		"details",
	)

	def scalar(value):
		return isinstance(value, (str, int, float)) and not isinstance(value, bool)

	def clean(value):
		return re.sub(r"\s+", " ", cstr(value)).strip()

	def add(message, code=None, path=None):
		message = clean(message)
		code = clean(code) if scalar(code) else ""
		path = clean(path) if scalar(path) else ""
		if not message:
			return
		if not code:
			code_match = re.match(r"^(\d{3,6}):\s*(.+)$", message)
			if code_match:
				code = code_match.group(1)
				message = code_match.group(2)
		key = (code, path, message)
		if key in seen:
			return
		seen.add(key)
		entry = {"message": message}
		if code:
			entry["code"] = code
		if path:
			entry["path"] = path
		errors.append(entry)

	def visit(value, inherited_path=None):
		if scalar(value):
			add(value, path=inherited_path)
			return
		if isinstance(value, list):
			for item in value:
				visit(item, inherited_path)
			return
		if not isinstance(value, dict):
			return

		code = next((value.get(key) for key in code_keys if scalar(value.get(key))), None)
		path = next((value.get(key) for key in path_keys if scalar(value.get(key))), inherited_path)
		messages = []
		for key in message_keys:
			if scalar(value.get(key)):
				message = clean(value.get(key))
				if message and message not in messages:
					messages.append(message)
		if messages:
			add(" — ".join(messages), code=code, path=path)

		visited_collection = False
		for key in collection_keys:
			if key in value and value.get(key) not in (None, "", [], {}):
				visited_collection = True
				visit(value.get(key), path)

		# Some gateways wrap the problem object in a data/response/result key.
		for key in ("data", "response", "result"):
			if isinstance(value.get(key), (dict, list)):
				visited_collection = True
				visit(value.get(key), path)

		if not messages and not visited_collection:
			for key, child in value.items():
				if isinstance(child, (dict, list)):
					visit(child, path or key)

	visit(data)
	return errors


def _dhl_response_identifiers(response, data=None):
	identifiers = {}
	for header in (
		"x-correlation-id",
		"x-request-id",
		"x-dhl-request-id",
		"request-id",
		"message-reference",
		"invocation-id",
		"location",
	):
		value = cstr(response.headers.get(header)).strip()
		if value:
			identifiers[header] = value
	if isinstance(data, dict) and isinstance(data.get("details"), dict):
		for key in ("msgId", "messageId", "transactionId"):
			value = cstr(data["details"].get(key)).strip()
			if value:
				identifiers[key] = value
	return identifiers


def _dhl_rejection_context(http_status, http_reason, environment, error_count, dhl_errors=None):
	"""Describe the request stage that failed without calling auth failures data errors."""
	status_label = "{0} {1}".format(http_status, cstr(http_reason).strip()).strip()
	if http_status == 401:
		return {
			"failure_stage": "authentication",
			"validation_status": "Authentication failed",
			"message": _("DHL authentication failed ({0}). The shipment payload was not validated. Verify that AMF DHL Settings contains active MyDHL API credentials for the selected {1} environment; no shipment or AWB was created.").format(status_label, environment),
		}
	if http_status == 403:
		return {
			"failure_stage": "authorization",
			"validation_status": "Authorization failed",
			"message": _("DHL authorization failed ({0}). The credentials were not permitted to use this MyDHL operation/environment, and the shipment payload was not validated; no shipment or AWB was created.").format(status_label),
		}
	error_codes = {cstr(error.get("code")) for error in (dhl_errors or [])}
	if error_codes.intersection({"803", "8003"}):
		return {
			"failure_stage": "account_service_authorization",
			"validation_status": "Account/service not allowed",
			"message": _("DHL authenticated the request but rejected account/service authorization (DHL code {0}). Verify every transmitted DHL billing account and ask DHL to enable the required Shipment service/product for the account; no shipment or AWB was created.").format(", ".join(sorted(error_codes.intersection({"803", "8003"})))),
		}
	if "8007" in error_codes:
		return {
			"failure_stage": "product_lookup",
			"validation_status": "Transport product lookup failed",
			"message": _("DHL could not resolve the requested transport product (DHL code 8007). Fetch the available DHL transport products for the current account, lane, parcel and date, then select one explicitly; no shipment or AWB was created."),
		}
	return {
		"failure_stage": "validation",
		"validation_status": "Rejected by DHL",
		"message": _("DHL rejected the draft data with {0} reported error detail(s); no shipment or AWB was created.").format(error_count),
	}


def _set_existing_shipment_fields(shipment, values, update_modified=False):
	"""Persist only fields installed on this ERPNext site's Shipment schema."""
	existing_values = {
		fieldname: value for fieldname, value in values.items()
		if shipment.meta.has_field(fieldname)
	}
	if existing_values:
		frappe.db.set_value(
			"Shipment", shipment.name, existing_values, update_modified=update_modified
		)
	return existing_values


def _clear_dhl_validation_fingerprint(shipment, validation_status=None):
	values = {
		"dhl_validated_payload_hash": "",
		"dhl_validated_environment": "",
	}
	if validation_status is not None:
		values["dhl_validation_status"] = validation_status
	_set_existing_shipment_fields(shipment, values)


@frappe.whitelist()
def get_dhl_shipment_products(shipment_name):
	"""Return live one-piece MyDHL Product capabilities; create no shipment/AWB."""
	shipment = frappe.get_doc("Shipment", shipment_name)
	shipment.check_permission("write")
	if shipment.docstatus != 0:
		frappe.throw(_("DHL transport products can only be fetched for a draft Shipment."))

	draft = DHLShipmentDraftBuilder(shipment).build()
	query, query_issues = _dhl_product_query_from_draft(draft)
	if query_issues:
		return {
			"fetched": False,
			"products": [],
			"draft": draft,
			"issues": query_issues,
			"message": _("DHL Product lookup was not sent because required lookup data is incomplete."),
			"remote_operation": "read-only Product capability lookup; no DHL shipment or AWB is created",
		}

	settings = frappe.get_single("AMF DHL Settings")
	username = cstr(settings.get("api_username")).strip()
	password = settings.get_password("api_password", raise_exception=False)
	environment = cstr(settings.get("api_environment") or "Test").strip()
	if not username or not password:
		return {"fetched": False, "products": [], "draft": draft, "issues": [], "message": _("MyDHL API username/password are missing; DHL was not contacted.")}
	if environment not in DHL_API_URLS:
		return {"fetched": False, "products": [], "draft": draft, "issues": [], "message": _("AMF DHL Settings has an invalid API environment; DHL was not contacted.")}

	url = DHL_API_URLS[environment] + "/products"
	try:
		response = requests.get(
			url,
			params=query,
			auth=(username, password),
			headers={"Accept": "application/json"},
			timeout=30,
		)
	except requests.RequestException as error:
		return {"fetched": False, "products": [], "draft": draft, "issues": [], "message": _("DHL Product lookup request failed: {0}").format(cstr(error))}

	data = _safe_response_data(response)
	fetched = 200 <= response.status_code < 300
	products = []
	if fetched and isinstance(data, dict):
		for product in data.get("products", []) or []:
			if not isinstance(product, dict) or not product.get("productCode"):
				continue
			delivery = product.get("deliveryCapabilities") or {}
			products.append({
				"productCode": product.get("productCode"),
				"productName": product.get("productName"),
				"localProductCode": product.get("localProductCode"),
				"networkTypeCode": product.get("networkTypeCode"),
				"isCustomerAgreement": bool(product.get("isCustomerAgreement")),
				"estimatedDeliveryDateAndTime": delivery.get("estimatedDeliveryDateAndTime"),
			})

	safe_query = dict(query)
	account_number = cstr(safe_query.get("accountNumber"))
	safe_query["accountNumber"] = "{0}{1}".format("*" * max(0, len(account_number) - 4), account_number[-4:])
	return {
		"fetched": fetched,
		"http_status": response.status_code,
		"http_reason": cstr(response.reason),
		"environment": environment,
		"products": products,
		"issues": [],
		"query": safe_query,
		"response_identifiers": _dhl_response_identifiers(response, data),
		"response": None if fetched else data,
		"dhl_errors": [] if fetched else _extract_dhl_validation_errors(data),
		"message": _("DHL returned {0} available transport product(s). Select one explicitly; no shipment or AWB was created.").format(len(products)) if fetched else _("DHL Product lookup failed; no shipment or AWB was created."),
		"remote_operation": "read-only Product capability lookup; no DHL shipment or AWB is created",
	}


@frappe.whitelist()
def validate_dhl_shipment_draft(shipment_name):
	"""Validate a saved draft with MyDHL; never create a DHL shipment or AWB."""
	shipment = frappe.get_doc("Shipment", shipment_name)
	shipment.check_permission("write")
	if shipment.docstatus != 0:
		frappe.throw(_("Only a draft Shipment can be validated with DHL."))
	if cstr(shipment.get("dhl_creation_status")) in ("Creation in progress", "Created", "Creation outcome unknown"):
		frappe.throw(_("This Shipment already has a DHL creation attempt and cannot be revalidated."))

	draft = DHLShipmentDraftBuilder(shipment).build()
	if not draft["ready_for_dhl_validation"]:
		_clear_dhl_validation_fingerprint(shipment, "")
		return {"validated": False, "draft": draft, "message": _("Local validation found blocking fields; DHL was not contacted.")}

	settings = frappe.get_single("AMF DHL Settings")
	username = cstr(settings.get("api_username")).strip()
	password = settings.get_password("api_password", raise_exception=False)
	environment = cstr(settings.get("api_environment") or "Test").strip()
	if not username or not password:
		_clear_dhl_validation_fingerprint(shipment, "")
		return {"validated": False, "draft": draft, "message": _("MyDHL API username/password are missing in AMF DHL Settings; DHL was not contacted.")}
	if environment not in DHL_API_URLS:
		_clear_dhl_validation_fingerprint(shipment, "")
		return {"validated": False, "draft": draft, "message": _("AMF DHL Settings has an invalid API environment; DHL was not contacted.")}

	url = DHL_API_URLS[environment] + "/shipments"
	try:
		response = requests.post(
			url,
			params={"validateDataOnly": "true"},
			auth=(username, password),
			headers={"Accept": "application/json", "Content-Type": "application/json"},
			json=draft["payload"],
			timeout=30,
		)
	except requests.RequestException as error:
		_clear_dhl_validation_fingerprint(shipment, "")
		return {"validated": False, "draft": draft, "message": _("DHL validation request failed: {0}").format(cstr(error))}

	data = _safe_response_data(response)
	validated = 200 <= response.status_code < 300
	dhl_errors = [] if validated else _extract_dhl_validation_errors(data)
	if validated:
		failure_stage = None
		validation_status = "Validated by DHL"
		message = _("DHL validated the data only; no shipment or AWB was created.")
	else:
		rejection = _dhl_rejection_context(
			response.status_code, response.reason, environment, len(dhl_errors), dhl_errors
		)
		failure_stage = rejection["failure_stage"]
		validation_status = rejection["validation_status"]
		message = rejection["message"]
	audit_values = {
		"dhl_validation_status": validation_status,
		"dhl_last_validation": now_datetime(),
		"dhl_validated_payload_hash": _dhl_payload_hash(draft["payload"]) if validated else "",
		"dhl_validated_environment": environment if validated else "",
	}
	_set_existing_shipment_fields(shipment, audit_values)
	return {
		"validated": validated,
		"failure_stage": failure_stage,
		"http_status": response.status_code,
		"http_reason": cstr(response.reason),
		"environment": environment,
		"response_identifiers": _dhl_response_identifiers(response, data),
		"response": data,
		"dhl_errors": dhl_errors,
		"draft": draft,
		"message": message,
	}


@frappe.whitelist()
def create_dhl_shipment(shipment_name, confirmation=None):
	"""Create one DHL shipment from the exact payload/environment already validated."""
	if cstr(confirmation).strip() != "CREATE DHL SHIPMENT":
		frappe.throw(_("Creation confirmation did not match 'CREATE DHL SHIPMENT'."))

	shipment = frappe.get_doc("Shipment", shipment_name)
	shipment.check_permission("write")
	if shipment.docstatus != 0:
		frappe.throw(_("Only a draft ERPNext Shipment can create a DHL shipment."))
	if not is_dhl_carrier(shipment.get("carrier")):
		frappe.throw(_("Shipment {0} Carrier is not DHL.").format(shipment.name))
	for required_audit_field in (
		"dhl_validated_payload_hash",
		"dhl_validated_environment",
		"dhl_creation_status",
		"dhl_creation_payload_hash",
	):
		if not shipment.meta.has_field(required_audit_field):
			frappe.throw(_("DHL creation audit fields are not installed. Run the AMF DHL Shipment setup before creating a shipment."))

	# Serialize competing create requests before reserving the one allowed attempt.
	frappe.db.sql("select name from `tabShipment` where name=%s for update", shipment.name)
	shipment.reload()
	creation_status = cstr(shipment.get("dhl_creation_status")).strip()
	if creation_status == "Created" or shipment.get("shipment_id") or shipment.get("awb_number"):
		frappe.throw(
			_("DHL shipment creation is blocked because this ERPNext Shipment already contains a DHL shipment/AWB identifier.")
		)
	if creation_status == "Creation in progress":
		frappe.throw(_("A DHL shipment creation request is already in progress. Do not retry it."))
	if creation_status == "Creation outcome unknown":
		frappe.throw(
			_("The prior DHL creation outcome is unknown. Check the DHL portal and contact DHL using the stored Message Reference before any retry; an automatic retry could create a duplicate AWB.")
		)
	if cstr(shipment.get("dhl_validation_status")) != "Validated by DHL":
		frappe.throw(_("DHL shipment creation requires a successful DHL validation first."))

	draft = DHLShipmentDraftBuilder(shipment).build()
	if not draft["ready_for_dhl_validation"]:
		frappe.throw(_("Current ERPNext data has local blockers. Rebuild and validate the DHL draft before creation."))
	current_payload_hash = _dhl_payload_hash(draft["payload"])
	validated_payload_hash = cstr(shipment.get("dhl_validated_payload_hash")).strip()
	if not validated_payload_hash:
		frappe.throw(_("No validated DHL payload fingerprint is stored. Validate this Shipment again before creation."))
	if current_payload_hash != validated_payload_hash:
		frappe.throw(
			_("The outbound DHL payload changed after validation. No creation request was sent; validate the current data again.")
		)

	settings = frappe.get_single("AMF DHL Settings")
	username = cstr(settings.get("api_username")).strip()
	password = settings.get_password("api_password", raise_exception=False)
	environment = cstr(settings.get("api_environment") or "Test").strip()
	validated_environment = cstr(shipment.get("dhl_validated_environment")).strip()
	if environment not in DHL_API_URLS:
		frappe.throw(_("AMF DHL Settings has an invalid API environment; DHL was not contacted."))
	if environment != validated_environment:
		frappe.throw(
			_("The MyDHL environment changed from {0} at validation to {1}. No creation request was sent; validate again in the current environment.").format(
				validated_environment or _("not recorded"), environment
			)
		)
	if not username or not password:
		frappe.throw(_("MyDHL API username/password are missing; DHL was not contacted."))

	message_reference = str(uuid.uuid4())
	_set_existing_shipment_fields(shipment, {
		"dhl_creation_status": "Creation in progress",
		"dhl_last_creation": now_datetime(),
		"dhl_creation_environment": environment,
		"dhl_message_reference": message_reference,
		"dhl_creation_payload_hash": current_payload_hash,
		"dhl_creation_error": "",
	})
	# Commit the attempt marker before the irreversible external call. This is the
	# duplicate-prevention boundary if the worker or network fails afterward.
	frappe.db.commit()

	url = DHL_API_URLS[environment] + "/shipments"
	try:
		response = requests.post(
			url,
			auth=(username, password),
			headers={
				"Accept": "application/json",
				"Content-Type": "application/json",
				"Message-Reference": message_reference,
			},
			json=draft["payload"],
			timeout=60,
		)
	except requests.RequestException as error:
		error_message = _(
			"The DHL creation request ended without an HTTP response. Its outcome is unknown; do not retry until the DHL portal has been checked with Message Reference {0}. Technical detail: {1}"
		).format(message_reference, cstr(error))
		_set_existing_shipment_fields(shipment, {
			"dhl_creation_status": "Creation outcome unknown",
			"dhl_last_creation": now_datetime(),
			"dhl_creation_error": error_message,
		})
		frappe.db.commit()
		return {
			"created": False,
			"outcome_unknown": True,
			"environment": environment,
			"message_reference": message_reference,
			"message": error_message,
			"draft": draft,
		}

	try:
		raw_data = response.json()
	except ValueError:
		raw_data = {"message": cstr(response.text)[:2000]}
	safe_data = _sanitize_dhl_response_data(raw_data)
	response_identifiers = _dhl_response_identifiers(response, safe_data)
	dhl_errors = _extract_dhl_validation_errors(safe_data)
	details = _dhl_creation_details(raw_data)
	tracking_number = details["shipment_tracking_number"]
	created = response.status_code == 201 and bool(tracking_number)

	if not created:
		outcome_unknown = response.status_code >= 500 or 200 <= response.status_code < 300
		creation_status = "Creation outcome unknown" if outcome_unknown else "Creation failed"
		if outcome_unknown:
			message = _(
				"DHL did not return the documented HTTP 201 response with a shipment tracking number. The creation outcome is unknown; check the DHL portal using Message Reference {0} before any retry."
			).format(message_reference)
		else:
			message = _(
				"DHL rejected the creation request (HTTP {0} {1}); no shipment tracking number was returned."
			).format(response.status_code, cstr(response.reason).strip())
		error_audit = json.dumps(safe_data, indent=2, ensure_ascii=False)[:20000]
		_set_existing_shipment_fields(shipment, {
			"dhl_creation_status": creation_status,
			"dhl_last_creation": now_datetime(),
			"dhl_creation_error": error_audit,
		})
		frappe.db.commit()
		return {
			"created": False,
			"outcome_unknown": outcome_unknown,
			"http_status": response.status_code,
			"http_reason": cstr(response.reason),
			"environment": environment,
			"message_reference": message_reference,
			"response_identifiers": response_identifiers,
			"response": safe_data,
			"dhl_errors": dhl_errors,
			"message": message,
			"draft": draft,
		}

	piece_tracking_numbers = "\n".join(details["piece_tracking_numbers"])
	_set_existing_shipment_fields(shipment, {
		"dhl_creation_status": "Created",
		"dhl_last_creation": now_datetime(),
		"dhl_creation_environment": environment,
		"dhl_dispatch_confirmation_number": details["dispatch_confirmation_number"],
		"dhl_piece_tracking_numbers": piece_tracking_numbers,
		"dhl_creation_error": "",
		"shipment_id": tracking_number,
		"awb_number": tracking_number,
		"tracking_url": details["tracking_url"],
		"carrier_service": "DHL Express {0}".format(cstr(shipment.get("dhl_product_code")).strip()),
		"status": "Booked",
	})
	# Persist the AWB before processing optional files: a local attachment error
	# must never erase evidence of an already-created DHL shipment.
	frappe.db.commit()
	attached_documents, attachment_warnings = _attach_dhl_response_documents(
		shipment.name, tracking_number, raw_data
	)
	frappe.db.commit()
	return {
		"created": True,
		"outcome_unknown": False,
		"http_status": response.status_code,
		"http_reason": cstr(response.reason),
		"environment": environment,
		"message_reference": message_reference,
		"response_identifiers": response_identifiers,
		"response": safe_data,
		"shipment_tracking_number": tracking_number,
		"tracking_url": details["tracking_url"],
		"dispatch_confirmation_number": details["dispatch_confirmation_number"],
		"piece_tracking_numbers": details["piece_tracking_numbers"],
		"attached_documents": attached_documents,
		"warnings": attachment_warnings,
		"message": _("DHL created the shipment and returned AWB {0}.").format(tracking_number),
		"draft": draft,
	}
