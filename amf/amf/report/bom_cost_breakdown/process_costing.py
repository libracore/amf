"""Observed per-Item machining and assembly costs for a recursive BOM.

The same completed-Work-Order samples, accepted quantities, and IQR rule used
by Average by Reference are retained. Source hours and rates are loaded for
audit; an average is unavailable if those source amounts do not reconcile.
"""
from __future__ import unicode_literals

from collections import defaultdict
from decimal import Decimal

import frappe
from frappe.utils import flt

from amf.amf.doctype.planning.planning import PLANNING_COSTING_HOURLY_RATE
from amf.amf.doctype.timer_production.timer_production import TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE
from amf.amf.report.bom_cost_breakdown.average_costing import (
	build_sample_groups, load_records, trimmed_statistics,
)
from amf.amf.report.bom_cost_breakdown.bom_cost_breakdown import operation_category


PROCESS_CATEGORIES = ("Machining", "Assembly")


def as_decimal(value):
	return Decimal(str(value))


def load_process_costs(item_codes, company, currency):
	"""Return audited, IQR-trimmed observed process averages for selected Items."""
	item_codes = set(item_codes)
	records, _, _ = load_records()
	selected = {key: record for key, record in records.items()
		if record["basis"] == "Actual" and record["reference"] in item_codes
		and record["company"] == company and record["currency"] == currency}
	groups = build_sample_groups(selected)
	details = load_source_details(selected, currency)
	work_orders = defaultdict(int)
	for record in selected.values():
		work_orders[record["reference"]] += 1
	result = {}
	for item_code in item_codes:
		result[item_code] = {}
		for category in PROCESS_CATEGORIES:
			key = (item_code, company, currency, "Actual", category)
			samples = groups.get(key, [])
			if not samples:
				result[item_code][category] = dict(average=None,
					eligible=0, retained=0, total_work_orders=work_orders[item_code],
					samples=[], valid=False)
				continue
			stat = trimmed_statistics(samples)
			excluded = set(sample["source"] for sample in stat["excluded"])
			audited = []
			valid = True
			for sample in samples:
				source_rows = details.get((sample["source"], category), [])
				source_total = sum((as_decimal(row["amount"]) for row in source_rows), Decimal("0"))
				matches = bool(source_rows and abs(source_total - as_decimal(sample["amount"])) <= Decimal("0.000001"))
				valid = valid and matches
				audited.append(dict(source=sample["source"],
					quantity=as_decimal(sample["quantity"]),
					amount=as_decimal(sample["amount"]),
					per_unit=as_decimal(sample["per_unit"]),
					excluded=sample["source"] in excluded,
					source_rows=source_rows, sources_match=matches))
			average = as_decimal(stat["amount"]) / as_decimal(stat["quantity"])
			result[item_code][category] = dict(average=average if valid else None,
				eligible=stat["eligible"], retained=stat["retained"],
				total_work_orders=work_orders[item_code],
				retained_amount=as_decimal(stat["amount"]),
				retained_quantity=as_decimal(stat["quantity"]),
				samples=audited, valid=valid,
				lower=stat["lower"], upper=stat["upper"])
	return result


def load_source_details(records, currency):
	"""Reconstruct the priced Planning, Timer, and WO Operation source lines."""
	work_orders = sorted(record["name"] for record in records.values())
	if not work_orders:
		return {}
	params = tuple(work_orders)
	in_sql = ", ".join(["%s"] * len(work_orders))
	details = defaultdict(list)
	plans = frappe.db.sql("""
		SELECT p.name, p.work_order, p.item_code, p.quantite_validee, p.quantite_scrap,
			p.temps_de_cycle_min, p.temps_de_reglage_hr, p.temps_de_programmation_hr,
			wo.production_item
		FROM `tabPlanning` p JOIN `tabWork Order` wo ON wo.name = p.work_order
		WHERE p.docstatus = 1 AND p.work_order IN ({0})
	""".format(in_sql), params, as_dict=True)
	plans_by_wo = defaultdict(list)
	for plan in plans:
		plans_by_wo[plan.work_order].append(plan)
		processed = flt(plan.quantite_validee) + flt(plan.quantite_scrap)
		cycle = flt(plan.temps_de_cycle_min)
		if currency != "CHF" or plan.item_code != plan.production_item or processed <= 0 or cycle <= 0:
			continue
		hours = processed * cycle / 60.0 + flt(plan.temps_de_reglage_hr) + flt(plan.temps_de_programmation_hr)
		details[(plan.work_order, "Machining")].append(dict(
			source_record=plan.name, source_type="Planning", hours=hours,
			rate=PLANNING_COSTING_HOURLY_RATE,
			amount=hours * PLANNING_COSTING_HOURLY_RATE,
			method="(accepted + scrap) × cycle minutes / 60 + setup hours + programming hours; fixed CHF 75/hour"))
	timers = frappe.db.sql("""
		SELECT name, work_order, status, total_duration
		FROM `tabTimer Production` WHERE work_order IN ({0})
	""".format(in_sql), params, as_dict=True)
	finished_timers = set()
	for timer in timers:
		hours = flt(timer.total_duration) / 3600.0
		if timer.status != "FINISHED" or hours <= 0 or currency != "CHF":
			continue
		finished_timers.add(timer.work_order)
		details[(timer.work_order, "Assembly")].append(dict(
			source_record=timer.name, source_type="Timer Production", hours=hours,
			rate=TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE,
			amount=hours * TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE,
			method="Timer Production.total_duration seconds / 3600 × fixed CHF 65/hour"))
	operations = frappe.db.sql("""
		SELECT name, parent, operation, actual_operation_time, hour_rate
		FROM `tabWork Order Operation` WHERE parent IN ({0})
	""".format(in_sql), params, as_dict=True)
	for op in operations:
		category = operation_category(op.operation)
		if category not in PROCESS_CATEGORIES:
			continue
		if category == "Machining" and plans_by_wo[op.parent]:
			continue
		if category == "Assembly" and op.parent in finished_timers:
			continue
		hours, rate = flt(op.actual_operation_time) / 60.0, flt(op.hour_rate)
		if hours <= 0 or rate <= 0:
			continue
		details[(op.parent, category)].append(dict(
			source_record="{0} / {1}".format(op.parent, op.name),
			source_type="Work Order Operation", hours=hours, rate=rate,
			amount=hours * rate,
			method="Work Order Operation.actual_operation_time minutes / 60 × hour_rate"))
	return details
