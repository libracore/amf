# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, cstr, getdate, now_datetime

from amf.amf.utils.tool_maintenance import get_plan_state


ALLOWED_ROLES = {
	"Stock User",
	"Stock Manager",
	"Manufacturing User",
	"Manufacturing Manager",
	"Quality Manager",
	"System Manager",
}
VALID_STATUSES = {"", "Overdue", "Due Soon", "Planned", "No Plan"}


@frappe.whitelist()
def get_dashboard(search=None, status=None, responsible=None, include_disabled=0):
	_assert_access()
	search = cstr(search).strip().lower()
	status = cstr(status).strip()
	responsible = cstr(responsible).strip()
	include_disabled = cint(include_disabled)
	if status not in VALID_STATUSES:
		status = ""

	filters = {"item_group": "Tool"}
	if not include_disabled:
		filters["disabled"] = 0
	items = frappe.get_list(
		"Item",
		filters=filters,
		fields=[
			"name", "item_code", "item_name", "description", "disabled",
			"tool_serial_number", "tool_equipment_type", "tool_location",
			"tool_responsible", "tool_required_ppe",
			"tool_calibration_procedure", "tool_maintenance_instructions",
		],
		order_by="item_code asc",
		limit_page_length=1000,
	)

	if search:
		items = [
			item for item in items
			if search in " ".join([
				cstr(item.item_code), cstr(item.item_name),
				cstr(item.tool_serial_number), cstr(item.tool_equipment_type),
				cstr(item.tool_location),
			]).lower()
		]
	item_codes = [item.name for item in items]
	if not item_codes:
		return _empty_dashboard(search, status, responsible, include_disabled)

	plans = frappe.get_list(
		"Tool Maintenance Plan",
		filters={"item_code": ["in", item_codes]},
		fields=[
			"name", "item_code", "status", "maintenance_type", "activity",
			"next_due_date", "warning_days", "responsible", "last_completed_on",
		],
		order_by="next_due_date asc",
		limit_page_length=2000,
	)
	logs = frappe.get_list(
		"Tool Maintenance Log",
		filters={"item_code": ["in", item_codes]},
		fields=[
			"name", "item_code", "maintenance_plan", "intervention_type",
			"intervention", "intervention_date", "responsible", "performed_by",
			"record_reference",
		],
		order_by="intervention_date desc, modified desc",
		limit_page_length=2000,
	)

	plans_by_item = _group_by_item(plans)
	logs_by_item = _group_by_item(logs)
	employee_names = _employee_name_map(
		[item.tool_responsible for item in items]
		+ [plan.responsible for plan in plans]
		+ [log.responsible for log in logs]
	)
	rows = []
	for item in items:
		active_plans = [
			plan for plan in plans_by_item.get(item.name, []) if plan.status == "Active"
		]
		state = get_plan_state(active_plans)
		if status and state["status"] != status:
			continue
		if responsible and not _item_matches_responsible(item, active_plans, responsible):
			continue
		next_plan = state["next_plan"]
		item_logs = logs_by_item.get(item.name, [])
		rows.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"disabled": item.disabled,
			"serial_number": item.tool_serial_number,
			"equipment_type": item.tool_equipment_type,
			"location": item.tool_location,
			"responsible": item.tool_responsible,
			"responsible_name": employee_names.get(item.tool_responsible, item.tool_responsible),
			"status": state["status"],
			"active_plan_count": state["active_count"],
			"overdue_count": state["overdue_count"],
			"next_due_date": state["next_due_date"],
			"next_plan": next_plan.name if next_plan else None,
			"next_activity": next_plan.activity if next_plan else None,
			"next_type": next_plan.maintenance_type if next_plan else None,
			"plan_responsible_name": employee_names.get(next_plan.responsible, next_plan.responsible) if next_plan else None,
			"last_intervention_date": item_logs[0].intervention_date if item_logs else None,
			"last_intervention": item_logs[0].intervention if item_logs else None,
		})

	status_rank = {"Overdue": 0, "Due Soon": 1, "Planned": 2, "No Plan": 3}
	rows.sort(key=lambda row: (
		status_rank.get(row["status"], 9),
		getdate(row["next_due_date"]) if row["next_due_date"] else date.max,
		row["item_code"],
	))
	summary = {
		"tools": len(rows),
		"overdue": len([row for row in rows if row["status"] == "Overdue"]),
		"due_soon": len([row for row in rows if row["status"] == "Due Soon"]),
		"planned": len([row for row in rows if row["status"] == "Planned"]),
		"no_plan": len([row for row in rows if row["status"] == "No Plan"]),
	}
	return {
		"items": rows,
		"summary": summary,
		"generated_at": cstr(now_datetime()),
		"filters": {
			"search": search,
			"status": status,
			"responsible": responsible,
			"include_disabled": include_disabled,
		},
	}


@frappe.whitelist()
def get_tool_detail(item_code):
	_assert_access()
	item_code = cstr(item_code).strip()
	item = frappe.get_doc("Item", item_code)
	frappe.has_permission("Item", ptype="read", doc=item, throw=True)
	if item.item_group != "Tool":
		frappe.throw(_("Maintenance details are only available for Tool Items."))

	plans = frappe.get_list(
		"Tool Maintenance Plan",
		filters={"item_code": item_code},
		fields=[
			"name", "status", "maintenance_type", "activity", "procedure",
			"responsible", "next_due_date", "warning_days", "frequency_value",
			"frequency_unit", "last_completed_on", "notes",
		],
		order_by="status asc, next_due_date asc",
		limit_page_length=200,
	)
	logs = frappe.get_list(
		"Tool Maintenance Log",
		filters={"item_code": item_code},
		fields=[
			"name", "maintenance_plan", "intervention_type", "intervention",
			"intervention_date", "responsible", "performed_by", "record_reference",
			"remarks", "attachment", "next_due_date",
		],
		order_by="intervention_date desc, modified desc",
		limit_page_length=200,
	)
	employee_names = _employee_name_map(
		[item.get("tool_responsible")]
		+ [plan.responsible for plan in plans]
		+ [log.responsible for log in logs]
	)
	for plan in plans:
		plan.responsible_name = employee_names.get(plan.responsible, plan.responsible)
	for log in logs:
		log.responsible_name = employee_names.get(log.responsible, log.responsible)

	return {
		"item": {
			"item_code": item.name,
			"item_name": item.item_name,
			"serial_number": item.get("tool_serial_number"),
			"equipment_type": item.get("tool_equipment_type"),
			"ownership": item.get("tool_ownership"),
			"location": item.get("tool_location"),
			"responsible": item.get("tool_responsible"),
			"responsible_name": employee_names.get(item.get("tool_responsible"), item.get("tool_responsible")),
			"required_ppe": item.get("tool_required_ppe"),
			"calibration_procedure": item.get("tool_calibration_procedure"),
			"maintenance_instructions": item.get("tool_maintenance_instructions"),
		},
		"plans": plans,
		"logs": logs,
	}


def _group_by_item(rows):
	result = {}
	for row in rows:
		result.setdefault(row.item_code, []).append(row)
	return result


def _employee_name_map(employee_ids):
	employee_ids = list({employee_id for employee_id in employee_ids if employee_id})
	if not employee_ids:
		return {}
	rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", employee_ids]},
		fields=["name", "employee_name"],
	)
	return {row.name: row.employee_name for row in rows}


def _item_matches_responsible(item, plans, responsible):
	if item.tool_responsible == responsible:
		return True
	return any(plan.responsible == responsible for plan in plans)


def _empty_dashboard(search, status, responsible, include_disabled):
	return {
		"items": [],
		"summary": {"tools": 0, "overdue": 0, "due_soon": 0, "planned": 0, "no_plan": 0},
		"generated_at": cstr(now_datetime()),
		"filters": {
			"search": search,
			"status": status,
			"responsible": responsible,
			"include_disabled": include_disabled,
		},
	}


def _assert_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to use Tool Maintenance."), frappe.PermissionError)
	if frappe.session.user == "Administrator":
		return
	if not ALLOWED_ROLES.intersection(set(frappe.get_roles())):
		frappe.throw(_("You do not have access to Tool Maintenance."), frappe.PermissionError)

