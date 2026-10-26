"""Bulk, source based averages for the BOM Cost Breakdown report.

One BOM or completed Work Order is one observation. IQR is applied to that
observation's unit cost within the finished Item, company, currency, basis and
cost category. Retained amounts are divided by retained finished quantities.
"""
from __future__ import unicode_literals

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt

from amf.amf.doctype.planning.planning import PLANNING_COSTING_HOURLY_RATE
from amf.amf.doctype.timer_production.timer_production import TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE
from amf.amf.report.bom_cost_breakdown.bom_cost_breakdown import (
	ALL_CATEGORIES, CATEGORIES, actual_good_qty, operation_category,
)
from amf.amf.report.bom_cost_breakdown.recursive_bom import load_cost_index


DISPLAY_CATEGORIES = (
	("Materials", "materials"), ("Machining", "machining"),
	("Assembly", "assembly"), ("Quality Control", "quality_control"),
	("Final Testing", "final_testing"), ("Other Operations", "other_operations"),
	("Scrap Credit", "scrap_credit"), ("Shared Costs", "shared_costs"),
	("Reconciliation", "reconciliation"),
	("Stored BOM Total", "stored_bom_total"),
	("Known Subtotal", "known_subtotal"), ("Full Total", "full_total"),
)


def execute_average(filters):
	if filters.get("item_code"):
		item = frappe.get_doc("Item", filters.item_code)
		if not frappe.has_permission("Item", "read", doc=item):
			frappe.throw(_("Not permitted to read Item {0}").format(item.name), frappe.PermissionError)
	view = filters.get("view") or "Average by Reference"
	if view not in ("Average by Reference", "Excluded Records"):
		frappe.throw(_("Unknown view"))

	records, source_counts, current_boms = load_records(
		filters.get("item_code"), only_4xxxxx=bool(cint(filters.get("only_4xxxxx"))))
	groups = build_sample_groups(records)
	statistics = {key: trimmed_statistics(values) for key, values in groups.items()}
	if view == "Excluded Records":
		return outlier_columns(), outlier_rows(statistics)
	return summary_columns(), summary_rows(statistics, source_counts, current_boms)


def _record(name, reference, company, currency, basis, quantity):
	return dict(name=name, reference=reference, company=company, currency=currency,
		basis=basis, quantity=flt(quantity), values=defaultdict(float),
		present=set(), invalid=set())


def _add_value(record, category, amount):
	record["present"].add(category)
	if amount is None:
		record["invalid"].add(category)
	else:
		record["values"][category] += flt(amount)


def _scope(field, item_code, only_4xxxxx=False):
	condition = " AND {0} = %(item_code)s".format(field) if item_code else ""
	if only_4xxxxx:
		condition += " AND {0} REGEXP '^4[0-9]{{5}}$'".format(field)
	return condition


def load_records(item_code=None, only_4xxxxx=False):
	"""Read all submitted BOMs and completed Work Orders in bounded SQL passes."""
	params = {"item_code": item_code}
	companies = {x.name: x.default_currency for x in frappe.get_all(
		"Company", fields=["name", "default_currency"], limit_page_length=0)}
	records = {}
	counts = defaultdict(set)
	current_boms = {}

	boms = frappe.db.sql("""
		SELECT b.name, b.item, b.company, b.quantity, b.base_total_cost,
			b.is_active, b.modified, i.default_bom
		FROM `tabBOM` b LEFT JOIN `tabItem` i ON i.name = b.item
		WHERE b.docstatus = 1
	""" + _scope("b.item", item_code, only_4xxxxx), params, as_dict=True)
	for b in boms:
		key = (b.item, b.company, companies.get(b.company), "Planned")
		record = _record(b.name, b.item, b.company,
			companies.get(b.company), "Planned", b.quantity)
		records[("Planned", b.name)] = record
		counts[key].add(b.name)
		if b.is_active and flt(b.quantity) > 0:
			current_key = (b.item, b.company, companies.get(b.company))
			priority = (1 if b.name == b.default_bom else 0, str(b.modified or ""))
			if current_key not in current_boms or priority > current_boms[current_key]["priority"]:
				current_boms[current_key] = dict(name=b.name,
					per_unit=flt(b.base_total_cost) / flt(b.quantity), priority=priority)
	if boms:
		index = load_cost_index()
		for b in boms:
			record = records[("Planned", b.name)]
			decomposition = index.decompose(b.name)
			record["stored_bom_total"] = index.headers[b.name].base_total_cost
			for category in decomposition["present"]:
				_add_value(record, category, None if category in decomposition["invalid"] else
					float(decomposition["amounts"].get(category, 0)))

	wos = frappe.db.sql("""
		SELECT wo.name, wo.production_item, wo.company, wo.produced_qty, wo.scrap_qty,
			wo.stock_uom
		FROM `tabWork Order` wo
		WHERE wo.docstatus = 1 AND wo.status = 'Completed' AND wo.produced_qty > 0
	""" + _scope("wo.production_item", item_code, only_4xxxxx), params, as_dict=True)
	for wo in wos:
		key = (wo.production_item, wo.company, companies.get(wo.company), "Actual")
		records[("Actual", wo.name)] = _record(wo.name, wo.production_item, wo.company,
			companies.get(wo.company), "Actual", None)
		counts[key].add(wo.name)

	plans = frappe.db.sql("""
		SELECT p.name, p.work_order, p.item_code, p.quantite_validee, p.quantite_scrap,
			p.temps_de_cycle_min, p.temps_de_reglage_hr, p.temps_de_programmation_hr
		FROM `tabPlanning` p JOIN `tabWork Order` wo ON wo.name = p.work_order
		WHERE p.docstatus = 1 AND wo.docstatus = 1 AND wo.status = 'Completed'
			AND wo.produced_qty > 0
	""" + _scope("wo.production_item", item_code, only_4xxxxx), params, as_dict=True)
	plans_by_wo = defaultdict(list)
	for plan in plans:
		plans_by_wo[plan.work_order].append(plan)
	for wo in wos:
		record = records[("Actual", wo.name)]
		good, _, _ = actual_good_qty(wo, plans_by_wo[wo.name])
		record["quantity"] = good
		if not plans_by_wo[wo.name]:
			continue
		for plan in plans_by_wo[wo.name]:
			processed = flt(plan.quantite_validee) + flt(plan.quantite_scrap)
			cycle = flt(plan.temps_de_cycle_min)
			if plan.item_code != wo.production_item or processed <= 0 or cycle <= 0 or record["currency"] != "CHF":
				_add_value(record, "Machining", None)
				continue
			hours = processed * cycle / 60.0 + flt(plan.temps_de_reglage_hr) + flt(plan.temps_de_programmation_hr)
			_add_value(record, "Machining", hours * PLANNING_COSTING_HOURLY_RATE)

	stock = frappe.db.sql("""
		SELECT se.work_order, sed.qty, sed.basic_amount
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		JOIN `tabWork Order` wo ON wo.name = se.work_order
		WHERE se.docstatus = 1 AND wo.docstatus = 1 AND wo.status = 'Completed'
			AND wo.produced_qty > 0
			AND se.purpose IN ('Manufacture', 'Material Consumption for Manufacture')
			AND IFNULL(sed.s_warehouse, '') != '' AND IFNULL(sed.t_warehouse, '') = ''
	""" + _scope("wo.production_item", item_code, only_4xxxxx), params, as_dict=True)
	for line in stock:
		record = records[("Actual", line.work_order)]
		qty, amount = flt(line.qty), flt(line.basic_amount)
		_add_value(record, "Materials", amount if qty > 0 and amount > 0 else None)

	timers = frappe.db.sql("""
		SELECT t.work_order, t.status, t.total_duration
		FROM `tabTimer Production` t JOIN `tabWork Order` wo ON wo.name = t.work_order
		WHERE wo.docstatus = 1 AND wo.status = 'Completed' AND wo.produced_qty > 0
	""" + _scope("wo.production_item", item_code, only_4xxxxx), params, as_dict=True)
	finished_timers = set()
	for timer in timers:
		record = records[("Actual", timer.work_order)]
		hours = flt(timer.total_duration) / 3600.0
		valid = timer.status == "FINISHED" and hours > 0 and record["currency"] == "CHF"
		_add_value(record, "Assembly", hours * TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE if valid else None)
		if valid:
			finished_timers.add(timer.work_order)

	work_operations = frappe.db.sql("""
		SELECT op.parent, op.operation, op.actual_operation_time, op.hour_rate
		FROM `tabWork Order Operation` op JOIN `tabWork Order` wo ON wo.name = op.parent
		WHERE wo.docstatus = 1 AND wo.status = 'Completed' AND wo.produced_qty > 0
	""" + _scope("wo.production_item", item_code, only_4xxxxx), params, as_dict=True)
	for op in work_operations:
		category = operation_category(op.operation)
		if category == "Machining" and plans_by_wo[op.parent]:
			continue
		if category == "Assembly" and op.parent in finished_timers:
			continue
		record = records[("Actual", op.parent)]
		hours, rate = flt(op.actual_operation_time) / 60.0, flt(op.hour_rate)
		_add_value(record, category, hours * rate if hours > 0 and rate > 0 else None)

	charges = frappe.db.sql("""
		SELECT se.work_order, c.description, c.amount
		FROM `tabLanded Cost Taxes and Charges` c
		JOIN `tabStock Entry` se ON se.name = c.parent
		JOIN `tabWork Order` wo ON wo.name = se.work_order
		WHERE c.parenttype = 'Stock Entry' AND se.docstatus = 1
			AND se.purpose = 'Manufacture' AND wo.docstatus = 1
			AND wo.status = 'Completed' AND wo.produced_qty > 0
	""" + _scope("wo.production_item", item_code, only_4xxxxx), params, as_dict=True)
	for charge in charges:
		if charge.description == "Operating Cost as per Work Order / BOM":
			continue
		amount = flt(charge.amount)
		_add_value(records[("Actual", charge.work_order)], "Shared Costs", amount if amount else None)
	return records, counts, current_boms


def build_sample_groups(records):
	groups = defaultdict(list)
	for record in records.values():
		quantity = flt(record["quantity"])
		if quantity <= 0:
			continue
		available = {}
		for category in ALL_CATEGORIES:
			if category in record["present"] and category not in record["invalid"]:
				available[category] = record["values"][category]
		if all(category in available for category in CATEGORIES) and not record["invalid"]:
			available["Full Total"] = sum(available[category] for category in ALL_CATEGORIES if category in available)
		for category, amount in available.items():
			key = (record["reference"], record["company"], record["currency"], record["basis"], category)
			groups[key].append(dict(source=record["name"], quantity=quantity,
				amount=amount, per_unit=amount / quantity))
		if record["basis"] == "Planned" and flt(record.get("stored_bom_total")) > 0:
			amount = flt(record["stored_bom_total"])
			key = (record["reference"], record["company"], record["currency"], "Planned", "Stored BOM Total")
			groups[key].append(dict(source=record["name"], quantity=quantity,
				amount=amount, per_unit=amount / quantity))
	return groups


def percentile(sorted_values, fraction):
	"""Linear interpolated percentile (the common type-7 percentile)."""
	position = (len(sorted_values) - 1) * fraction
	lower = int(position)
	upper = min(lower + 1, len(sorted_values) - 1)
	return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


def trimmed_statistics(samples):
	"""Apply Tukey's 1.5 × IQR fences to unit costs when n >= 4."""
	ordered = sorted(samples, key=lambda sample: sample["per_unit"])
	if len(ordered) < 4:
		lower = upper = None
		kept, excluded = ordered, []
	else:
		values = [sample["per_unit"] for sample in ordered]
		q1, q3 = percentile(values, 0.25), percentile(values, 0.75)
		iqr = q3 - q1
		lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
		kept = [s for s in ordered if lower <= s["per_unit"] <= upper]
		excluded = [s for s in ordered if s["per_unit"] < lower or s["per_unit"] > upper]
	quantity = sum(s["quantity"] for s in kept)
	amount = sum(s["amount"] for s in kept)
	return dict(average=amount / quantity if quantity > 0 else None,
		eligible=len(ordered), retained=len(kept), excluded=excluded,
		kept=kept, lower=lower, upper=upper, quantity=quantity, amount=amount)


def summary_columns():
	columns = [
		{"fieldname": "item_code", "label": _("Finished Item reference"), "fieldtype": "Link", "options": "Item", "width": 170},
		{"fieldname": "basis", "label": _("Basis"), "fieldtype": "Data", "width": 90},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 190},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Data", "width": 75},
		{"fieldname": "source_count", "label": _("Source records"), "fieldtype": "Int", "width": 105},
		{"fieldname": "current_bom", "label": _("Current BOM"), "fieldtype": "Link", "options": "BOM", "width": 170},
		{"fieldname": "current_bom_cost", "label": _("Current BOM cost / unit"), "fieldtype": "Currency", "options": "currency", "precision": 6, "width": 150},
	]
	for category_label, fieldname in DISPLAY_CATEGORIES:
		columns.append({"fieldname": fieldname, "label": _(category_label + " / unit"),
			"fieldtype": "Currency", "options": "currency", "precision": 6, "width": 135})
	columns.extend([
		{"fieldname": "known_samples", "label": _("Retained source records"), "fieldtype": "Int", "width": 145},
		{"fieldname": "full_samples", "label": _("Complete samples"), "fieldtype": "Int", "width": 110},
		{"fieldname": "excluded_observations", "label": _("Excluded observations"), "fieldtype": "Int", "width": 130},
		{"fieldname": "coverage", "label": _("Category records (retained / priced / total)"), "fieldtype": "Data", "width": 420},
		{"fieldname": "method", "label": _("Calculation method"), "fieldtype": "Data", "width": 420},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
	])
	return columns


def summary_rows(statistics, source_counts, current_boms=None):
	rows = []
	current_boms = current_boms or {}
	keys = set(source_counts)
	for key in sorted(keys, key=lambda k: (k[0], k[3], k[1] or "")):
		reference, company, currency, basis = key
		row = dict(item_code=reference, company=company, currency=currency, basis=basis,
			source_count=len(source_counts[key]), excluded_observations=0)
		current = current_boms.get((reference, company, currency)) if basis == "Planned" else None
		row["current_bom"] = current["name"] if current else None
		row["current_bom_cost"] = round(current["per_unit"], 6) if current else None
		coverage = []
		known_sources = set()
		for category, fieldname in DISPLAY_CATEGORIES:
			if category == "Known Subtotal":
				continue
			stat = statistics.get(key + (category,))
			row[fieldname] = round(stat["average"], 6) if stat and stat["average"] is not None else None
			if stat:
				row["excluded_observations"] += len(stat["excluded"])
				if category != "Full Total":
					known_sources.update(sample["source"] for sample in stat["kept"])
			if category in CATEGORIES:
				coverage.append("{0} {1}/{2}/{3}".format(category,
					stat["retained"] if stat else 0,
					stat["eligible"] if stat else 0, len(source_counts[key])))
		known_components = [row[fieldname] for category, fieldname in DISPLAY_CATEGORIES
			if category in ALL_CATEGORIES and row.get(fieldname) is not None]
		row["known_subtotal"] = round(sum(known_components), 6) if known_components else None
		row["known_samples"] = len(known_sources)
		row["full_samples"] = statistics.get(key + ("Full Total",), {}).get("retained", 0)
		row["coverage"] = "; ".join(coverage)
		row["method"] = "Completed Work Orders" if basis == "Actual" else "Submitted BOM revisions"
		row["method"] += "; IQR per category (n ≥ 4), retained amount / retained finished quantity; category averages use priced records only, missing records are unavailable; known subtotal sums shown components; full total uses complete sources"
		row["status"] = "Complete" if row["full_total"] is not None else "Partial" if (
			row["known_subtotal"] is not None or row["stored_bom_total"] is not None) else "Unavailable"
		rows.append(row)
	return rows


def outlier_columns():
	return [
		{"fieldname": "item_code", "label": _("Finished Item reference"), "fieldtype": "Link", "options": "Item", "width": 170},
		{"fieldname": "basis", "label": _("Basis"), "fieldtype": "Data", "width": 85},
		{"fieldname": "category", "label": _("Cost category"), "fieldtype": "Data", "width": 145},
		{"fieldname": "source_type", "label": _("Source type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "source_record", "label": _("Excluded source record"), "fieldtype": "Data", "width": 170},
		{"fieldname": "quantity", "label": _("Finished quantity"), "fieldtype": "Float", "width": 120},
		{"fieldname": "amount", "label": _("Cost amount"), "fieldtype": "Currency", "options": "currency", "width": 115},
		{"fieldname": "per_unit", "label": _("Cost per unit"), "fieldtype": "Currency", "options": "currency", "width": 115},
		{"fieldname": "lower_fence", "label": _("IQR lower fence"), "fieldtype": "Currency", "options": "currency", "width": 115},
		{"fieldname": "upper_fence", "label": _("IQR upper fence"), "fieldtype": "Currency", "options": "currency", "width": 115},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Data", "width": 75},
		{"fieldname": "method", "label": _("Reason"), "fieldtype": "Data", "width": 330},
	]


def outlier_rows(statistics):
	rows = []
	for key, stat in sorted(statistics.items(), key=lambda entry: tuple(str(part or "") for part in entry[0])):
		reference, company, currency, basis, category = key
		for sample in stat["excluded"]:
			rows.append(dict(item_code=reference, company=company, currency=currency,
				basis=basis, category=category, source_type="BOM" if basis == "Planned" else "Work Order",
				source_record=sample["source"], quantity=round(sample["quantity"], 6),
				amount=round(sample["amount"], 6), per_unit=round(sample["per_unit"], 6),
				lower_fence=round(stat["lower"], 6), upper_fence=round(stat["upper"], 6),
				method="Per-unit value outside Q1 − 1.5×IQR to Q3 + 1.5×IQR"))
	return rows
