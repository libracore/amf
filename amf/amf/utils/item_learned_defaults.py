# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from collections import Counter

import frappe
from frappe.utils import cstr, escape_html, flt


LEARNED_ITEM_GROUPS = ("Plug", "Valve Seat", "Valve Head", "Product")
BATCH_TRACKED_ITEM_GROUPS = ("Plug", "Valve Seat", "Valve Head")

GROUP_FALLBACKS = {
	"Plug": {
		"weight_per_unit": 0.1,
		"weight_uom": "Kg",
		"customs_tariff_number": "8487.9000",
		"has_batch_no": 1,
	},
	"Valve Seat": {
		"weight_per_unit": 0.01,
		"weight_uom": "Kg",
		"customs_tariff_number": "8487.9000",
		"has_batch_no": 1,
	},
	"Valve Head": {
		"weight_per_unit": 0.1,
		"weight_uom": "Kg",
		"customs_tariff_number": "8487.9000",
		"has_batch_no": 1,
	},
	"Product": {
		"weight_per_unit": 2.18,
		"weight_uom": "Kg",
		"customs_tariff_number": "8413.5000",
		"has_batch_no": 0,
	},
}

VALVE_TYPE_MAP = {
	"D": "Distribution",
	"DS": "Distribution/Switch",
	"B": "Bypass",
	"DA": "Distribution/Angled",
	"O": "On/Off",
	"OS": "On/Off-Switch",
	"SA": "Switch/Angled",
	"SL": "Sample Loop",
	"T": "Triangle",
	"M": "Multiplexing",
	"C": "Check",
	"S": "Switch",
}

MATERIAL_MAP = {
	"C": "PCTFE",
	"P": "PTFE",
	"U": "UHMW-PE",
	"V": "Viton",
	"E": "EPDM",
	"S": "Stainless Steel",
	"K": "PEEK",
	"A": "PMMA",
}


@frappe.whitelist()
def get_new_item_learned_defaults(
	item_code,
	item_name,
	item_group,
	item_type=None,
	reference_code=None,
):
	"""Return learned creation defaults without changing any existing Item."""
	item_group = cstr(item_group).strip()
	if item_group not in LEARNED_ITEM_GROUPS:
		return {}

	item_code = cstr(item_code).strip()
	item_type = cstr(item_type).strip()
	peers, group_peers = _get_peer_rows(item_group, item_type, item_code)
	fallbacks = GROUP_FALLBACKS[item_group]

	weight_per_unit = _mode(
		[row.weight_per_unit for row in peers if flt(row.weight_per_unit) > 0]
	)
	if weight_per_unit in (None, ""):
		weight_per_unit = _mode(
			[row.weight_per_unit for row in group_peers if flt(row.weight_per_unit) > 0]
		)

	weight_uom = _mode([row.weight_uom for row in peers if row.weight_uom])
	if not weight_uom:
		weight_uom = _mode([row.weight_uom for row in group_peers if row.weight_uom])

	customs_tariff_number = _mode([
		row.customs_tariff_number
		for row in peers
		if row.customs_tariff_number
	])
	if not customs_tariff_number:
		customs_tariff_number = _mode([
			row.customs_tariff_number
			for row in group_peers
			if row.customs_tariff_number
		])

	return {
		"description": build_item_description(
			item_code=item_code,
			item_name=item_name,
			item_group=item_group,
			item_type=item_type,
			reference_code=reference_code,
		),
		"weight_per_unit": flt(weight_per_unit or fallbacks["weight_per_unit"]),
		"weight_uom": weight_uom or fallbacks["weight_uom"],
		"customs_tariff_number": (
			customs_tariff_number or fallbacks["customs_tariff_number"]
		),
		"has_batch_no": (
			1 if item_group in BATCH_TRACKED_ITEM_GROUPS else fallbacks["has_batch_no"]
		),
	}


def build_item_description(
	item_code,
	item_name,
	item_group,
	item_type=None,
	reference_code=None,
):
	item_code = cstr(item_code).strip()
	item_name = cstr(item_name).strip()
	item_group = cstr(item_group).strip()
	item_type = cstr(item_type).strip()
	reference_code = cstr(reference_code).strip()

	if item_group == "Product":
		return _build_product_description(item_code, item_name, reference_code)
	if item_group == "Valve Head":
		return _build_valve_head_description(item_name)
	if item_group in ("Plug", "Valve Seat"):
		return _build_component_description(
			item_code,
			item_name,
			item_group,
			item_type,
			reference_code,
		)
	return ""


def _get_peer_rows(item_group, item_type, item_code):
	fields = [
		"item_code",
		"item_type",
		"weight_per_unit",
		"weight_uom",
		"customs_tariff_number",
		"has_batch_no",
	]
	group_peers = frappe.get_all(
		"Item",
		filters={"item_group": item_group, "disabled": 0},
		fields=fields,
		order_by="modified desc",
	)
	peers = [row for row in group_peers if not item_type or row.item_type == item_type]

	if item_group == "Product" and len(item_code) >= 2:
		prefix = item_code[:2].upper()
		prefix_peers = [
			row for row in peers
			if cstr(row.item_code).upper().startswith(prefix)
		]
		if len(prefix_peers) >= 2:
			peers = prefix_peers

	return peers or group_peers, group_peers


def _mode(values):
	values = [value for value in values if value not in (None, "")]
	if not values:
		return None
	counts = Counter(values)
	return max(counts, key=lambda value: (counts[value], -values.index(value)))


def _build_component_description(
	item_code,
	item_name,
	item_group,
	item_type,
	reference_code,
):
	parts = item_name.split("-")
	if len(parts) < 6:
		return _build_generic_description(
			item_code, item_name, item_group, reference_code
		)

	lines = [_description_line("Item Code", item_code)]

	lines.extend([
		_description_line("Item Name", item_name),
		_description_line("Item Group", item_group),
		_description_line("R&D Code", reference_code),
		_description_line("Valve Type", VALVE_TYPE_MAP.get(parts[1], parts[1])),
		_description_line("Number of Stages", parts[2]),
		_description_line("Number of Ports", parts[3]),
		_description_line("Channel Size", _format_channel_size(parts[4])),
	])
	material_label = "Plug Material" if item_group == "Plug" else "Valve Material"
	lines.append(_description_line(material_label, MATERIAL_MAP.get(parts[5], parts[5])))
	return "".join(lines)


def _build_valve_head_description(item_name):
	parts = item_name.split("-")
	if len(parts) < 7:
		return _build_generic_description("", item_name, "Valve Head", "")

	return "".join([
		_description_line("Valve Type", VALVE_TYPE_MAP.get(parts[1], parts[1])),
		_description_line("Valve Head", item_name),
		_description_line("Number of Stages", parts[2]),
		_description_line("Number of Ports", parts[3]),
		_description_line("Channel Size", _format_channel_size(parts[4], decimals=1)),
		_description_line("Valve Material", MATERIAL_MAP.get(parts[5], parts[5])),
		_description_line("Plug Material", MATERIAL_MAP.get(parts[6], parts[6])),
	])


def _build_product_description(item_code, item_name, reference_code):
	return _build_generic_description(
		item_code,
		item_name,
		"Product",
		reference_code,
	)


def _build_generic_description(item_code, item_name, item_group, reference_code):
	return "".join([
		_description_line("Item Code", item_code),
		_description_line("Reference", reference_code),
		_description_line("Item Name", item_name),
		_description_line("Item Group", item_group),
	])


def _description_line(label, value):
	return "<b>{0}:</b> {1}<br>".format(
		escape_html(cstr(label)),
		escape_html(cstr(value)),
	)


def _format_channel_size(channel_code, decimals=2):
	try:
		value = float(channel_code) / 100
		return ("{0:.%df} mm" % decimals).format(value)
	except (TypeError, ValueError):
		return "{0} mm".format(channel_code)
