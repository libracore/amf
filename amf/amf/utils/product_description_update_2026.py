#!/usr/bin/env python3
"""Standardize all three descriptions for Item Group ``Product``.

This module is used by a Frappe patch and can also be run manually from a
bench.  It derives customer-facing specifications from the configured body,
valve head and syringe, and derives the production description from the
preferred active/submitted BOM.  It never invents a BOM for products that do
not have one.

Usage from the bench directory::

    ./env/bin/python scripts/update_product_descriptions_2026_08_18.py \
        --site site1.local
    ./env/bin/python scripts/update_product_descriptions_2026_08_18.py \
        --site site1.local --apply
"""

from __future__ import unicode_literals

import argparse
import hashlib
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime


BENCH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
if BENCH_PATH not in sys.path:
	sys.path.insert(0, BENCH_PATH)


VALVE_TYPES = {
	"B": "Bypass",
	"D": "Distribution",
	"DA": "Distribution/angled",
	"DS": "Distribution/switch",
	"DSPLIT": "Distribution/split",
	"O": "On/off",
	"OS": "On/off-switch",
	"S": "Switch",
	"SA": "Switch/angled",
	"SL": "Sample loop",
	"SPLIT": "Split",
	"T": "Triangle",
}

MATERIALS = {
	"A": "PMMA",
	"C": "PCTFE",
	"E": "EPDM",
	"K": "PEEK",
	"P": "PTFE",
	"PFG": "food-grade PTFE",
	"S": "stainless steel",
	"U": "UHMW-PE",
	"V": "Viton",
}

PRODUCT_FAMILIES = {
	"P100-O": {
		"series": "SPM",
		"version": "SPM",
		"kind": "pump",
		"audience": "Industrial",
	},
	"P101-O": {
		"series": "SPM",
		"version": "SPM+",
		"kind": "pump",
		"audience": "Industrial",
	},
	"P110-O": {
		"series": "SPM",
		"version": "SPM HD",
		"kind": "pump",
		"audience": "Industrial",
	},
	"P111-O": {
		"series": "SPM",
		"version": "SPM+ HD",
		"kind": "pump",
		"audience": "Industrial",
	},
	"P100-L": {
		"series": "LSPone",
		"version": "LSPone",
		"kind": "pump",
		"audience": "Laboratory",
	},
	"P101-L": {
		"series": "LSPone",
		"version": "LSPone+",
		"kind": "pump",
		"audience": "Laboratory",
	},
	"P110-L": {
		"series": "LSPone",
		"version": "LSPone HD",
		"kind": "pump",
		"audience": "Laboratory",
	},
	"P111-L": {
		"series": "LSPone",
		"version": "LSPone+ HD",
		"kind": "pump",
		"audience": "Laboratory",
	},
	"P200-O": {
		"series": "RVM",
		"version": "RVM Low Power",
		"kind": "valve",
		"audience": "Industrial",
	},
	"P201-O": {
		"series": "RVM",
		"version": "RVM Fast",
		"kind": "valve",
		"audience": "Industrial",
	},
	"P202-O": {
		"series": "RVM mini",
		"version": "RVM mini",
		"kind": "valve",
		"audience": "Industrial",
	},
	"P211-O": {
		"series": "RVM",
		"version": "RVM NMD",
		"kind": "valve",
		"audience": "Industrial",
	},
	"P221-O": {
		"series": "RVM",
		"version": "RVM NSK",
		"kind": "valve",
		"audience": "Industrial",
	},
}

BODY_PATTERN = re.compile(r"P\d{3}-[OL]", re.IGNORECASE)
STANDARD_HEAD_PATTERN = re.compile(
	r"V-(?P<type>[A-Z]+)-(?P<stages>\d+)-(?P<ports>[\d_]+)-"
	r"(?P<channel>[\d+]+)-(?P<valve_material>[A-Z])-"
	r"(?P<plug_material>PFG|[A-Z])",
	re.IGNORECASE,
)
DSPLIT_HEAD_PATTERN = re.compile(
	r"V-(?P<type>DSPLIT)-(?P<stages>\d+)-(?P<ports>[\d_]+)-"
	r"(?P<channel_a>\d+)-(?P<channel_b>\d+)-"
	r"(?P<valve_material>[A-Z])-(?P<plug_material>PFG|[A-Z])",
	re.IGNORECASE,
)
SYRINGE_PATTERN = re.compile(r"(?:^|/)(S-(?P<volume>\d+)(?:-[A-Z0-9]+)+)", re.IGNORECASE)


def esc(value):
	return html.escape(str(value or "").strip(), quote=True)


def plain(value):
	value = re.sub(r"<[^>]+>", " ", str(value or ""))
	return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fmt_number(value):
	try:
		number = float(value)
	except (TypeError, ValueError):
		return str(value or "")
	if number.is_integer():
		return str(int(number))
	return ("{:.6f}".format(number)).rstrip("0").rstrip(".")


def format_channel_code(code):
	parts = str(code or "").split("+")
	formatted = []
	for part in parts:
		try:
			value = int(part) / 100.0
		except (TypeError, ValueError):
			formatted.append(part)
			continue
		text = ("{:.2f}".format(value)).rstrip("0").rstrip(".")
		if value >= 1 and "." not in text:
			text += ".0"
		formatted.append(text)
	return " / ".join(formatted) + " mm"


def format_syringe_volume(microlitres):
	value = int(microlitres)
	if value >= 1000:
		millilitres = value / 1000.0
		text = ("{:.3f}".format(millilitres)).rstrip("0").rstrip(".")
		return text + " mL"
	return "{} µL".format(value)


def family_key(value):
	match = BODY_PATTERN.search(str(value or ""))
	if match:
		key = match.group(0).upper()
		if key in PRODUCT_FAMILIES:
			return key
	return None


def parse_head(value):
	source = str(value or "").strip()
	match = DSPLIT_HEAD_PATTERN.search(source)
	if match:
		data = match.groupdict()
		data["channel"] = "{}+{}".format(data.pop("channel_a"), data.pop("channel_b"))
	else:
		match = STANDARD_HEAD_PATTERN.search(source)
		if not match:
			return None
		data = match.groupdict()

	data = {key: str(value).upper() for key, value in data.items()}
	base_reference = match.group(0)
	data.update({
		"base_reference": base_reference,
		"reference": source if source.upper().startswith("V-") else base_reference,
		"type_label": VALVE_TYPES.get(data["type"], data["type"]),
		"ports_label": data["ports"].replace("_", " + "),
		"channel_label": format_channel_code(data["channel"]),
		"valve_material_label": MATERIALS.get(data["valve_material"], data["valve_material"]),
		"plug_material_label": MATERIALS.get(data["plug_material"], data["plug_material"]),
	})
	return data


def parse_syringe(value):
	match = SYRINGE_PATTERN.search(str(value or ""))
	if not match:
		return None
	return {
		"reference": match.group(1).upper(),
		"volume_ul": int(match.group("volume")),
		"volume_label": format_syringe_volume(match.group("volume")),
	}


def component_reference(component):
	return (component.get("reference_code") or component.get("item_name") or component.get("item_code") or "").strip()


def preferred_component(components, item_group):
	matches = [row for row in components if row.get("item_group") == item_group]
	return matches[0] if matches else None


def infer_configuration(item, components):
	body_component = preferred_component(components, "Body")
	head_component = preferred_component(components, "Valve Head")
	syringe_component = preferred_component(components, "Syringe")

	search_text = " ".join([
		item.get("item_name") or "",
		item.get("item_code") or "",
		item.get("reference_code") or "",
	])
	body_reference = component_reference(body_component) if body_component else ""
	body_family = family_key(body_reference) or family_key(search_text)

	# Legacy 491xxx Product records contain body item code 591000 in the name.
	if not body_family and re.search(r"(?:^|/)591000(?:/|$)", item.get("item_name") or ""):
		body_family = "P110-O"
		body_reference = "591000 (legacy P110-O / SPM HD)"
	if not body_reference:
		body_reference = body_family or ""

	head_reference = component_reference(head_component) if head_component else search_text
	head = parse_head(head_reference) or parse_head(search_text)
	if head and head_component:
		head["component_code"] = head_component.get("item_code")
	if head and not str(head.get("reference") or "").upper().startswith("V-"):
		head["reference"] = head["base_reference"]

	syringe_reference = component_reference(syringe_component) if syringe_component else ""
	syringe = parse_syringe("/" + syringe_reference) if syringe_reference else None
	if not syringe:
		syringe = parse_syringe(search_text)
	if not syringe and body_family and PRODUCT_FAMILIES[body_family]["kind"] == "pump":
		legacy = re.search(
			r"-(25|50|100|250|500|1000|2500|5000)([PU])$",
			str(item.get("item_code") or "").strip(),
			re.IGNORECASE,
		)
		if legacy:
			syringe = parse_syringe("/S-{}-{}".format(legacy.group(1), legacy.group(2)))
	if syringe and syringe_component:
		syringe["component_code"] = syringe_component.get("item_code")

	return {
		"body_component": body_component,
		"body_family": body_family,
		"body_reference": body_reference,
		"head_component": head_component,
		"head": head,
		"syringe_component": syringe_component,
		"syringe": syringe,
	}


def option_labels(item, configuration):
	text = " ".join([
		item.get("item_name") or "",
		item.get("item_code") or "",
		configuration.get("body_reference") or "",
		(configuration.get("head") or {}).get("reference") or "",
	]).upper()
	options = []
	if "PROTO" in text or re.search(r"4D[0-9A-Z]+-P(?:\s|$)", text):
		options.append("Prototype")
	if "10/32UNF" in text or "10-32 UNF" in text:
		options.append("10-32 UNF port connection")
	if "RS485" in text or "RS-485" in text:
		options.append("RS-485 communication")
	if re.search(r"(?:^|[-/ .])HV(?:$|[-/ .])", text):
		options.append("High-volume valve-head configuration")
	if re.search(r"(?:^|[-/ .])BR(?:$|[-/ .])", text):
		options.append("Bio-Rad customer configuration")
	for token, label in (
		("OKO", "OKO customer configuration"),
		("BIO", "BIO customer configuration"),
		("MLDP", "MLDP configuration"),
		(" XS", "XS configuration"),
		("/RP", "RP configuration"),
		("S103623", "S103623 customer-specific valve head"),
		("/NM/TH/", "NM / TH configuration"),
	):
		if token in text:
			options.append(label)
	return list(dict.fromkeys(options))


def div(label, value):
	return "<div><strong>{}:</strong> {}</div>".format(esc(label), esc(value))


def standard_client_description(item, configuration):
	family = PRODUCT_FAMILIES[configuration["body_family"]]
	head = configuration.get("head")
	syringe = configuration.get("syringe")
	is_template = bool(item.get("has_variants"))
	prototype = "Prototype" in option_labels(item, configuration)

	if family["kind"] == "pump":
		title = "{} – {} Programmable Microfluidic Syringe Pump with Rotary Valve".format(
			family["version"], family["audience"]
		)
		if prototype:
			title = "Prototype – " + title
		if syringe and head:
			summary = (
				"High-precision programmable syringe pump with integrated microfluidic "
				"rotary valve, designed for accurate dosing, routing, and flow control."
			)
		else:
			summary = "Configured liquid-dosing assembly for laboratory and OEM fluidic systems."
	else:
		product_noun = "Miniature Microfluidic Rotary Valve" if configuration["body_family"] == "P202-O" else "Industrial Microfluidic Rotary Valve"
		title = "{} – {}".format(family["version"], product_noun)
		if prototype:
			title = "Prototype – " + title
		if is_template:
			summary = "Configurable actuator-and-valve-head product template for laboratory and OEM fluidic systems."
		elif head:
			summary = (
				"High-performance rotary valve head and actuator assembly designed for "
				"seamless integration into laboratory and OEM microfluidic systems."
			)
		else:
			summary = "Configured rotary-valve actuator assembly for laboratory and OEM fluidic systems."

	parts = [
		"<div><strong>{}</strong></div>".format(esc(title)),
		"<div>{}</div>".format(esc(summary)),
		"<div><br></div>",
	]
	parts.append(div("Product reference", item.get("item_code") or item.get("name")))
	body_value = configuration.get("body_reference") or configuration.get("body_family")
	if body_value:
		parts.append(div("Body / version", "{} — {}".format(body_value, family["version"])))
	if syringe:
		parts.append(div("Syringe", "{} ({})".format(syringe["volume_label"], syringe["reference"])))
	if head:
		parts.extend([
			div("Valve head", head["reference"]),
			div("Valve function", head["type_label"]),
			div("Stages", head["stages"]),
			div("Ports", head["ports_label"]),
			div("Channel size", head["channel_label"]),
			div("Valve material", head["valve_material_label"]),
			div("Plug / rotor material", head["plug_material_label"]),
		])
	options = option_labels(item, configuration)
	if options:
		parts.append(div("Configuration / options", "; ".join(options)))
	return "".join(parts)


def valve_head_client_description(item, configuration):
	head = configuration.get("head")
	parts = [
		"<div><strong>Microfluidic rotary-valve head</strong></div>",
		"<div>Valve-head assembly for controlled liquid routing in laboratory and OEM fluidic systems.</div>",
		"<div><br></div>",
	]
	parts.append(div("Product reference", item.get("item_code") or item.get("name")))
	if head:
		parts.extend([
			div("Valve head", head["reference"]),
			div("Valve function", head["type_label"]),
			div("Stages", head["stages"]),
			div("Ports", head["ports_label"]),
			div("Channel size", head["channel_label"]),
			div("Valve material", head["valve_material_label"]),
			div("Plug / rotor material", head["plug_material_label"]),
		])
	return "".join(parts)


def special_client_description(item, configuration):
	code = item.get("item_code") or item.get("name")
	name = item.get("item_name") or code
	upper = "{} {}".format(code, name).upper()

	if code == "4X1477":
		return (
			"<div><strong>NAGI 16-position PEEK connector and valve assembly</strong></div>"
			"<div>Microfluidic connector assembly with mechanical O-ring retention, "
			"supplied with the 16-position PEEK connector and Vici valve assembled and watertightness tested.</div>"
			"<div><br></div>" + div("Product reference", code)
		)
	if code == "CFR.1102":
		return (
			"<div><strong>Continuous Flow Rate System</strong></div>"
			"<div>Microfluidic flow-control system for continuous liquid handling in laboratory and OEM setups.</div>"
			"<div><br></div>" + div("Product reference", code)
		)
	if code == "UFM V4.0":
		return (
			"<div><strong>Microfluidics Module V4.0 – Integrated liquid-handling module</strong></div>"
			"<div>Module combining a motorized syringe pump, 500 µL syringe, "
			"two-stage six-port rotary valve, mixer, incubator and control electronics for dosing, routing and mixing liquids.</div>"
			"<div><br></div>" + div("Product reference", code)
		)
	if "UFM" in upper:
		without_assembly = "WITHOUT ASSEMBLY" in upper or "_1" in upper
		title = "Microfluidics module without final assembly" if without_assembly else "Microfluidics module"
		return (
			"<div><strong>{}</strong></div>".format(esc(title))
			+ "<div>Liquid-handling module for microfluidic laboratory and OEM applications.</div>"
			+ ("<div>Supplied without final assembly.</div>" if without_assembly else "")
			+ "<div><br></div>" + div("Product reference", code)
		)
	if code == "RVM.4000":
		return (
			"<div><strong>RVM valve-position sensor flange subassembly</strong></div>"
			"<div>Electromechanical flange subassembly comprising the RVM-FS flange, valve-position sensor, connector cable and fastener.</div>"
			"<div><br></div>" + div("Product reference", code)
		)
	if "PRD.9000" in upper or "PRODUCTION DUMMY PART" in upper:
		return "<div><strong>Production dummy part</strong></div><div>Internal non-saleable item used for production testing or placeholder processing.</div><div><br></div>" + div("Product reference", code)
	if "PRD.9001" in upper or "DUMMY S/N" in upper:
		return "<div><strong>Serialized production dummy assembly</strong></div><div>Internal non-saleable assembly used for production testing or serial-number processing.</div><div><br></div>" + div("Product reference", code)
	if "VALVE HEAD" in upper:
		return valve_head_client_description(item, configuration)
	return (
		"<div><strong>{}</strong></div>".format(esc(name))
		+ "<div>Configured microfluidic product for laboratory and OEM liquid-handling applications.</div>"
		+ "<div><br></div>" + div("Product reference", code)
	)


def customs_description(item, configuration):
	code = item.get("item_code") or item.get("name")
	name = item.get("item_name") or code
	upper = "{} {}".format(code, name).upper()
	head = configuration.get("head")
	family_key_value = configuration.get("body_family")
	prototype = "Prototype" in option_labels(item, configuration)

	if code == "4X1477":
		return "Non-medical PEEK microfluidic connector and valve assembly"
	if code == "CFR.1102":
		return "Non-medical laboratory liquid-flow control system"
	if code == "UFM V4.0":
		return "Non-medical microfluidic pump, valve and mixing module"
	if "UFM" in upper:
		return "Non-medical microfluidic liquid-handling module"
	if code == "RVM.4000":
		return "Electromechanical rotary-valve sensor flange subassembly"
	if "PRD.900" in upper or "DUMMY" in upper:
		return "Non-saleable production test item"
	if "VALVE HEAD" in upper:
		materials = ""
		if head:
			materials = "; {}/{}".format(head["valve_material_label"], head["plug_material_label"])
		return "Non-medical microfluidic rotary-valve head{}".format(materials)
	if family_key_value:
		family = PRODUCT_FAMILIES[family_key_value]
		lead = "Prototype non-medical" if prototype else "Non-medical"
		if family["kind"] == "pump":
			volume = "; " + configuration["syringe"]["volume_label"] if configuration.get("syringe") else ""
			return "{} electric microfluidic syringe pump with rotary valve{}".format(lead, volume).strip()
		materials = ""
		if head:
			materials = "; {}/{}".format(head["valve_material_label"], head["plug_material_label"])
		return "{} electric microfluidic rotary valve assembly{}".format(lead, materials).strip()
	return "Non-medical microfluidic product: {}".format(plain(name)[:100])


def component_line(component):
	identity = component.get("item_code") or ""
	if component.get("reference_code") and component.get("reference_code") != identity:
		identity += " / " + component.get("reference_code")
	name = component.get("item_name") or ""
	if name and name not in identity:
		identity += " — " + name
	return "{} × {} {} [{}]".format(
		fmt_number(component.get("qty")),
		identity,
		component.get("uom") or "",
		component.get("item_group") or "Unclassified",
	).strip()


def internal_description(item, configuration, bom, components, operations):
	parts = [
		"<div><strong>Production configuration</strong></div>",
		div("ERP item", "{} — {}".format(item.get("item_code") or item.get("name"), item.get("item_name") or "")),
		div("Item type", item.get("item_type") or "Not set"),
		div("R&D reference", item.get("reference_code") or "Not set"),
		div("Lifecycle", "Disabled / legacy" if item.get("disabled") else "Active"),
	]
	if item.get("customs_tariff_number"):
		parts.append(div("Customs tariff number", item.get("customs_tariff_number")))

	if bom:
		basis = "Default active submitted BOM" if bom.get("is_default") else "Latest active submitted BOM (no default flagged)"
		parts.extend([
			div("Production basis", basis),
			div("BOM", "{}; output quantity {} {}".format(
				bom.get("name"), fmt_number(bom.get("quantity")), bom.get("uom") or item.get("stock_uom") or ""
			)),
			"<div><strong>BOM components:</strong></div>",
			"<ul>{}</ul>".format("".join("<li>{}</li>".format(esc(component_line(row))) for row in components)),
		])
		if operations:
			parts.append("<div><strong>BOM operations:</strong></div>")
			parts.append("<ul>{}</ul>".format("".join(
				"<li>{}</li>".format(esc("{} — {} min{}".format(
					row.get("operation") or "Operation",
					fmt_number(row.get("time_in_mins")),
					" at " + row.get("workstation") if row.get("workstation") else "",
				))) for row in operations
			)))
	else:
		parts.extend([
			div("Production basis", "No active submitted BOM found"),
			"<div><strong>Production warning:</strong> Confirm the approved drawing/order and create or reactivate a submitted BOM before manufacture.</div>",
			"<div><strong>Configuration parsed from the product master:</strong></div>",
		])
		parsed = []
		if configuration.get("body_reference"):
			parsed.append("Body: " + configuration["body_reference"])
		if configuration.get("head"):
			parsed.append("Valve head: " + configuration["head"]["reference"])
		if configuration.get("syringe"):
			parsed.append("Syringe: " + configuration["syringe"]["reference"])
		if parsed:
			parts.append("<ul>{}</ul>".format("".join("<li>{}</li>".format(esc(value)) for value in parsed)))
		else:
			parts.append("<div>No standard body/head/syringe configuration could be derived.</div>")
	return "".join(parts)


def select_boms(frappe, item_names):
	if not item_names:
		return {}
	rows = frappe.db.sql(
		"""
		select name, item, quantity, uom, is_default, modified
		from tabBOM
		where docstatus = 1 and is_active = 1 and item in %(items)s
		order by item, is_default desc, modified desc, name desc
		""",
		{"items": tuple(item_names)},
		as_dict=True,
	)
	selected = {}
	for row in rows:
		selected.setdefault(row.item, row)
	return selected


def load_bom_details(frappe, boms):
	if not boms:
		return {}, {}
	parents = tuple(row.name for row in boms.values())
	component_rows = frappe.db.sql(
		"""
		select bi.parent, bi.idx, bi.item_code, bi.item_name, bi.qty, bi.uom,
		       i.item_group, i.reference_code
		from `tabBOM Item` bi
		left join tabItem i on i.name = bi.item_code
		where bi.parent in %(parents)s
		order by bi.parent, bi.idx
		""",
		{"parents": parents},
		as_dict=True,
	)
	operation_rows = frappe.db.sql(
		"""
		select parent, idx, operation, workstation, time_in_mins
		from `tabBOM Operation`
		where parent in %(parents)s
		order by parent, idx
		""",
		{"parents": parents},
		as_dict=True,
	)
	components = defaultdict(list)
	operations = defaultdict(list)
	for row in component_rows:
		components[row.parent].append(row)
	for row in operation_rows:
		operations[row.parent].append(row)
	return components, operations


def build_updates(frappe):
	fields = [
		"name", "item_code", "item_name", "item_group", "item_type", "reference_code",
		"description", "internal_description", "custom_description", "customs_tariff_number",
		"disabled", "has_variants", "stock_uom", "modified",
	]
	items = frappe.get_all(
		"Item",
		filters={"item_group": "Product"},
		fields=fields,
		order_by="item_code",
		limit_page_length=10000,
	)
	boms = select_boms(frappe, [row.name for row in items])
	components_by_bom, operations_by_bom = load_bom_details(frappe, boms)
	updates = []
	for item in items:
		bom = boms.get(item.name)
		components = components_by_bom.get(bom.name, []) if bom else []
		operations = operations_by_bom.get(bom.name, []) if bom else []
		configuration = infer_configuration(item, components)
		if configuration.get("body_family"):
			client = standard_client_description(item, configuration)
		else:
			client = special_client_description(item, configuration)
		new_values = {
			"description": client,
			"internal_description": internal_description(item, configuration, bom, components, operations),
			"custom_description": customs_description(item, configuration),
		}
		updates.append({
			"name": item.name,
			"item": dict(item),
			"bom": dict(bom) if bom else None,
			"configuration": configuration,
			"new_values": new_values,
		})
	return updates


def validate_updates(updates):
	errors = []
	if not updates:
		errors.append("No Product items were found.")
	seen = set()
	for row in updates:
		name = row["name"]
		if name in seen:
			errors.append("Duplicate Item in generated updates: {}".format(name))
		seen.add(name)
		for fieldname, value in row["new_values"].items():
			if not str(value or "").strip():
				errors.append("{} has an empty {}".format(name, fieldname))
		if len(plain(row["new_values"]["custom_description"])) > 512:
			errors.append("{} customs description exceeds DHL's 512-character line limit".format(name))
		for fieldname in ("description", "custom_description"):
			value = str(row["new_values"][fieldname])
			if re.search(r"\b(?:Unknown|None)\b", value, re.IGNORECASE):
				errors.append("{} contains a placeholder in {}".format(name, fieldname))
		client_description = str(row["new_values"]["description"])
		if "non-medical" in client_description.lower():
			errors.append("{} client description contains non-medical wording".format(name))
		expected_reference = div(
			"Product reference",
			row["item"].get("item_code") or row["item"].get("name"),
		)
		if expected_reference not in client_description:
			errors.append("{} client Product reference is not the Item Code".format(name))
		if "<script" in row["new_values"]["description"].lower():
			errors.append("{} contains unsafe client-description markup".format(name))
	if errors:
		raise RuntimeError("Description validation failed:\n- " + "\n- ".join(errors[:100]))


def report_summary(updates):
	changed = [
		row for row in updates
		if any((row["item"].get(field) or "") != value for field, value in row["new_values"].items())
	]
	families = Counter(
		row["configuration"].get("body_family") or "Special / other"
		for row in updates
	)
	custom_lengths = [len(plain(row["new_values"]["custom_description"])) for row in updates]
	return {
		"product_count": len(updates),
		"changed_count": len(changed),
		"active_count": sum(not row["item"].get("disabled") for row in updates),
		"disabled_count": sum(bool(row["item"].get("disabled")) for row in updates),
		"with_active_submitted_bom": sum(bool(row.get("bom")) for row in updates),
		"without_active_submitted_bom": sum(not row.get("bom") for row in updates),
		"family_counts": dict(sorted(families.items())),
		"maximum_customs_description_length": max(custom_lengths) if custom_lengths else 0,
	}


def serializable_update(row):
	configuration = dict(row["configuration"])
	for key in ("body_component", "head_component", "syringe_component"):
		if configuration.get(key):
			configuration[key] = dict(configuration[key])
	return {
		"name": row["name"],
		"item_code": row["item"].get("item_code"),
		"item_name": row["item"].get("item_name"),
		"disabled": row["item"].get("disabled"),
		"bom": row.get("bom"),
		"configuration": configuration,
		"before": {
			field: row["item"].get(field)
			for field in ("description", "internal_description", "custom_description")
		},
		"after": row["new_values"],
	}


def write_json(path, value):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8") as handle:
		json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
		handle.write("\n")


def file_sha256(path):
	digest = hashlib.sha256()
	with open(path, "rb") as handle:
		for chunk in iter(lambda: handle.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def output_path(output_dir, filename):
	path = os.path.join(output_dir, filename)
	if not os.path.exists(path):
		return path
	stem, extension = os.path.splitext(filename)
	stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	return os.path.join(output_dir, "{}_{}{}".format(stem, stamp, extension))


def self_test():
	assert format_channel_code("050") == "0.5 mm"
	assert format_channel_code("075") == "0.75 mm"
	assert format_channel_code("100") == "1.0 mm"
	assert format_channel_code("040+050") == "0.4 / 0.5 mm"
	assert format_syringe_volume("50") == "50 µL"
	assert format_syringe_volume("2500") == "2.5 mL"
	head = parse_head("V-DS-1-12_4-050-C-P/RS485")
	assert head["type_label"] == "Distribution/switch"
	assert head["ports_label"] == "12 + 4"
	head = parse_head("V-DSPLIT-1-6-120-160-C-P")
	assert head["channel_label"] == "1.2 / 1.6 mm"
	head = parse_head("V-D-1-12-050-C-PFG")
	assert head["plug_material_label"] == "food-grade PTFE"
	assert parse_syringe("P100-O/V-D-1-6-050-C-P/S-50-P")["volume_label"] == "50 µL"


def apply_product_description_updates(frappe_module, update_modified=True):
	self_test()
	updates = build_updates(frappe_module)
	validate_updates(updates)
	changed = []
	for row in updates:
		new_values = row["new_values"]
		if any((row["item"].get(field) or "") != value for field, value in new_values.items()):
			changed.append(row)
			frappe_module.db.set_value(
				"Item",
				row["name"],
				new_values,
				modified_by="Administrator",
				update_modified=update_modified,
			)

	for row in updates:
		persisted = frappe_module.db.get_value(
			"Item",
			row["name"],
			["description", "internal_description", "custom_description"],
			as_dict=True,
		)
		if any((persisted.get(field) or "") != value for field, value in row["new_values"].items()):
			raise RuntimeError("Post-write verification failed for Item {}".format(row["name"]))

	summary = report_summary(updates)
	summary["applied_count"] = len(changed)
	return summary


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--site", default="site1.local", help="Frappe site name")
	parser.add_argument("--apply", action="store_true", help="Persist the generated descriptions")
	parser.add_argument(
		"--output-dir",
		default=os.path.join(BENCH_PATH, "product_description_update_2026-08-18"),
		help="Directory for the preview, backup and summary",
	)
	args = parser.parse_args()
	self_test()

	import frappe

	frappe.init(site=args.site, sites_path=os.path.join(BENCH_PATH, "sites"))
	frappe.connect()
	try:
		frappe.set_user("Administrator")
		updates = build_updates(frappe)
		validate_updates(updates)
		summary = report_summary(updates)
		preview_path = output_path(args.output_dir, "preview.json")
		write_json(preview_path, [serializable_update(row) for row in updates])
		summary["preview_file"] = preview_path
		summary["preview_sha256"] = file_sha256(preview_path)

		if args.apply:
			backup_path = output_path(args.output_dir, "backup_before_apply.json")
			backup = [{
				"name": row["name"],
				"modified": row["item"].get("modified"),
				"description": row["item"].get("description"),
				"internal_description": row["item"].get("internal_description"),
				"custom_description": row["item"].get("custom_description"),
			} for row in updates]
			write_json(backup_path, backup)
			summary["backup_file"] = backup_path
			summary["backup_sha256"] = file_sha256(backup_path)

			apply_summary = apply_product_description_updates(frappe)
			frappe.db.commit()
			summary["applied_count"] = apply_summary["applied_count"]
			summary["applied"] = True
			summary["verified_count"] = len(updates)
		else:
			frappe.db.rollback()
			summary["applied"] = False

		summary_path = output_path(args.output_dir, "summary.json")
		write_json(summary_path, summary)
		print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
		print("Summary file: {}".format(summary_path))
	except Exception:
		frappe.db.rollback()
		raise
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
