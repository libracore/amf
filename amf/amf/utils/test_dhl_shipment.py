# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import unittest
from unittest.mock import MagicMock, patch

import frappe

from amf.amf.utils.dhl_shipment import (
	DHL_CONTENT_DESCRIPTION,
	DHLShipmentDraftBuilder,
	_bundled_iso_country_code,
	_delivery_note_package,
	_delivery_note_item_weight_kg,
	_dhl_creation_details,
	_dhl_payload_hash,
	_dhl_rejection_context,
	_dhl_product_query_from_draft,
	_dhl_response_documents,
	_extract_dhl_validation_errors,
	_incoterm_from_delivery_note,
	_sanitize_dhl_response_data,
	_strict_delivery_note_number,
	create_dhl_shipment,
	get_explicit_incoterm,
	is_dhl_carrier,
)


class AttrDict(dict):
	__getattr__ = dict.get


class AttrObject(object):
	def __init__(self, **values):
		self.__dict__.update(values)


class FakeMeta(object):
	def has_field(self, fieldname):
		return True


class FakeShipment(AttrDict):
	def __init__(self, **values):
		super(FakeShipment, self).__init__(**values)
		self.meta = FakeMeta()

	def check_permission(self, permission_type):
		return None

	def reload(self):
		return self


class FakeSettings(AttrDict):
	def get_password(self, fieldname, raise_exception=False):
		return self.get(fieldname)


class FakeResponse(object):
	def __init__(self, status_code, reason, data, headers=None):
		self.status_code = status_code
		self.reason = reason
		self._data = data
		self.headers = headers or {}
		self.text = ""

	def json(self):
		return self._data


class TestDHLShipmentHelpers(unittest.TestCase):
	def test_dhl_carrier_requires_standalone_token(self):
		self.assertTrue(is_dhl_carrier("DHL"))
		self.assertTrue(is_dhl_carrier("DHL (DAP)"))
		self.assertTrue(is_dhl_carrier("EXW (DHL 950164283)"))
		self.assertFalse(is_dhl_carrier("UPS"))
		self.assertFalse(is_dhl_carrier("DHLS"))
		self.assertFalse(is_dhl_carrier(""))

	def test_incoterm_is_returned_only_when_unambiguous(self):
		self.assertEqual(get_explicit_incoterm("SALES - DAP - 30 days net"), "DAP")
		self.assertEqual(get_explicit_incoterm("Delivery conditions: Incoterm EXW"), "EXW")
		self.assertIsNone(get_explicit_incoterm("SALES - 30 days net"))
		self.assertIsNone(get_explicit_incoterm("DAP DDP"))

	def test_delivery_note_terms_conflict_is_not_silently_resolved(self):
		value, error = _incoterm_from_delivery_note({
			"tc_name": "SALES - DAP - 30 days net",
			"terms": "<div><strong>Delivery conditions:</strong> Incoterm DDP</div>",
		})
		self.assertIsNone(value)
		self.assertEqual(error, "conflict")

	def test_content_description_fits_dhl_limit(self):
		self.assertEqual(
			DHL_CONTENT_DESCRIPTION,
			"OEM microfluidic pumps/rotary valves, non-medical, with accessories",
		)
		self.assertLessEqual(len(DHL_CONTENT_DESCRIPTION), 70)

	def test_delivery_note_decimal_comma_is_not_treated_as_thousands(self):
		self.assertEqual(float(_strict_delivery_note_number("0,7")), 0.7)
		self.assertEqual(float(_strict_delivery_note_number("1,25")), 1.25)
		self.assertIsNone(_strict_delivery_note_number("1,2,3"))

	def test_delivery_note_packaging_maps_one_measurement_set_to_one_parcel(self):
		parcel, error = _delivery_note_package({
			"name": "DN-TEST",
			"weight": "1,25",
			"length": "24",
			"width": "18",
			"height": "9",
		})
		self.assertIsNone(error)
		self.assertEqual(parcel, {"weight": 1.25, "length": 24, "width": 18, "height": 9, "count": 1})

	def test_delivery_note_packaging_rejects_fractional_dimensions(self):
		parcel, error = _delivery_note_package({
			"name": "DN-TEST",
			"weight": "1.2",
			"length": "24.5",
			"width": "18",
			"height": "9",
		})
		self.assertIsNone(parcel)
		self.assertEqual(error["code"], "fractional_delivery_note_dimensions")

	def test_common_country_name_resolves_through_bundled_iso_territories(self):
		self.assertEqual(_bundled_iso_country_code("South Korea"), "KR")
		self.assertEqual(_bundled_iso_country_code("Korea, Republic of"), "KR")
		self.assertIsNone(_bundled_iso_country_code("Not a country"))

	def test_explicit_total_weight_kg_label_resolves_invalid_nos_uom(self):
		resolution = _delivery_note_item_weight_kg(
			AttrDict(total_weight=0.05, weight_per_unit=0.05, qty=1, weight_uom="Nos"),
			"Total Weight kg",
			"Unit Weight kg",
		)
		self.assertEqual(resolution["value"], 0.05)
		self.assertTrue(resolution["label_based_kg"])
		self.assertEqual(resolution["ignored_weight_uom"], "Nos")

	def test_explicit_mass_uom_remains_authoritative_over_field_label(self):
		resolution = _delivery_note_item_weight_kg(
			AttrDict(total_weight=50, weight_per_unit=50, qty=1, weight_uom="Gram"),
			"Total Weight kg",
			"Unit Weight kg",
		)
		self.assertEqual(resolution["value"], 0.05)
		self.assertFalse(resolution["label_based_kg"])

	def test_receiver_full_name_falls_back_to_linked_sales_order_contact(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.delivery_notes = [AttrDict(name="DN-TEST", contact_person="", contact_display="")]
		builder.sales_orders = [AttrDict(name="SO-TEST", contact_person="CONTACT-1", contact_display="Stored Name")]
		builder.issues = []
		builder.sources = {}
		contact = AttrDict(name="CONTACT-1", full_name="Receiver Full Name", phone="+41 1", email_id="receiver@example.com")
		with patch("amf.amf.utils.dhl_shipment.frappe.get_doc", return_value=contact):
			full_name, contact_doc = builder._receiver_contact_full_name()
		self.assertEqual(full_name, "Receiver Full Name")
		self.assertIs(contact_doc, contact)
		self.assertIn(
			{"doctype": "Sales Order", "name": "SO-TEST", "fieldname": "contact_person"},
			builder.sources["customerDetails.receiverDetails.contactInformation.fullName"],
		)

	def test_conflicting_delivery_note_contacts_block_receiver_name(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.delivery_notes = [
			AttrDict(name="DN-1", contact_person="CONTACT-1", contact_display="First"),
			AttrDict(name="DN-2", contact_person="CONTACT-2", contact_display="Second"),
		]
		builder.sales_orders = []
		builder.issues = []
		builder.sources = {}
		full_name, contact_doc = builder._receiver_contact_full_name()
		self.assertIsNone(full_name)
		self.assertIsNone(contact_doc)
		self.assertEqual(builder.issues[0]["code"], "conflicting_receiver_contacts")

	def test_document_display_keeps_linked_contact_for_phone_and_email(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.delivery_notes = [AttrDict(name="DN-TEST", contact_person="CONTACT-1", contact_display="Stored Full Name")]
		builder.sales_orders = []
		builder.issues = []
		builder.sources = {}
		contact = AttrDict(name="CONTACT-1", full_name="", phone="+41 1", email_id="receiver@example.com")
		with patch("amf.amf.utils.dhl_shipment.frappe.get_doc", return_value=contact):
			full_name, contact_doc = builder._receiver_contact_full_name()
		self.assertEqual(full_name, "Stored Full Name")
		self.assertIs(contact_doc, contact)

	def test_dhl_problem_details_are_normalized_for_the_dialog(self):
		errors = _extract_dhl_validation_errors({
			"status": 400,
			"title": "Bad Request",
			"detail": "Input validation failed",
			"instance": "/shipments",
			"additionalDetails": [
				"220202: Receiver postal code is invalid",
				{
					"code": "220105",
					"field": "content.packages[0].weight",
					"message": "Package weight must be positive",
				},
			],
		})
		self.assertEqual(len(errors), 3)
		self.assertEqual(errors[0], {
			"message": "Input validation failed — Bad Request",
			"path": "/shipments",
		})
		self.assertEqual(errors[1], {
			"message": "Receiver postal code is invalid",
			"code": "220202",
			"path": "/shipments",
		})
		self.assertEqual(errors[2], {
			"message": "Package weight must be positive",
			"code": "220105",
			"path": "content.packages[0].weight",
		})

	def test_nested_dhl_error_shape_is_supported(self):
		errors = _extract_dhl_validation_errors({
			"errors": [{
				"errorCode": "E123",
				"path": "customerDetails.receiverDetails.contactInformation.fullName",
				"description": "Receiver full name is required",
			}],
		})
		self.assertEqual(errors, [{
			"message": "Receiver full name is required",
			"code": "E123",
			"path": "customerDetails.receiverDetails.contactInformation.fullName",
		}])

	def test_dhl_invalid_credentials_reason_is_reported(self):
		errors = _extract_dhl_validation_errors({
			"reasons": [{"msg": "Invalid Credentials"}],
			"details": {"msgId": "request-identifier"},
		})
		self.assertEqual(errors, [{"message": "Invalid Credentials"}])

	def test_dhl_401_is_reported_as_authentication_not_payload_rejection(self):
		context = _dhl_rejection_context(401, "Unauthorized", "Test", 1)
		self.assertEqual(context["failure_stage"], "authentication")
		self.assertEqual(context["validation_status"], "Authentication failed")
		self.assertIn("payload was not validated", context["message"])
		self.assertIn("Test environment", context["message"])

	def test_dhl_account_numbers_must_be_exactly_nine_alphanumeric_characters(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.issues = []
		self.assertEqual(
			builder.dhl_account_number("123456789", "accounts.payer", "DHL payer account"),
			"123456789",
		)
		self.assertIsNone(builder.dhl_account_number("123", "accounts.payer", "DHL payer account"))
		self.assertEqual(builder.issues[0]["code"], "invalid_dhl_account_number")
		self.assertIn("3 characters", builder.issues[0]["message"])

	def test_dhl_803_is_reported_as_account_service_authorization(self):
		errors = _extract_dhl_validation_errors({
			"instance": "/expressapi/shipments?validateDataOnly=true",
			"detail": "803: Account not allowed for this service. Please contact your DHL Express representative",
			"title": "Bad request",
		})
		self.assertEqual(errors[0]["code"], "803")
		context = _dhl_rejection_context(400, "Bad Request", "Test", len(errors), errors)
		self.assertEqual(context["failure_stage"], "account_service_authorization")
		self.assertEqual(context["validation_status"], "Account/service not allowed")

	def test_dhl_8007_is_reported_as_transport_product_lookup_failure(self):
		errors = _extract_dhl_validation_errors({"detail": "8007: Error getting Product details from GREF"})
		context = _dhl_rejection_context(400, "Bad Request", "Test", 1, errors)
		self.assertEqual(errors[0]["code"], "8007")
		self.assertEqual(context["failure_stage"], "product_lookup")
		self.assertEqual(context["validation_status"], "Transport product lookup failed")

	def test_product_query_uses_lane_one_package_date_and_customs_status(self):
		draft = {
			"payload": {
				"plannedShippingDateAndTime": "2026-08-14T16:00:00GMT+02:00",
				"accounts": [{"typeCode": "shipper", "number": "123456789"}],
				"customerDetails": {
					"shipperDetails": {"postalAddress": {"countryCode": "CH", "postalCode": "1024", "cityName": "Ecublens"}},
					"receiverDetails": {"postalAddress": {"countryCode": "FR", "postalCode": "42300", "cityName": "Mably"}},
				},
				"content": {
					"isCustomsDeclarable": True,
					"packages": [{"weight": 0.7, "dimensions": {"length": 20, "width": 16, "height": 10}}],
				},
			}
		}
		query, issues = _dhl_product_query_from_draft(draft)
		self.assertEqual(issues, [])
		self.assertEqual(query["plannedShippingDate"], "2026-08-14")
		self.assertEqual(query["unitOfMeasurement"], "metric")
		self.assertEqual(query["isCustomsDeclarable"], "true")
		self.assertEqual(query["weight"], 0.7)

	def test_dhl_payload_fingerprint_is_stable_for_json_key_order(self):
		first = {"productCode": "P", "content": {"description": "Pump", "packages": [1]}}
		second = {"content": {"packages": [1], "description": "Pump"}, "productCode": "P"}
		self.assertEqual(_dhl_payload_hash(first), _dhl_payload_hash(second))
		self.assertNotEqual(_dhl_payload_hash(first), _dhl_payload_hash({"productCode": "Y"}))

	def test_dhl_creation_identifiers_and_piece_ids_are_normalized(self):
		details = _dhl_creation_details({
			"shipmentTrackingNumber": "1103733901",
			"trackingUrl": "https://example.invalid/tracking/1103733901",
			"dispatchConfirmationNumber": "PRG123",
			"packages": [
				{"trackingNumber": "JD001"},
				{"trackingNumber": "JD002"},
				{"trackingNumber": "JD001"},
			],
		})
		self.assertEqual(details["shipment_tracking_number"], "1103733901")
		self.assertEqual(details["dispatch_confirmation_number"], "PRG123")
		self.assertEqual(details["piece_tracking_numbers"], ["JD001", "JD002"])

	def test_dhl_response_documents_include_piece_documents_and_are_sanitized(self):
		response = {
			"documents": [{"typeCode": "label", "imageFormat": "PDF", "content": "BASE64-A"}],
			"packages": [{
				"referenceNumber": 2,
				"documents": [{"typeCode": "qr-code", "imageFormat": "PNG", "content": "BASE64-B"}],
			}],
		}
		documents = _dhl_response_documents(response)
		self.assertEqual(len(documents), 2)
		self.assertEqual(documents[1]["packageReferenceNumber"], 2)
		safe_response = _sanitize_dhl_response_data(response)
		self.assertEqual(safe_response["documents"][0]["content"], "[base64 document omitted]")
		self.assertEqual(safe_response["packages"][0]["documents"][0]["content"], "[base64 document omitted]")
		self.assertEqual(response["documents"][0]["content"], "BASE64-A")

	def test_creation_refuses_changed_payload_without_contacting_dhl(self):
		shipment = FakeShipment(
			name="SHIPMENT-TEST",
			docstatus=0,
			carrier="DHL",
			dhl_creation_status="",
			shipment_id="",
			awb_number="",
			dhl_validation_status="Validated by DHL",
			dhl_validated_payload_hash=_dhl_payload_hash({"productCode": "P"}),
		)
		builder = AttrObject(build=lambda: {
			"ready_for_dhl_validation": True,
			"payload": {"productCode": "Y"},
		})
		frappe.local.db = MagicMock()
		try:
			with patch("amf.amf.utils.dhl_shipment.frappe.get_doc", return_value=shipment), \
				patch("amf.amf.utils.dhl_shipment.frappe.throw", side_effect=frappe.ValidationError), \
				patch("amf.amf.utils.dhl_shipment.DHLShipmentDraftBuilder", return_value=builder), \
				patch("amf.amf.utils.dhl_shipment.requests.post") as request:
				with self.assertRaises(frappe.ValidationError):
					create_dhl_shipment("SHIPMENT-TEST", "CREATE DHL SHIPMENT")
			request.assert_not_called()
		finally:
			del frappe.local.db

	def test_creation_refuses_existing_awb_without_contacting_dhl(self):
		shipment = FakeShipment(
			name="SHIPMENT-TEST",
			docstatus=0,
			carrier="DHL",
			dhl_creation_status="Created",
			shipment_id="1103733901",
			awb_number="1103733901",
		)
		frappe.local.db = MagicMock()
		try:
			with patch("amf.amf.utils.dhl_shipment.frappe.get_doc", return_value=shipment), \
				patch("amf.amf.utils.dhl_shipment.frappe.throw", side_effect=frappe.ValidationError), \
				patch("amf.amf.utils.dhl_shipment.requests.post") as request:
				with self.assertRaises(frappe.ValidationError):
					create_dhl_shipment("SHIPMENT-TEST", "CREATE DHL SHIPMENT")
			request.assert_not_called()
		finally:
			del frappe.local.db

	def test_creation_posts_without_validate_only_and_persists_returned_awb(self):
		payload = {"productCode": "P", "pickup": {"isRequested": False}}
		shipment = FakeShipment(
			name="SHIPMENT-TEST",
			docstatus=0,
			carrier="DHL",
			dhl_product_code="P",
			dhl_creation_status="",
			shipment_id="",
			awb_number="",
			dhl_validation_status="Validated by DHL",
			dhl_validated_environment="Test",
			dhl_validated_payload_hash=_dhl_payload_hash(payload),
		)
		builder = AttrObject(build=lambda: {"ready_for_dhl_validation": True, "payload": payload})
		settings = FakeSettings(api_username="username", api_password="password", api_environment="Test")
		response = FakeResponse(201, "Created", {
			"shipmentTrackingNumber": "1103733901",
			"trackingUrl": "https://example.invalid/tracking/1103733901",
			"packages": [{"trackingNumber": "JD001"}],
		}, headers={"Message-Reference": "returned-reference"})
		frappe.local.db = MagicMock()
		try:
			with patch("amf.amf.utils.dhl_shipment.frappe.get_doc", return_value=shipment), \
				patch("amf.amf.utils.dhl_shipment.frappe.get_single", return_value=settings), \
				patch("amf.amf.utils.dhl_shipment.DHLShipmentDraftBuilder", return_value=builder), \
				patch("amf.amf.utils.dhl_shipment.now_datetime", return_value="2026-08-14 12:00:00"), \
				patch("amf.amf.utils.dhl_shipment._set_existing_shipment_fields") as persist, \
				patch("amf.amf.utils.dhl_shipment._attach_dhl_response_documents", return_value=([], [])), \
				patch("amf.amf.utils.dhl_shipment.requests.post", return_value=response) as request:
				result = create_dhl_shipment("SHIPMENT-TEST", "CREATE DHL SHIPMENT")
			self.assertTrue(result["created"])
			self.assertEqual(result["shipment_tracking_number"], "1103733901")
			request.assert_called_once()
			request_kwargs = request.call_args.kwargs
			self.assertNotIn("params", request_kwargs)
			self.assertEqual(request_kwargs["json"], payload)
			self.assertEqual(len(request_kwargs["headers"]["Message-Reference"]), 36)
			self.assertTrue(any(
				call.args[1].get("awb_number") == "1103733901"
				for call in persist.call_args_list
			))
		finally:
			del frappe.local.db

	def test_customs_invoice_uses_submitted_sales_invoice_name_and_invoice_date(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.shipment = AttrDict(name="SHIPMENT-TEST", dhl_customs_invoice_number="", dhl_customs_invoice_date="")
		builder.sales_invoices = [AttrDict(name="SINV-01700", posting_date="2026-08-07")]
		builder.issues = []
		builder.sources = {}
		self.assertEqual(builder._customs_invoice(), {"number": "SINV-01700", "date": "2026-08-07"})
		self.assertEqual(
			builder.sources["content.exportDeclaration.invoice.date"],
			[{"doctype": "Sales Invoice", "name": "SINV-01700", "fieldname": "posting_date (Invoice Date)"}],
		)

	def test_customs_invoice_without_sales_invoice_requires_explicit_date(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.shipment = AttrDict(name="SHIPMENT-TEST", dhl_customs_invoice_number="", dhl_customs_invoice_date="")
		builder.sales_invoices = []
		builder.issues = []
		builder.sources = {}
		self.assertIsNone(builder._customs_invoice())
		self.assertEqual(builder.issues[0]["code"], "missing_customs_invoice_date")

	def test_multiple_sales_invoices_require_exact_explicit_selection(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.shipment = AttrDict(
			name="SHIPMENT-TEST",
			dhl_customs_invoice_number="SINV-2",
			dhl_customs_invoice_date="2026-08-08",
		)
		builder.sales_invoices = [
			AttrDict(name="SINV-1", posting_date="2026-08-07"),
			AttrDict(name="SINV-2", posting_date="2026-08-08"),
		]
		builder.issues = []
		builder.sources = {}
		self.assertEqual(builder._customs_invoice(), {"number": "SINV-2", "date": "2026-08-08"})
		self.assertEqual(builder.issues, [])

	def test_manual_customs_invoice_date_cannot_override_submitted_invoice_date(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.shipment = AttrDict(
			name="SHIPMENT-TEST",
			dhl_customs_invoice_number="",
			dhl_customs_invoice_date="2026-08-09",
		)
		builder.sales_invoices = [AttrDict(name="SINV-01700", posting_date="2026-08-07")]
		builder.issues = []
		builder.sources = {}
		self.assertIsNone(builder._customs_invoice())
		self.assertEqual(builder.issues[0]["code"], "customs_invoice_date_conflict")

	def test_each_delivery_note_item_tariff_maps_to_its_own_outbound_commodity_code(self):
		builder = object.__new__(DHLShipmentDraftBuilder)
		builder.delivery_notes = [AttrObject(
			name="DN-TEST",
			items=[
				AttrDict(name="DNI-1", item_code="ITEM-1", customs_tariff_number_="8481 80 99 70"),
				AttrDict(name="DNI-2", item_code="ITEM-2", customs_tariff_number_="8413 60 39 90"),
			],
		)]
		self.assertEqual(builder._customs_commodity_codes(), [
			{
				"line_number": 1,
				"delivery_note": "DN-TEST",
				"delivery_note_item": "DNI-1",
				"item_code": "ITEM-1",
				"source_field": "customs_tariff_number_",
				"source_value": "8481 80 99 70",
				"dhl_type_code": "outbound",
				"dhl_value": "8481809970",
			},
			{
				"line_number": 2,
				"delivery_note": "DN-TEST",
				"delivery_note_item": "DNI-2",
				"item_code": "ITEM-2",
				"source_field": "customs_tariff_number_",
				"source_value": "8413 60 39 90",
				"dhl_type_code": "outbound",
				"dhl_value": "8413603990",
			},
		])


if __name__ == "__main__":
	unittest.main()
