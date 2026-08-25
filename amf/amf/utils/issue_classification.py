# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

"""Governed Issue process, classification and ownership model for AMF."""

from __future__ import unicode_literals

import math
import re
import unicodedata

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, cstr


PROCESS_DEFINITIONS = (
	{
		"code": "SMQ",
		"name": "Quality Management System (SMQ)",
		"primary_owner": "maximilien.guerin@amf.ch",
		"description": "Quality system, audits, compliance, safety and cross-process improvement.",
	},
	{
		"code": "MKT",
		"name": "Marketing",
		"primary_owner": "nathan.favereau@amf.ch",
		"description": "Brand, content, website, campaigns, events and lead generation.",
	},
	{
		"code": "SCS",
		"name": "Sales & Customer Service",
		"primary_owner": "tristan.bolmont@amf.ch",
		"description": "Commercial commitments, customer communication, complaint intake and service coordination.",
	},
	{
		"code": "PUR",
		"name": "Procurement",
		"primary_owner": "alexandre.ringwald@amf.ch",
		"description": "Purchasing, supplier performance, purchased material and external processing.",
	},
	{
		"code": "MFG",
		"name": "Manufacturing",
		"primary_owner": "alexandre.ringwald@amf.ch",
		"description": "Planning, machining, assembly, inspection, production records and traceability.",
	},
	{
		"code": "IS",
		"name": "Information System",
		"primary_owner": "alexandre.ringwald@amf.ch",
		"description": "ERPNext, business applications, access, infrastructure, devices, data and security.",
	},
	{
		"code": "LOG",
		"name": "Packaging & Shipping",
		"primary_owner": "alexandre.trachsel@amf.ch",
		"description": "Picking, packaging, labelling, shipping documentation, carriers and delivery condition.",
	},
	{
		"code": "MNT",
		"name": "Maintenance",
		"primary_owner": "alexandre.trachsel@amf.ch",
		"description": "Production equipment, preventive maintenance, tooling, facilities and utilities.",
	},
	{
		"code": "RND",
		"name": "Research & Development",
		"primary_owner": "matthieu.gevers@amf.ch",
		"secondary_owner": "nicolas.craquelin@amf.ch",
		"description": "Product design, performance, reliability, electronics, firmware, product software and specifications.",
	},
)


def _issue_type(code, name, process, description):
	return {
		"code": code,
		"name": name,
		"process": process,
		"description": description,
	}


ISSUE_TYPE_DEFINITIONS = (
	# Quality Management System (SMQ)
	_issue_type("SMQ-AUD", "Audit Nonconformity", "Quality Management System (SMQ)", "Internal, customer or certification audit finding requiring correction and follow-up."),
	_issue_type("SMQ-QMS", "QMS / Procedure Nonconformity", "Quality Management System (SMQ)", "Missing, incorrect, uncontrolled or ineffective procedure, record or management-system control."),
	_issue_type("SMQ-CMP", "Regulatory / Compliance Issue", "Quality Management System (SMQ)", "Legal, regulatory, contractual-compliance or certification requirement is at risk or not met."),
	_issue_type("SMQ-HSE", "Health, Safety & Environment Incident", "Quality Management System (SMQ)", "Actual or potential health, workplace-safety or environmental incident."),
	_issue_type("SMQ-CI", "Continuous Improvement Opportunity", "Quality Management System (SMQ)", "Cross-process weakness or improvement proposal not better owned by one operational process."),
	# Marketing
	_issue_type("MKT-WEB", "Website / Digital Marketing Issue", "Marketing", "Website, form, SEO, analytics or other marketing-channel malfunction or content defect."),
	_issue_type("MKT-BRD", "Marketing Content / Brand Issue", "Marketing", "Incorrect, missing or inconsistent brand, product-marketing or public-facing content."),
	_issue_type("MKT-CAM", "Campaign / Event / Lead Generation Issue", "Marketing", "Campaign, event, lead capture, qualification handover or marketing automation problem."),
	# Sales and customer service
	_issue_type("SCS-QUO", "Quotation / Pricing Issue", "Sales & Customer Service", "Quotation, selling price, discount, currency or commercial offer is missing or incorrect."),
	_issue_type("SCS-ORD", "Sales Order / Commercial Terms Issue", "Sales & Customer Service", "Customer requirement, order entry, acknowledgement, scope or commercial commitment is incorrect or unclear."),
	_issue_type("SCS-COM", "Customer Communication / Service Issue", "Sales & Customer Service", "Customer response, communication, support coordination or service follow-up is late, missing or incorrect."),
	_issue_type("SCS-TRI", "Customer Complaint - Triage Pending", "Sales & Customer Service", "Temporary intake classification when a customer complaint has not yet been attributed to the process that must prevent recurrence."),
	# Procurement
	_issue_type("PUR-PO", "Purchase Order / Purchasing Data Issue", "Procurement", "Purchase order, quantity, price, specification, item or supplier data is missing or incorrect."),
	_issue_type("PUR-DEL", "Supplier Delivery / Availability Issue", "Procurement", "Supplier delay, shortage, availability or delivery-quantity problem."),
	_issue_type("PUR-QUA", "Supplier Quality Nonconformity", "Procurement", "Purchased material, component or external service does not meet the defined requirement."),
	_issue_type("PUR-DOC", "Supplier Documentation / Certificate Issue", "Procurement", "Supplier certificate, declaration, inspection record or required document is missing or incorrect."),
	_issue_type("PUR-SUB", "External Processing / Subcontracting Issue", "Procurement", "Nonconformity or coordination failure involving outsourced manufacturing or another external process."),
	# Manufacturing
	_issue_type("MFG-PLN", "Production Planning / Scheduling Issue", "Manufacturing", "Production plan, sequence, capacity, material readiness or work-order release is incorrect or late."),
	_issue_type("MFG-MCH", "Machining / Dimensional Nonconformity", "Manufacturing", "Machined feature, tolerance, surface or dimension does not conform to the released definition."),
	_issue_type("MFG-ASM", "Assembly / Workmanship Nonconformity", "Manufacturing", "Assembly, wiring, fastening, orientation or workmanship does not meet the requirement."),
	_issue_type("MFG-ELC", "Electrical / Electronic Manufacturing Nonconformity", "Manufacturing", "Electronic component, PCB, cable or electrical assembly fails due to production or workmanship."),
	_issue_type("MFG-TST", "Production Test / Inspection Failure", "Manufacturing", "Production test, inspection, control plan or acceptance record is failed, missing or incorrectly executed."),
	_issue_type("MFG-TRC", "Manufacturing Material / Traceability Issue", "Manufacturing", "Wrong material, batch, serial, BOM, route or production traceability information is used or missing."),
	_issue_type("MFG-PRC", "Production Process / Yield Issue", "Manufacturing", "Recurring production-process instability, excessive scrap, rework, bottleneck or yield loss."),
	# Information system
	_issue_type("IS-ERP", "ERPNext / Business Application Issue", "Information System", "ERPNext or another internal business application is unavailable, incorrect or behaves unexpectedly."),
	_issue_type("IS-ACC", "IT Access / User Account Issue", "Information System", "Account, role, permission, authentication or access request/problem."),
	_issue_type("IS-INF", "IT Infrastructure / Device Issue", "Information System", "Computer, phone, network, printer, server or other internal IT asset is unavailable, damaged or lost."),
	_issue_type("IS-DAT", "Data / Master Data Issue", "Information System", "Business data is missing, duplicated, inconsistent or governed incorrectly in an information system."),
	_issue_type("IS-SEC", "Information Security / Data Protection Incident", "Information System", "Actual or suspected confidentiality, integrity, availability or personal-data incident."),
	# Packaging and shipping
	_issue_type("LOG-PKG", "Packaging / Product Protection Issue", "Packaging & Shipping", "Packaging method, material or protection is missing, incorrect or insufficient."),
	_issue_type("LOG-PCK", "Picking / Quantity / Item Error", "Packaging & Shipping", "Wrong item, accessory, quantity or destination is picked or packed."),
	_issue_type("LOG-LBL", "Labelling / Shipping Documentation Issue", "Packaging & Shipping", "Product/shipping label, packing list, customs or transport document is missing or incorrect."),
	_issue_type("LOG-SHP", "Shipment / Carrier / Delivery Issue", "Packaging & Shipping", "Dispatch, carrier selection, tracking, delivery timing or delivery execution problem."),
	_issue_type("LOG-DMG", "Transit Damage / Delivery Condition Issue", "Packaging & Shipping", "Goods are damaged, lost or delivered in an unacceptable condition during transport."),
	# Maintenance
	_issue_type("MNT-BRK", "Equipment Breakdown", "Maintenance", "Production or test equipment is unavailable or cannot perform its intended function."),
	_issue_type("MNT-PRE", "Preventive Maintenance Issue", "Maintenance", "Preventive maintenance is late, missed, ineffective or recorded incorrectly."),
	_issue_type("MNT-TOL", "Tooling / Fixture Issue", "Maintenance", "Tool, jig, fixture, gauge or production aid is damaged, unsuitable or unavailable."),
	_issue_type("MNT-FAC", "Facility / Utility Issue", "Maintenance", "Building, power, compressed air, extraction, climate or another facility utility is impaired."),
	# Research and development
	_issue_type("RND-MEC", "Mechanical Design / Product Issue", "Research & Development", "Mechanical product behaviour, interface, fit, strength or design definition is defective or unclear."),
	_issue_type("RND-FLU", "Fluidic / Performance Design Issue", "Research & Development", "Leakage, pressure, flow, pumping, valve behaviour or product performance indicates a design-level issue."),
	_issue_type("RND-ELC", "Electrical / Electronic Design Issue", "Research & Development", "Electrical architecture, PCB, component selection, interface or electronic design is defective or unclear."),
	_issue_type("RND-FW", "Firmware / Embedded Software Issue", "Research & Development", "Product firmware, embedded control logic, protocol or device configuration does not behave as specified."),
	_issue_type("RND-SW", "Product Software / Integration Issue", "Research & Development", "Customer-facing product software, driver, script, API or product integration does not behave as specified."),
	_issue_type("RND-DOC", "Product Specification / R&D Documentation Issue", "Research & Development", "Product specification, drawing, datasheet, design record or released R&D document is missing or incorrect."),
	_issue_type("RND-LIFE", "Product Reliability / Lifetime Issue", "Research & Development", "Product wear, durability, lifetime or recurring field reliability does not meet expectations."),
)


# The vocabulary is deliberately explicit and auditable.  It supplements the
# words already present in each Issue Type name and description.  User-confirmed
# classifications are also learned from historical Issue subjects (see
# _build_issue_suggestion_history_model), so the suggestions improve as the
# team uses them without silently changing any Issue Type.
ISSUE_TYPE_SUGGESTION_TERMS = {
	"Audit Nonconformity": ("audit", "audit finding", "certification finding", "audit observation"),
	"QMS / Procedure Nonconformity": ("procedure", "work instruction", "sop", "uncontrolled document", "missing record", "qms"),
	"Regulatory / Compliance Issue": ("regulatory", "compliance", "legal requirement", "ce marking", "reach", "rohs", "certification requirement"),
	"Health, Safety & Environment Incident": ("safety", "accident", "injury", "near miss", "environmental incident", "spill", "hazard"),
	"Continuous Improvement Opportunity": ("continuous improvement", "improvement idea", "kaizen", "inefficiency", "process improvement"),
	"Website / Digital Marketing Issue": ("website", "web form", "seo", "analytics", "digital campaign", "landing page"),
	"Marketing Content / Brand Issue": ("marketing content", "brand", "brochure", "social media", "public content", "logo"),
	"Campaign / Event / Lead Generation Issue": ("campaign", "event", "trade show", "lead generation", "lead capture", "marketing automation"),
	"Quotation / Pricing Issue": ("quotation", "quote", "selling price", "discount", "commercial offer", "price error"),
	"Sales Order / Commercial Terms Issue": ("sales order", "customer order", "order acknowledgement", "commercial terms", "incoterm", "customer requirement"),
	"Customer Communication / Service Issue": ("customer communication", "customer service", "no response", "support follow up", "service request"),
	"Customer Complaint - Triage Pending": ("customer complaint", "complaint", "customer claim", "complaint triage"),
	"Purchase Order / Purchasing Data Issue": ("purchase order", "purchasing data", "buying price", "supplier master", "purchase price"),
	"Supplier Delivery / Availability Issue": ("supplier delay", "supplier delivery", "delivery from supplier", "material shortage", "supplier availability", "late material"),
	"Supplier Quality Nonconformity": ("supplier quality", "incoming inspection", "purchased material defect", "nonconforming supplier", "supplier reject"),
	"Supplier Documentation / Certificate Issue": ("supplier certificate", "material certificate", "missing certificate", "certificate of conformity", "supplier documentation"),
	"External Processing / Subcontracting Issue": ("subcontractor", "subcontracting", "external processing", "outsourced manufacturing", "external service"),
	"Production Planning / Scheduling Issue": ("production planning", "production schedule", "capacity planning", "work order release", "material readiness"),
	"Machining / Dimensional Nonconformity": ("machining", "dimension", "tolerance", "surface finish", "out of tolerance", "machined part"),
	"Assembly / Workmanship Nonconformity": ("assembly", "workmanship", "wiring error", "fastening", "wrong orientation", "assembly defect"),
	"Electrical / Electronic Manufacturing Nonconformity": ("soldering", "pcb soldering", "pcb assembly", "electronic assembly", "cable assembly", "electrical workmanship"),
	"Production Test / Inspection Failure": ("production test", "inspection failure", "test failure", "control plan", "acceptance test", "inspection record"),
	"Manufacturing Material / Traceability Issue": ("traceability", "wrong material", "wrong batch", "wrong serial", "wrong bom", "production route"),
	"Production Process / Yield Issue": ("yield", "scrap", "rework", "process instability", "production bottleneck", "cycle time"),
	"ERPNext / Business Application Issue": ("erpnext", "erpnext error", "erp", "business application", "system error", "application error", "server error"),
	"IT Access / User Account Issue": ("user account", "login", "password", "permission denied", "access request", "authentication", "role permission"),
	"IT Infrastructure / Device Issue": ("computer", "laptop", "phone", "network", "printer", "server", "it device", "company device"),
	"Data / Master Data Issue": ("master data", "duplicate data", "missing data", "incorrect data", "data inconsistency", "duplicate record"),
	"Information Security / Data Protection Incident": ("information security", "data breach", "phishing", "malware", "personal data", "cyber security", "unauthorized access"),
	"Packaging / Product Protection Issue": ("packaging", "product protection", "packing material", "insufficient protection", "wrong packaging"),
	"Picking / Quantity / Item Error": ("picking error", "wrong item", "wrong quantity", "missing accessory", "wrong destination", "packing error"),
	"Labelling / Shipping Documentation Issue": ("shipping label", "wrong label", "packing list", "customs document", "transport document", "shipping documentation"),
	"Shipment / Carrier / Delivery Issue": ("shipment", "carrier", "tracking", "dispatch", "delivery delay", "late delivery", "transport delay"),
	"Transit Damage / Delivery Condition Issue": ("transit damage", "damaged in transport", "delivery damage", "lost shipment", "damaged parcel", "delivery condition"),
	"Equipment Breakdown": ("equipment breakdown", "machine breakdown", "machine stopped", "equipment failure", "machine failure", "production equipment"),
	"Preventive Maintenance Issue": ("preventive maintenance", "maintenance overdue", "missed maintenance", "maintenance plan", "maintenance record"),
	"Tooling / Fixture Issue": ("tooling", "fixture", "jig", "gauge", "broken tool", "production aid"),
	"Facility / Utility Issue": ("facility", "power outage", "compressed air", "extraction", "heating", "cooling", "building", "utility"),
	"Mechanical Design / Product Issue": ("mechanical design", "product fit", "mechanical interface", "strength", "mechanical drawing", "design tolerance"),
	"Fluidic / Performance Design Issue": ("leak", "leakage", "pressure", "flow", "pump performance", "valve behavior", "fluidic"),
	"Electrical / Electronic Design Issue": ("electronic design", "electrical design", "pcb design", "component selection", "electrical interface", "circuit"),
	"Firmware / Embedded Software Issue": ("firmware", "embedded software", "device firmware", "bootloader", "embedded control", "device protocol"),
	"Product Software / Integration Issue": ("product software", "driver", "api", "software integration", "customer integration", "product script"),
	"Product Specification / R&D Documentation Issue": ("product specification", "drawing error", "datasheet", "design record", "rnd document", "released drawing"),
	"Product Reliability / Lifetime Issue": ("reliability", "lifetime", "durability", "wear", "fatigue", "recurring field failure", "premature failure"),
}


# Lightweight multilingual normalization for the vocabulary most often used at
# AMF.  Both subjects and configured terms pass through this map.
ISSUE_SUGGESTION_TOKEN_ALIASES = {
	"acces": "access", "accès": "access", "zugriff": "access",
	"achat": "purchase", "einkauf": "purchase",
	"ausfall": "breakdown", "panne": "breakdown",
	"broken": "breakdown",
	"beschadigt": "damage", "beschädigt": "damage", "dommage": "damage", "endommage": "damage", "endommagé": "damage",
	"damaged": "damage",
	"commande": "order", "bestellung": "order",
	"compte": "account", "konto": "account",
	"debit": "flow", "débit": "flow", "durchfluss": "flow",
	"devis": "quotation", "offre": "quotation",
	"emballage": "packaging", "verpackung": "packaging",
	"erreur": "error", "fehler": "error",
	"incorrect": "error", "wrong": "error",
	"etiquette": "label", "étiquette": "label", "etikett": "label",
	"expedition": "shipment", "expédition": "shipment", "versand": "shipment",
	"fournisseur": "supplier", "lieferant": "supplier",
	"fuite": "leak", "leck": "leak",
	"imprimante": "printer", "drucker": "printer",
	"lieferung": "delivery", "livraison": "delivery",
	"late": "delay", "delayed": "delay",
	"leaked": "leak", "leaking": "leak",
	"logiciel": "software", "anwendung": "application",
	"maintenance": "maintenance", "wartung": "maintenance",
	"manquant": "missing", "manquante": "missing", "fehlend": "missing",
	"micrologiciel": "firmware",
	"motdepasse": "password", "passwort": "password",
	"outillage": "tooling", "werkzeug": "tooling",
	"pression": "pressure", "druck": "pressure",
	"prix": "price", "preis": "price",
	"qualite": "quality", "qualität": "quality",
	"reclamation": "complaint", "réclamation": "complaint", "reklamation": "complaint",
	"reseau": "network", "réseau": "network", "netzwerk": "network",
	"retard": "delay", "verspatung": "delay", "verspätung": "delay",
	"securite": "safety", "sécurité": "safety", "sicherheit": "safety",
	"usinage": "machining", "bearbeitung": "machining",
}

ISSUE_SUGGESTION_STOP_WORDS = frozenset((
	"a", "after", "an", "and", "are", "at", "be", "by", "de", "des", "did", "does", "du", "during",
	"en", "et", "for", "from", "had", "has", "have", "in", "is", "issue", "la", "le", "les", "of",
	"on", "or", "problem", "the", "to", "un", "une", "und", "von", "when", "while", "with", "zu",
))
ISSUE_SUGGESTION_CACHE_KEY = "amf:issue-type-suggestion-history:v1"
ISSUE_SUGGESTION_HISTORY_TTL = 900


# Legacy choices remain in the database for historical auditability. Open records are
# moved to these canonical types; closed records retain the classification used at closure.
LEGACY_ISSUE_TYPE_MAP = {
	"Documentation R&D Issue": "Product Specification / R&D Documentation Issue",
	"Safety Issue": "Health, Safety & Environment Incident",
	"Fluidic Issue": "Fluidic / Performance Design Issue",
	"Software Issue": "Product Software / Integration Issue",
	"Firmware Issue": "Firmware / Embedded Software Issue",
	"Process Issue": "QMS / Procedure Nonconformity",
	"Documentation Issue": "QMS / Procedure Nonconformity",
	"Hardware Lifetime Issue": "Product Reliability / Lifetime Issue",
	"Human Resources Issue": "Continuous Improvement Opportunity",
	"Marketing Issue": "Marketing Content / Brand Issue",
	"Mechanic Issue": "Mechanical Design / Product Issue",
	"Sales Issue": "Sales Order / Commercial Terms Issue",
	"Shipping Issue": "Shipment / Carrier / Delivery Issue",
	"Lost company property": "IT Infrastructure / Device Issue",
	"Damaged company property": "IT Infrastructure / Device Issue",
	"Information System Failure": "ERPNext / Business Application Issue",
	"Procurement Issue": "Purchase Order / Purchasing Data Issue",
	"Production Issue": "Assembly / Workmanship Nonconformity",
	"Finished Goods Delivery Issue": "Picking / Quantity / Item Error",
	"Supplier Delivery Time Issue": "Supplier Delivery / Availability Issue",
	"Supplier Delivery Quality Issue": "Supplier Quality Nonconformity",
	"Electronic Issue": "Electrical / Electronic Manufacturing Nonconformity",
	"Equipment Breakdown Issue": "Equipment Breakdown",
}


# This is a resolution outcome, not a problem nature. It is deliberately not
# auto-mapped to a canonical Issue Type.
LEGACY_OUTCOME_TYPES = ("No issue found after analysis",)


ISSUE_CLASSIFICATION_CUSTOM_FIELDS = {
	"Issue Type": [
		{
			"fieldname": "classification_code",
			"fieldtype": "Data",
			"label": "Classification Code",
			"insert_after": "description",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"read_only": 1,
		},
		{
			"fieldname": "process",
			"fieldtype": "Link",
			"label": "Process",
			"options": "AMF Issue Process",
			"insert_after": "classification_code",
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "process_owner",
			"fieldtype": "Link",
			"label": "Primary Process Owner",
			"options": "User",
			"insert_after": "process",
			"fetch_from": "process.primary_owner",
			"read_only": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "process_co_owner",
			"fieldtype": "Link",
			"label": "Secondary Process Owner",
			"options": "User",
			"insert_after": "process_owner",
			"fetch_from": "process.secondary_owner",
			"read_only": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "is_active",
			"fieldtype": "Check",
			"label": "Active",
			"insert_after": "process_co_owner",
			"default": "1",
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
	],
	"Issue": [
		{
			"fieldname": "issue_type_suggestions",
			"fieldtype": "HTML",
			"label": "Smart Issue Type Suggestions",
			"insert_after": "issue_outcome",
			"print_hide": 1,
		},
		{
			"fieldname": "issue_type_user_confirmed",
			"fieldtype": "Check",
			"label": "Issue Type User Confirmed",
			"insert_after": "issue_type_suggestions",
			"default": "0",
			"hidden": 1,
			"no_copy": 1,
			"read_only": 1,
		},
		{
			"fieldname": "process_co_owner",
			"fieldtype": "Link",
			"label": "Secondary Process Owner",
			"options": "User",
			"insert_after": "process_owner",
			"read_only": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "issue_outcome",
			"fieldtype": "Select",
			"label": "Issue Outcome",
			"options": "\nConfirmed Nonconformity\nUnable to Reproduce\nNo Issue Found\nDuplicate\nUser / Configuration Error\nInformation Request",
			"insert_after": "process_co_owner",
			"in_standard_filter": 1,
		},
	],
	"AMF Issue Test": [
		{
			"fieldname": "issue_type_suggestions",
			"fieldtype": "HTML",
			"label": "Smart Issue Type Suggestions",
			"insert_after": "issue_outcome",
			"print_hide": 1,
		},
		{
			"fieldname": "issue_type_user_confirmed",
			"fieldtype": "Check",
			"label": "Issue Type User Confirmed",
			"insert_after": "issue_type_suggestions",
			"default": "0",
			"hidden": 1,
			"no_copy": 1,
			"read_only": 1,
		},
		{
			"fieldname": "process_co_owner",
			"fieldtype": "Link",
			"label": "Secondary Process Owner",
			"options": "User",
			"insert_after": "process_owner",
			"read_only": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "issue_outcome",
			"fieldtype": "Select",
			"label": "Issue Outcome",
			"options": "\nConfirmed Nonconformity\nUnable to Reproduce\nNo Issue Found\nDuplicate\nUser / Configuration Error\nInformation Request",
			"insert_after": "process_co_owner",
			"in_standard_filter": 1,
		},
	],
}


def sync_issue_classification_setup():
	"""Install and normalize the governed process/type model after migration."""
	create_custom_fields(ISSUE_CLASSIFICATION_CUSTOM_FIELDS, update=True)
	sync_issue_processes()
	sync_issue_types()
	migrate_open_legacy_issues()
	clear_issue_classification_cache()


def sync_issue_processes():
	for definition in PROCESS_DEFINITIONS:
		values = {
			"process_code": definition["code"],
			"process_name": definition["name"],
			"description": definition["description"],
			"primary_owner": _existing_user(definition.get("primary_owner")),
			"secondary_owner": _existing_user(definition.get("secondary_owner")),
			"enabled": 1,
		}

		if frappe.db.exists("AMF Issue Process", definition["name"]):
			doc = frappe.get_doc("AMF Issue Process", definition["name"])
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(dict(values, doctype="AMF Issue Process")).insert(ignore_permissions=True)


def sync_issue_types():
	processes = _processes_by_name()
	canonical_names = {definition["name"] for definition in ISSUE_TYPE_DEFINITIONS}

	for definition in ISSUE_TYPE_DEFINITIONS:
		process = processes[definition["process"]]
		values = {
			"description": definition["description"],
			"classification_code": definition["code"],
			"process": definition["process"],
			"process_owner": process.get("primary_owner"),
			"process_co_owner": process.get("secondary_owner"),
			"is_active": 1,
		}
		_upsert_issue_type(definition["name"], values)

	for legacy_name, canonical_name in LEGACY_ISSUE_TYPE_MAP.items():
		if not frappe.db.exists("Issue Type", legacy_name):
			continue
		canonical = _issue_types_by_name()[canonical_name]
		_update_issue_type(
			legacy_name,
			{
				"classification_code": "LEGACY",
				"process": canonical["process"],
				"process_owner": canonical.get("process_owner"),
				"process_co_owner": canonical.get("process_co_owner"),
				"is_active": 0,
			},
		)

	for legacy_outcome in LEGACY_OUTCOME_TYPES:
		if frappe.db.exists("Issue Type", legacy_outcome):
			_update_issue_type(
				legacy_outcome,
				{
					"classification_code": "LEGACY-OUTCOME",
					"process": "Sales & Customer Service",
					"process_owner": processes["Sales & Customer Service"].get("primary_owner"),
					"process_co_owner": processes["Sales & Customer Service"].get("secondary_owner"),
					"is_active": 0,
				},
			)

	# Any ungoverned type remains available historically but is no longer offered
	# for new classification.
	for row in frappe.get_all("Issue Type", fields=["name"]):
		if row.name not in canonical_names and row.name not in LEGACY_ISSUE_TYPE_MAP and row.name not in LEGACY_OUTCOME_TYPES:
			frappe.db.set_value("Issue Type", row.name, "is_active", 0, update_modified=False)


def migrate_open_legacy_issues():
	"""Reclassify active work only; preserve closed records as audit history."""
	for doctype in ("Issue", "AMF Issue Test"):
		if not frappe.db.table_exists(doctype):
			continue

		for legacy_name, canonical_name in LEGACY_ISSUE_TYPE_MAP.items():
			rows = frappe.get_all(
				doctype,
				filters={"issue_type": legacy_name, "status": ["!=", "Closed"]},
				fields=["name"],
			)
			for row in rows:
				values = get_issue_type_routing(canonical_name)
				values["issue_type"] = canonical_name
				frappe.db.set_value(doctype, row.name, values, update_modified=False)


def apply_issue_type_routing(doc, method=None):
	process_name = cstr(doc.get("process")).strip()
	if not process_name:
		doc.process_owner = None
		if _doc_has_field(doc, "process_co_owner"):
			doc.process_co_owner = None
		return

	owners = frappe.db.get_value(
		"AMF Issue Process",
		process_name,
		["primary_owner", "secondary_owner", "enabled"],
		as_dict=True,
	)
	if not owners:
		frappe.throw(_("Unknown Issue Process: {0}").format(process_name))
	if not cint(owners.enabled):
		frappe.throw(_("Issue Process {0} is disabled.").format(process_name))

	doc.process_owner = owners.primary_owner
	if _doc_has_field(doc, "process_co_owner"):
		doc.process_co_owner = owners.secondary_owner


def apply_issue_routing(doc, method=None):
	issue_type = cstr(doc.get("issue_type")).strip()
	if not issue_type:
		return

	routing = get_issue_type_routing(issue_type, include_active=True)
	if not routing:
		frappe.throw(_("Unknown Issue Type: {0}").format(issue_type))
	if doc.is_new() and not cint(routing.pop("is_active", 0)):
		frappe.throw(_("Issue Type {0} is retired. Select an active Issue Type.").format(issue_type))
	routing.pop("is_active", None)

	for fieldname, value in routing.items():
		if _doc_has_field(doc, fieldname):
			doc.set(fieldname, value)


def get_issue_type_routing(issue_type, include_active=False):
	fields = ["process", "process_owner", "process_co_owner"]
	if include_active:
		fields.append("is_active")
	values = frappe.db.get_value("Issue Type", issue_type, fields, as_dict=True)
	if not values:
		return None
	return _issue_type_values_to_routing(values, include_active=include_active)


@frappe.whitelist()
def suggest_issue_types(subject, limit=3):
	"""Return ranked active Issue Types for an Issue subject.

	The method never changes the Issue.  It combines the governed vocabulary with
	aggregated terms from previously confirmed classifications and leaves the final
	choice to the user.
	"""
	subject = cstr(subject).strip()[:500]
	limit = max(1, min(cint(limit) or 3, 5))
	if len(subject) < 3:
		return {"suggestions": [], "uses_history": False}

	candidates = frappe.get_all(
		"Issue Type",
		filters={"is_active": 1},
		fields=["name", "description", "classification_code", "process"],
		order_by="name asc",
	)
	history_model = _get_issue_suggestion_history_model()
	return {
		"suggestions": rank_issue_type_suggestions(
			subject,
			candidates=candidates,
			history_model=history_model,
			limit=limit,
		),
		"uses_history": bool(history_model.get("total_documents")),
	}


def rank_issue_type_suggestions(subject, candidates=None, history_model=None, limit=3):
	"""Pure ranking function used by the API and unit tests."""
	subject_normalized, subject_tokens = _normalize_issue_suggestion_text(subject)
	if len(subject_normalized) < 3 or not subject_tokens:
		return []

	if candidates is None:
		candidates = [
			{
				"name": definition["name"],
				"description": definition["description"],
				"classification_code": definition["code"],
				"process": definition["process"],
			}
			for definition in ISSUE_TYPE_DEFINITIONS
		]

	history_model = history_model or {}
	scored = []
	for candidate in candidates:
		candidate = dict(candidate)
		score, signals, history_documents = _score_issue_type_candidate(
			subject_normalized,
			subject_tokens,
			candidate,
			history_model,
		)
		if score <= 0:
			continue
		candidate["score"] = round(score, 2)
		candidate["signals"] = signals[:3]
		candidate["history_documents"] = history_documents
		scored.append(candidate)

	scored.sort(key=lambda row: (-row["score"], cstr(row.get("name"))))
	if not scored or scored[0]["score"] < 3:
		return []

	top_score = scored[0]["score"]
	second_score = scored[1]["score"] if len(scored) > 1 else 0
	minimum_score = max(3, top_score * 0.25)
	results = []
	for index, row in enumerate(scored):
		if len(results) >= limit or row["score"] < minimum_score:
			break

		gap = top_score - second_score if index == 0 else 0
		row["match_strength"] = _issue_suggestion_match_strength(row["score"], gap)
		# The internal score is useful for stable sorting but should not be presented
		# as a statistically calibrated probability.
		row.pop("score", None)
		results.append(row)

	return results


def _score_issue_type_candidate(subject_normalized, subject_tokens, candidate, history_model):
	name = cstr(candidate.get("name"))
	name_normalized, name_tokens = _normalize_issue_suggestion_text(name)
	_, description_tokens = _normalize_issue_suggestion_text(candidate.get("description"))
	_, process_tokens = _normalize_issue_suggestion_text(candidate.get("process"))
	subject_token_set = set(subject_tokens)
	score = 0.0
	signals = []

	if name_normalized and name_normalized in subject_normalized:
		score += 24
		signals.append(name)

	name_matches = subject_token_set.intersection(name_tokens)
	description_matches = subject_token_set.intersection(description_tokens)
	process_matches = subject_token_set.intersection(process_tokens)
	score += len(name_matches) * 2.0
	score += len(description_matches.difference(name_matches)) * 0.45
	score += len(process_matches.difference(name_matches)) * 0.25

	for term in ISSUE_TYPE_SUGGESTION_TERMS.get(name, ()):
		term_normalized, term_tokens = _normalize_issue_suggestion_text(term)
		if not term_tokens:
			continue
		if " {0} ".format(term_normalized) in " {0} ".format(subject_normalized):
			score += 5.0 + (2.0 * len(term_tokens))
			signals.append(term)
		elif set(term_tokens).issubset(subject_token_set):
			score += 2.5 + len(term_tokens)
			signals.append(term)

	if not signals and name_matches:
		signals.extend(sorted(name_matches))
	elif len(signals) < 3:
		for token in sorted(name_matches):
			if token not in signals:
				signals.append(token)

	history_score, history_documents = _score_issue_suggestion_history(
		name,
		subject_token_set,
		history_model,
	)
	score += history_score
	return score, _unique_values(signals), history_documents


def _score_issue_suggestion_history(issue_type, subject_tokens, history_model):
	type_model = history_model.get("types", {}).get(issue_type, {})
	document_count = cint(type_model.get("documents"))
	total_documents = cint(history_model.get("total_documents"))
	if document_count < 3 or total_documents < 3:
		return 0.0, 0

	token_documents = type_model.get("tokens", {})
	global_documents = history_model.get("token_documents", {})
	score = 0.0
	matched = False
	for token in subject_tokens:
		type_hits = cint(token_documents.get(token))
		if not type_hits:
			continue
		matched = True
		global_hits = max(1, cint(global_documents.get(token)))
		affinity = float(type_hits) / document_count
		inverse_frequency = math.log(float(total_documents + 1) / (global_hits + 1)) + 1.0
		score += 2.25 * affinity * inverse_frequency

	return min(score, 10.0), document_count if matched and score >= 1.0 else 0


def _issue_suggestion_match_strength(score, gap):
	if score >= 15 and gap >= 3:
		return "Strong"
	if score >= 8:
		return "Good"
	return "Possible"


def _normalize_issue_suggestion_text(value):
	text = unicodedata.normalize("NFKD", cstr(value))
	text = "".join(character for character in text if not unicodedata.combining(character)).lower()
	tokens = []
	for token in re.findall(r"[a-z0-9]+", text):
		token = ISSUE_SUGGESTION_TOKEN_ALIASES.get(token, token)
		if len(token) > 4 and token.endswith("ies"):
			token = token[:-3] + "y"
		elif len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
			token = token[:-1]
		if len(token) > 1 and token not in ISSUE_SUGGESTION_STOP_WORDS:
			tokens.append(token)
	return " ".join(tokens), tokens


def _get_issue_suggestion_history_model():
	cache = frappe.cache()
	model = cache.get_value(ISSUE_SUGGESTION_CACHE_KEY, expires=True)
	if model is None:
		model = _build_issue_suggestion_history_model()
		cache.set_value(
			ISSUE_SUGGESTION_CACHE_KEY,
			model,
			expires_in_sec=ISSUE_SUGGESTION_HISTORY_TTL,
		)
	return model


def _build_issue_suggestion_history_model():
	active_names = {
		row.name
		for row in frappe.get_all("Issue Type", filters={"is_active": 1}, fields=["name"])
	}
	model = {"total_documents": 0, "token_documents": {}, "types": {}}

	for doctype in ("Issue", "AMF Issue Test"):
		if not frappe.db.table_exists(doctype) or not frappe.get_meta(doctype).has_field("issue_type_user_confirmed"):
			continue

		rows = frappe.get_all(
			doctype,
			filters={
				"issue_type": ["is", "set"],
				"issue_type_user_confirmed": 1,
			},
			fields=["subject", "issue_type"],
			limit_page_length=10000,
		)
		for row in rows:
			issue_type = row.issue_type
			if issue_type not in active_names:
				continue
			_, tokens = _normalize_issue_suggestion_text(row.subject)
			tokens = set(tokens)
			if not tokens:
				continue

			type_model = model["types"].setdefault(issue_type, {"documents": 0, "tokens": {}})
			type_model["documents"] += 1
			model["total_documents"] += 1
			for token in tokens:
				type_model["tokens"][token] = type_model["tokens"].get(token, 0) + 1
				model["token_documents"][token] = model["token_documents"].get(token, 0) + 1

	return model


def clear_issue_suggestion_cache(doc=None, method=None):
	frappe.cache().delete_value(ISSUE_SUGGESTION_CACHE_KEY)


def _unique_values(values):
	result = []
	for value in values:
		if value not in result:
			result.append(value)
	return result


def _issue_type_values_to_routing(values, include_active=False):
	routing = {
		"process_involved": values.get("process"),
		"process_owner": values.get("process_owner"),
		"process_co_owner": values.get("process_co_owner"),
	}
	if include_active:
		routing["is_active"] = values.get("is_active")
	return routing


def clear_issue_classification_cache():
	clear_issue_suggestion_cache()
	for doctype in ("AMF Issue Process", "Issue Type", "Issue", "AMF Issue Test"):
		frappe.clear_cache(doctype=doctype)


def _upsert_issue_type(name, values):
	if frappe.db.exists("Issue Type", name):
		_update_issue_type(name, values)
		return

	doc = frappe.get_doc(dict(values, doctype="Issue Type", name=name))
	doc.insert(ignore_permissions=True)


def _update_issue_type(name, values):
	doc = frappe.get_doc("Issue Type", name)
	doc.update(values)
	doc.save(ignore_permissions=True)


def _processes_by_name():
	return {
		row.name: row
		for row in frappe.get_all(
			"AMF Issue Process",
			fields=["name", "primary_owner", "secondary_owner"],
		)
	}


def _issue_types_by_name():
	return {
		row.name: row
		for row in frappe.get_all(
			"Issue Type",
			fields=["name", "process", "process_owner", "process_co_owner"],
		)
	}


def _existing_user(user):
	user = cstr(user).strip()
	if user and frappe.db.exists("User", user):
		return user
	return None


def _doc_has_field(doc, fieldname):
	return bool(doc.meta and doc.meta.has_field(fieldname))
