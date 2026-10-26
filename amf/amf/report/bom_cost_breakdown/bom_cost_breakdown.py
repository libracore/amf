# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt
from __future__ import unicode_literals

import re

import frappe
from frappe import _
from frappe.utils import flt

from amf.amf.doctype.planning.planning import PLANNING_COSTING_HOURLY_RATE
from amf.amf.doctype.timer_production.timer_production import TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE


CATEGORIES = ("Materials", "Machining", "Assembly", "Quality Control", "Final Testing")
ALL_CATEGORIES = CATEGORIES + ("Other Operations", "Scrap Credit", "Shared Costs", "Reconciliation")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.get("view") or ("Detailed Work Order" if filters.get("work_order") or filters.get("bom") else "Average by Reference")
	if view == "Recursive BOM":
		from amf.amf.report.bom_cost_breakdown.recursive_bom import execute_recursive
		return execute_recursive(filters)
	if view in ("Latest Purchase BOM", "Latest Purchase + Process BOM"):
		from amf.amf.report.bom_cost_breakdown.latest_purchase_bom import execute_latest_purchase
		return execute_latest_purchase(filters, include_process=view == "Latest Purchase + Process BOM")
	if view != "Detailed Work Order":
		filters.view = view
		from amf.amf.report.bom_cost_breakdown.average_costing import execute_average
		return execute_average(filters)
	if not filters.get("item_code"):
		frappe.throw(_("Finished Item is required"))

	item = frappe.get_doc("Item", filters.item_code)
	_check_read(item)
	work_order = frappe.get_doc("Work Order", filters.work_order) if filters.get("work_order") else None
	if work_order:
		_check_read(work_order)
		if work_order.production_item != item.name:
			frappe.throw(_("Work Order does not produce the selected Item"))

	bom_name = filters.get("bom") or (work_order.bom_no if work_order else None) or item.default_bom
	if bom_name and not filters.get("bom") and not work_order:
		default = frappe.db.get_value("BOM", bom_name, ["item", "docstatus", "is_active"], as_dict=True)
		if not default or default.item != item.name or default.docstatus != 1 or not default.is_active:
			bom_name = None
	if not bom_name:
		matches = frappe.get_all("BOM", filters={"item": item.name, "docstatus": 1, "is_active": 1},
			fields=["name"], order_by="modified desc", limit_page_length=1)
		bom_name = matches[0].name if matches else None
	bom = frappe.get_doc("BOM", bom_name) if bom_name else None
	if bom:
		_check_read(bom)
		if bom.item != item.name or (bom.docstatus != 1 and not (
			work_order and work_order.bom_no == bom.name and bom.docstatus == 2)):
			frappe.throw(_("The selected BOM must be submitted, or be the historical BOM of the Work Order"))
	if work_order and bom and work_order.bom_no != bom.name:
		frappe.throw(_("The selected BOM is not the Work Order BOM"))

	company = work_order.company if work_order else (bom.company if bom else None)
	if work_order and bom and bom.company != work_order.company:
		frappe.throw(_("BOM and Work Order companies differ"))
	currency = (frappe.db.get_value("Company", company, "default_currency") if company else None) or (
		bom.currency if bom else None)
	rows = []
	if bom:
		planned_rows(rows, bom)
	finalize(rows, "Planned", flt(bom.quantity) if bom else None, currency)
	if work_order:
		actual_rows(rows, work_order, currency)
	else:
		for category in CATEGORIES:
			add(rows, "Actual", category, "No Work Order selected", status="Unavailable",
				method="Select a Work Order to calculate actual costs")
	finalize(rows, "Actual", actual_good_qty(work_order)[0] if work_order else None, currency,
		partial=bool(work_order and work_order.status != "Completed"))
	return columns(), rows


def _check_read(doc):
	if not frappe.has_permission(doc.doctype, "read", doc=doc):
		frappe.throw(_("Not permitted to read {0} {1}").format(doc.doctype, doc.name), frappe.PermissionError)


def columns():
	return [
		{"fieldname": "basis", "label": _("Basis"), "fieldtype": "Data", "width": 85},
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 135},
		{"fieldname": "component", "label": _("Cost component"), "fieldtype": "Data", "width": 240},
		{"fieldname": "quantity", "label": _("Quantity / time"), "fieldtype": "Float", "width": 115},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 75},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "per_unit", "label": _("Per good unit"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Data", "width": 75},
		{"fieldname": "source_type", "label": _("Source type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "source_record", "label": _("Source record"), "fieldtype": "Data", "width": 180},
		{"fieldname": "method", "label": _("Calculation method / assumption"), "fieldtype": "Data", "width": 400},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 105},
	]


def add(rows, basis, category, component, quantity=None, uom=None, rate=None,
		amount=None, source_type=None, source_record=None, method=None, status=None):
	rows.append(dict(basis=basis, category=category, component=component,
		quantity=round(flt(quantity), 6) if quantity is not None else None, uom=uom,
		rate=round(flt(rate), 6) if rate is not None else None,
		amount=round(flt(amount), 6) if amount is not None else None, per_unit=None,
		source_type=source_type, source_record=source_record, method=method,
		status=status or ("Available" if amount is not None else "Unavailable")))


def operation_category(name):
	"""Classify only clear operation names. Unknown work stays visible separately."""
	name = (name or "").lower()
	if re.search(r"test|bench|essai|épreuve|epreuve", name):
		return "Final Testing"
	if re.search(r"quality|inspection|contr[oô]le|check|qc|calibrat", name):
		return "Quality Control"
	if re.search(r"cnc|machin|usinage|tournage|fraisage", name):
		return "Machining"
	if re.search(r"assembl|montage|solder|soudage", name):
		return "Assembly"
	return "Other Operations"


def planned_rows(rows, bom):
	for item in bom.items:
		qty, rate = flt(item.qty), flt(item.base_rate)
		amount = flt(item.base_amount) if qty > 0 and rate > 0 and item.base_amount is not None else None
		add(rows, "Planned", "Materials", item.item_code, qty, item.uom, rate or None,
			amount, "BOM Item", "{0} / {1}".format(bom.name, item.name),
			"Stored base_amount from ERPNext qty × rate calculation; child BOM cost is embedded in this booked amount" if item.bom_no else
			"Stored base_amount from ERPNext qty × rate calculation")
	for op in bom.operations:
		hours, rate = flt(op.time_in_mins) / 60.0, flt(op.base_hour_rate)
		amount = flt(op.base_operating_cost) if hours > 0 and rate > 0 and op.base_operating_cost is not None else None
		add(rows, "Planned", operation_category(op.operation), op.operation, hours, "hour", rate or None,
			amount, "BOM Operation", "{0} / {1}".format(bom.name, op.name),
			"Stored base_operating_cost, calculated by ERPNext from time_in_mins ÷ 60 × hour_rate")
	for scrap in bom.scrap_items:
		qty, rate = flt(scrap.stock_qty), flt(scrap.base_rate)
		amount = -flt(scrap.base_amount) if qty > 0 and rate > 0 and scrap.base_amount is not None else None
		add(rows, "Planned", "Scrap Credit", scrap.item_code, qty, scrap.stock_uom, -rate if rate else None,
			amount, "BOM Scrap Item", "{0} / {1}".format(bom.name, scrap.name),
			"Negative stored base_amount, deducted once")
	direct = sum(flt(i.base_amount) for i in bom.items) + sum(flt(o.base_operating_cost) for o in bom.operations) - sum(
		flt(s.base_amount) for s in bom.scrap_items)
	difference = flt(bom.base_total_cost) - direct
	if abs(difference) > 0.000001:
		add(rows, "Planned", "Reconciliation", "BOM header difference", 1, "adjustment", difference,
			difference, "BOM", bom.name,
			"Stored base_total_cost − stored item/operation/scrap amounts")
	if bom.inspection_required and not any(r["basis"] == "Planned" and r["category"] == "Quality Control" for r in rows):
		add(rows, "Planned", "Quality Control", "Inspection required by BOM", source_type="BOM",
			source_record=bom.name, method="BOM inspection_required has no rate or duration")


def actual_good_qty(work_order, plans=None):
	if not work_order:
		return None, None, "No Work Order"
	produced = flt(work_order.produced_qty)
	if plans is None:
		plans = frappe.get_all("Planning", filters={"work_order": work_order.name, "docstatus": 1},
			fields=["name", "item_code", "quantite_validee", "quantite_scrap"], limit_page_length=0)
	if any(p.get("item_code") and p.item_code != work_order.production_item for p in plans):
		return None, None, "Planning item differs from Work Order production item"
	good = sum(flt(p.quantite_validee) for p in plans)
	scrap = sum(flt(p.quantite_scrap) for p in plans)
	if plans and good > 0 and abs(good + scrap - produced) < 0.000001:
		return good, scrap, "Planning accepted + scrap = Work Order produced_qty"
	custom_scrap = work_order.get("scrap_qty")
	if custom_scrap not in (None, ""):
		try:
			scrap = float(custom_scrap)
		except (TypeError, ValueError):
			return None, None, "Work Order scrap_qty is not numeric"
		if 0 <= scrap < produced:
			return produced - scrap, scrap, "Work Order produced_qty − scrap_qty"
		return None, scrap, "Work Order scrap_qty exceeds or equals produced_qty"
	if plans:
		return None, scrap, "Planning quantities do not reconcile to Work Order produced_qty"
	return (produced if produced > 0 else None), None, "Work Order produced_qty; no separately recorded scrap"


def actual_rows(rows, wo, currency):
	plans = frappe.get_all("Planning", filters={"work_order": wo.name, "docstatus": 1},
		fields=["name", "item_code", "quantite_validee", "quantite_scrap", "temps_de_cycle_min",
			"temps_de_reglage_hr", "temps_de_programmation_hr"], limit_page_length=0)
	good, scrap, yield_method = actual_good_qty(wo, plans)
	add(rows, "Actual", "Yield", "Accepted output", good, wo.stock_uom,
		source_type="Work Order", source_record=wo.name, method=yield_method, status="Information")
	if scrap is not None:
		add(rows, "Actual", "Yield", "Scrap / wastage", scrap, wo.stock_uom,
			source_type="Planning" if plans else "Work Order",
			source_record=", ".join(p.name for p in plans) if plans else wo.name,
			method="Costs are divided by accepted output; scrap receives no finished-unit allocation",
			status="Information")
	stock_rows = frappe.db.sql("""
		SELECT sed.name, sed.parent AS stock_entry, sed.item_code, sed.qty, sed.uom,
			sed.basic_rate, sed.basic_amount
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.work_order = %(work_order)s AND se.docstatus = 1
			AND se.purpose IN ('Manufacture', 'Material Consumption for Manufacture')
			AND IFNULL(sed.s_warehouse, '') != ''
			AND IFNULL(sed.t_warehouse, '') = ''
		ORDER BY se.posting_date, se.posting_time, sed.parent, sed.idx
	""", {"work_order": wo.name}, as_dict=True)
	for stock in stock_rows:
		qty, amount = flt(stock.qty), flt(stock.basic_amount)
		available = qty > 0 and amount > 0
		add(rows, "Actual", "Materials", stock.item_code, qty, stock.uom,
			amount / qty if available else None, amount if available else None,
			"Stock Entry Detail", "{0} / {1}".format(stock.stock_entry, stock.name),
			"Submitted consumption basic_amount; rate = basic_amount ÷ qty. Transfers excluded")
	if not stock_rows:
		fallback = frappe.db.sql("""
			SELECT pct.name, pct.parent, pct.raw_material_prec, pct.raw_material_cost_per_meter,
				pct.raw_material_cost, p.used_qty
			FROM `tabPlanning Costing Table` pct
			JOIN `tabPlanning` p ON p.name = pct.parent
			WHERE p.work_order = %(work_order)s AND p.docstatus = 1
				AND pct.parenttype = 'Planning' AND pct.parentfield = 'costing'
		""", {"work_order": wo.name}, as_dict=True)
		for cost in fallback:
			qty, rate = flt(cost.used_qty), flt(cost.raw_material_cost_per_meter)
			valid = qty > 0 and rate > 0 and flt(cost.raw_material_cost) > 0
			add(rows, "Actual", "Materials", "Planning raw material estimate", qty, "stock UOM",
				rate if valid else None, qty * rate if valid else None,
				"Planning Costing Table", "{0} / {1}{2}".format(cost.parent, cost.name,
					" / " + cost.raw_material_prec if cost.raw_material_prec else ""),
				"Used qty × stored purchase receipt or Item valuation rate; provisional, no posted consumption",
				status="Provisional" if valid else "Unavailable")
		if not fallback:
			add(rows, "Actual", "Materials", "No submitted consumption", source_type="Work Order",
				source_record=wo.name, method="Manufacture or Material Consumption for Manufacture required")
	if plans:
		for plan in plans:
			if plan.item_code != wo.production_item:
				add(rows, "Actual", "Machining", "Planning item mismatch", source_type="Planning",
					source_record=plan.name, method="Planning item differs from Work Order production item")
				continue
			processed = flt(plan.quantite_validee) + flt(plan.quantite_scrap)
			cycle = flt(plan.temps_de_cycle_min)
			for component, hours in (("Cycle time", processed * cycle / 60.0),
				("Setup time", flt(plan.temps_de_reglage_hr)),
				("Programming time", flt(plan.temps_de_programmation_hr))):
				valid = processed > 0 and (cycle > 0 if component == "Cycle time" else True)
				add(rows, "Actual", "Machining", component, hours, "hour",
					PLANNING_COSTING_HOURLY_RATE if currency == "CHF" else None,
					hours * PLANNING_COSTING_HOURLY_RATE if valid and currency == "CHF" else None,
					"Planning", plan.name,
					"Fixed 75 CHF/h cannot be converted to company currency" if currency != "CHF" else
					"(accepted + scrap) × cycle min ÷ 60 × 75 CHF/h" if component == "Cycle time" else
					"Recorded hours × 75 CHF/h; shared over accepted output")
	for op in wo.operations:
		category = operation_category(op.operation)
		if category == "Machining" and plans and currency == "CHF":
			continue  # Planning is the site's machining time source for this Work Order.
		hours, rate = flt(op.actual_operation_time) / 60.0, flt(op.hour_rate)
		add(rows, "Actual", category, op.operation, hours, "hour", rate or None,
			hours * rate if hours > 0 and rate > 0 else None,
			"Work Order Operation", "{0} / {1}".format(wo.name, op.name),
			"actual_operation_time ÷ 60 × hour_rate; planned operating cost excluded")
	timers = frappe.get_all("Timer Production", filters={"work_order": wo.name},
		fields=["name", "status", "total_duration"], limit_page_length=0)
	for timer in timers:
		hours = flt(timer.total_duration) / 3600.0
		valid = timer.status == "FINISHED" and hours > 0 and currency == "CHF"
		add(rows, "Actual", "Assembly", "Assembly timer", hours, "hour",
			TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE if currency == "CHF" else None,
			hours * TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE if valid else None,
			"Timer Production", timer.name,
			"total_duration seconds ÷ 3600 × 65 CHF/h; Work Order accepted output is denominator; timer quantity is a mirrored Data field" if valid else
			"Fixed CHF rate cannot be converted to company currency" if currency != "CHF" else
			"Timer must be FINISHED with positive duration; open sessions are not final")
	if currency == "CHF" and any(timer.status == "FINISHED" and flt(timer.total_duration) > 0 for timer in timers) and any(
			operation_category(op.operation) == "Assembly" for op in wo.operations):
		# These two sources may describe the same work. Keep the timer and remove
		# matching Work Order operation rows, avoiding an unprovable double charge.
		rows[:] = [r for r in rows if not (r["basis"] == "Actual" and r["source_type"] == "Work Order Operation"
			and r["category"] == "Assembly")]
	shared_cost_rows(rows, wo)
	inspections = frappe.db.sql("""
		SELECT qi.name FROM `tabQuality Inspection` qi
		JOIN `tabStock Entry` se ON se.name = qi.reference_name
		WHERE qi.reference_type = 'Stock Entry' AND qi.docstatus = 1
			AND se.work_order = %(work_order)s AND se.docstatus = 1
	""", {"work_order": wo.name}, as_dict=True)
	if inspections and not any(r["basis"] == "Actual" and r["category"] == "Quality Control" for r in rows):
		add(rows, "Actual", "Quality Control", "{0} submitted inspections".format(len(inspections)),
			source_type="Quality Inspection", source_record=", ".join(x.name for x in inspections),
			method="Inspections record results, but have no cost rate or labour duration")


def shared_cost_rows(rows, wo):
	"""Include posted additional charges except ERPNext's generated operating estimate.

	The generated 'Operating Cost as per Work Order / BOM' charge can be a
	planned fallback and overlaps the operation/timer breakdown.
	"""
	charges = frappe.db.sql("""
		SELECT c.name, c.parent, c.description, c.amount
		FROM `tabLanded Cost Taxes and Charges` c
		JOIN `tabStock Entry` se ON se.name = c.parent
		WHERE se.work_order = %(work_order)s AND se.docstatus = 1
			AND se.purpose = 'Manufacture' AND c.parenttype = 'Stock Entry'
	""", {"work_order": wo.name}, as_dict=True)
	for charge in charges:
		if charge.description == "Operating Cost as per Work Order / BOM":
			continue
		amount = flt(charge.amount)
		add(rows, "Actual", "Shared Costs", charge.description or "Additional cost", 1, "charge",
			amount if amount else None, amount if amount else None,
			"Landed Cost Taxes and Charges", "{0} / {1}".format(charge.parent, charge.name),
			"Posted Manufacture additional charge, allocated over accepted output")


def finalize(rows, basis, denominator, currency, partial=False):
	"""Show both known subtotal and full total; never fill missing costs with zero."""
	for row in rows:
		if row["basis"] == basis:
			row["currency"] = currency
			if row["amount"] is not None and denominator and denominator > 0:
				row["per_unit"] = round(row["amount"] / denominator, 6)
	for category in CATEGORIES:
		if not any(r["basis"] == basis and r["category"] == category for r in rows):
			add(rows, basis, category, "No costed source found",
				method="No priced BOM operation or recorded actual labour source for this category")
			rows[-1]["currency"] = currency
	known = 0.0
	priced_count = 0
	complete = bool(denominator and denominator > 0) and not partial
	for category in ALL_CATEGORIES:
		items = [r for r in rows if r["basis"] == basis and r["category"] == category]
		if not items:
			continue
		missing = any(r["amount"] is None or r["status"] != "Available" for r in items)
		amount = sum(r["amount"] for r in items if r["amount"] is not None and r["status"] == "Available")
		priced_count += sum(r["amount"] is not None and r["status"] == "Available" for r in items)
		known += amount
		if category in CATEGORIES or missing:
			complete = complete and not missing
		add(rows, basis, category, "Subtotal", amount=amount if not missing else None,
			method="Sum of {0} detail amounts".format(category),
			status="Available" if not missing else "Unavailable")
		rows[-1]["currency"] = currency
		if not missing and denominator and denominator > 0:
			rows[-1]["per_unit"] = round(amount / denominator, 6)
	add(rows, basis, "Total", "Known cost subtotal", amount=known if priced_count else None,
		method="Sum of priced detail rows only; excludes unavailable and provisional costs",
		status="Unavailable" if not priced_count else "Partial" if not complete else "Available")
	rows[-1]["currency"] = currency
	if priced_count and denominator and denominator > 0:
		rows[-1]["per_unit"] = round(known / denominator, 6)
	add(rows, basis, "Total", "Full cost per finished unit", amount=known if complete else None,
		method="All five cost categories must have rates and a positive finished quantity" +
			("; Work Order is not completed" if partial else ""),
		status="Available" if complete else "Unavailable")
	rows[-1]["currency"] = currency
	if complete:
		rows[-1]["per_unit"] = round(known / denominator, 6)
