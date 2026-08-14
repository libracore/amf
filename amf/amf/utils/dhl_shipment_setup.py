# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def install_dhl_shipment_fields():
	"""Install the explicit operator inputs and validation audit fields."""
	create_custom_fields(
		{
			"Shipment": [
				{
					"fieldname": "dhl_shipment_draft_section",
					"fieldtype": "Section Break",
					"label": "DHL Express Draft",
					"insert_after": "description_of_content",
					"collapsible": 1,
					"depends_on": "eval:doc.carrier && /(^|[^A-Z0-9])DHL($|[^A-Z0-9])/i.test(doc.carrier)",
				},
				{
					"fieldname": "dhl_product_code",
					"fieldtype": "Data",
					"label": "DHL Transport Product Code (Global)",
					"description": "One shipment-wide DHL transport service code returned by MyDHL Product/Rating or confirmed by DHL. This is not an HS/customs tariff number; each Delivery Note Item customs_tariff_number_ is sent separately as its outbound customs commodity code.",
					"insert_after": "dhl_shipment_draft_section",
				},
				{
					"fieldname": "dhl_customs_declarable",
					"fieldtype": "Select",
					"label": "DHL Customs Declarable",
					"options": "\nYes\nNo",
					"description": "Required explicit decision. The algorithm does not infer customs status from the countries.",
					"insert_after": "dhl_product_code",
				},
				{
					"fieldname": "dhl_customs_invoice_date",
					"fieldtype": "Date",
					"label": "DHL Customs Invoice Date",
					"description": "MyDHL customs invoice issue date. A single submitted Sales Invoice linked through the Delivery Note is authoritative; otherwise this explicit date is required. The DN date, pickup date, and current date are never substituted.",
					"insert_after": "dhl_customs_declarable",
					"depends_on": "eval:doc.dhl_customs_declarable == 'Yes'",
				},
				{
					"fieldname": "dhl_customs_invoice_number",
					"fieldtype": "Data",
					"label": "DHL Customs Invoice Number",
					"description": "Optional when no submitted Sales Invoice is linked; maximum 35 characters. When a single submitted Sales Invoice exists, its document name is sent and conflicting manual input is blocked.",
					"insert_after": "dhl_customs_invoice_date",
					"depends_on": "eval:doc.dhl_customs_declarable == 'Yes'",
				},
				{
					"fieldname": "dhl_draft_accounts_column",
					"fieldtype": "Column Break",
					"insert_after": "dhl_customs_invoice_number",
				},
				{
					"fieldname": "dhl_payer_account_number",
					"fieldtype": "Data",
					"label": "DHL Payer Account Number",
					"description": "Optional shipment-specific payer account. It is not extracted from free-text Carrier values.",
					"insert_after": "dhl_draft_accounts_column",
				},
				{
					"fieldname": "dhl_duties_taxes_account_number",
					"fieldtype": "Data",
					"label": "DHL Duties/Taxes Account Number",
					"description": "Optional DHL Express billing account for duties/taxes. This is not an EIN/EORI; Organization EIN/EORI is sent separately as a DHL registration number.",
					"insert_after": "dhl_payer_account_number",
				},
				{
					"fieldname": "dhl_validation_section",
					"fieldtype": "Section Break",
					"label": "DHL Validation",
					"insert_after": "dhl_duties_taxes_account_number",
					"collapsible": 1,
					"collapsible_depends_on": "dhl_validation_status",
				},
				{
					"fieldname": "dhl_validation_status",
					"fieldtype": "Select",
					"label": "DHL Validation Status",
					"options": "\nValidated by DHL\nRejected by DHL\nAuthentication failed\nAuthorization failed\nAccount/service not allowed\nTransport product lookup failed",
					"insert_after": "dhl_validation_section",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_last_validation",
					"fieldtype": "Datetime",
					"label": "DHL Last Validation",
					"insert_after": "dhl_validation_status",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_validated_environment",
					"fieldtype": "Select",
					"label": "DHL Validated Environment",
					"options": "\nTest\nProduction",
					"insert_after": "dhl_last_validation",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_validated_payload_hash",
					"fieldtype": "Data",
					"label": "DHL Validated Payload Fingerprint",
					"insert_after": "dhl_validated_environment",
					"read_only": 1,
					"hidden": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_creation_section",
					"fieldtype": "Section Break",
					"label": "DHL Creation",
					"insert_after": "dhl_validated_payload_hash",
					"collapsible": 1,
					"collapsible_depends_on": "dhl_creation_status",
				},
				{
					"fieldname": "dhl_creation_status",
					"fieldtype": "Select",
					"label": "DHL Creation Status",
					"options": "\nCreation in progress\nCreated\nCreation failed\nCreation outcome unknown",
					"description": "Outcome unknown blocks automatic retries because DHL may have accepted the request even though ERPNext did not receive the response.",
					"insert_after": "dhl_creation_section",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_last_creation",
					"fieldtype": "Datetime",
					"label": "DHL Last Creation Attempt",
					"insert_after": "dhl_creation_status",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_creation_environment",
					"fieldtype": "Select",
					"label": "DHL Creation Environment",
					"options": "\nTest\nProduction",
					"insert_after": "dhl_last_creation",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_creation_audit_column",
					"fieldtype": "Column Break",
					"insert_after": "dhl_creation_environment",
				},
				{
					"fieldname": "dhl_message_reference",
					"fieldtype": "Data",
					"label": "DHL Message Reference",
					"description": "Unique identifier sent with the irreversible Create Shipment request. Use it when asking DHL to investigate an unknown outcome.",
					"insert_after": "dhl_creation_audit_column",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_dispatch_confirmation_number",
					"fieldtype": "Data",
					"label": "DHL Pickup Dispatch Confirmation",
					"insert_after": "dhl_message_reference",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_piece_tracking_numbers",
					"fieldtype": "Small Text",
					"label": "DHL Piece Tracking Numbers",
					"insert_after": "dhl_dispatch_confirmation_number",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_creation_error",
					"fieldtype": "Long Text",
					"label": "DHL Creation Error / Audit Response",
					"insert_after": "dhl_piece_tracking_numbers",
					"read_only": 1,
					"no_copy": 1,
				},
				{
					"fieldname": "dhl_creation_payload_hash",
					"fieldtype": "Data",
					"label": "DHL Creation Payload Fingerprint",
					"insert_after": "dhl_creation_error",
					"read_only": 1,
					"hidden": 1,
					"no_copy": 1,
				},
			],
		},
		update=True,
	)
	settings = frappe.get_single("AMF DHL Settings")
	if not settings.get("api_environment"):
		settings.api_environment = "Test"
		settings.flags.ignore_permissions = True
		settings.save()
	frappe.clear_cache(doctype="Shipment")
