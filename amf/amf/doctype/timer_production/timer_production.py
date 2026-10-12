# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt


from __future__ import unicode_literals
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from html import escape
from urllib.parse import quote
# import frappe
from frappe.model.document import Document


TIMER_PRODUCTION_WORK_ORDER_FIELD_MAP = {
	"item_code": "production_item",
	"quantity": "produced_qty",
}
TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE = 65.0
SECONDS_PER_HOUR = 3600.0
TIMER_PRODUCTION_ASSEMBLY_COST_SOURCE_FIELDS = (
	"item_code",
	"quantity",
	"total_duration",
)
TIMER_ALERT_AFTER = timedelta(hours=4)
TERMINAL_WORK_ORDER_STATUSES = ("Completed", "Stopped", "Cancelled")


class TimerProduction(Document):
	pass


import frappe
from frappe.utils import (
	cstr,
	flt,
	get_datetime,
	get_url,
	get_url_to_form,
	now_datetime,
	nowdate,
	validate_email_address,
)


def get_timer_production_work_order_values(work_order):
	"""Fetch the values that Timer Production mirrors from its linked Work Order."""
	if not work_order:
		return {}

	return frappe.db.get_value(
		"Work Order",
		work_order,
		list(TIMER_PRODUCTION_WORK_ORDER_FIELD_MAP.values()),
		as_dict=True,
	) or {}



def normalize_timer_production_work_order_value(target_field, value):
	"""Normalize mirrored values so repeated backfills do not rewrite identical data."""
	if value in (None, ""):
		return ""

	if target_field != "quantity":
		return cstr(value)

	try:
		normalized_value = format(Decimal(cstr(value)).normalize(), "f")
	except (InvalidOperation, ValueError, TypeError):
		return cstr(value)

	if "." in normalized_value:
		normalized_value = normalized_value.rstrip("0").rstrip(".")

	return normalized_value or "0"



def calculate_timer_production_total_cost(total_duration=0, hourly_rate=TIMER_PRODUCTION_ASSEMBLY_COSTING_HOURLY_RATE):
	"""
	Calculate the total assembly cost for a timer using a fixed hourly shop rate.

	Algorithm:
	1. Timer Production stores `total_duration` in seconds because the sessions table
	   records precise start and stop datetimes.
	2. The costing rate is defined per hour (`65 CHF / hour`), so we first convert the
	   duration from seconds to hours by dividing by 3600.
	3. Once the duration is expressed in hours, we multiply it by the hourly rate to get
	   the total assembly cost for this timer.
	4. The result is rounded to 2 decimals because it is a currency value.
	"""
	# Convert the accumulated session duration from seconds into billable hours.
	total_duration_hours = flt(total_duration) / SECONDS_PER_HOUR

	# Apply the fixed assembly hourly rate once the unit matches hours.
	total_cost = total_duration_hours * flt(hourly_rate)

	return flt(total_cost, 2)



def calculate_timer_production_cost_per_part(total_cost=0, quantity=0):
	"""Return the assembly cost allocated to each produced part."""
	produced_qty = flt(quantity)
	if produced_qty <= 0:
		return 0

	return flt(flt(total_cost) / produced_qty, 2)



def calculate_timer_production_time_per_part_minutes(total_duration=0, quantity=0):
	"""
	Calculate the assembly time consumed by one finished part in minutes.

	Algorithm:
	1. `total_duration` is stored in seconds because each session is measured from a
	   precise start and stop datetime.
	2. To obtain the time spent per produced unit, we divide that total duration by the
	   produced quantity.
	3. The result of step 2 is still in seconds per part, so we divide by 60 to convert
	   it into minutes per part for a more readable production KPI.
	4. The final value is rounded to 2 decimals for display in the child table.
	"""
	produced_qty = flt(quantity)
	if produced_qty <= 0:
		return 0

	time_per_part_seconds = flt(total_duration) / produced_qty
	return flt(time_per_part_seconds / 60.0, 2)



def has_timer_production_assembly_cost_inputs(doc):
	"""Only build the computed row once at least one source value exists."""
	return any(doc.get(fieldname) not in (None, "") for fieldname in TIMER_PRODUCTION_ASSEMBLY_COST_SOURCE_FIELDS)



def build_timer_production_assembly_cost_row(doc):
	"""Build the single computed row displayed in the Assembly Costs child table."""
	if not has_timer_production_assembly_cost_inputs(doc):
		return None

	total_cost = calculate_timer_production_total_cost(
		total_duration=doc.get("total_duration"),
	)

	return {
		"item_code": doc.get("item_code"),
		"total_cost": total_cost,
		"time_per_part_minutes": calculate_timer_production_time_per_part_minutes(
			total_duration=doc.get("total_duration"),
			quantity=doc.get("quantity"),
		),
		"cost_per_part": calculate_timer_production_cost_per_part(
			total_cost=total_cost,
			quantity=doc.get("quantity"),
		),
	}



def sync_timer_production_assembly_costs(timer, costing_row=None):
	"""Keep the Assembly Costs child table synchronized with the parent timer fields."""
	if not timer.meta.get_field("assembly_costs"):
		return

	timer.set("assembly_costs", [])

	costing_row = costing_row if costing_row is not None else build_timer_production_assembly_cost_row(timer)
	if costing_row:
		timer.append("assembly_costs", costing_row)


def sync_timer_production_work_order_fields(timer):
	"""
	Mirror selected Work Order fields onto Timer Production if those custom fields exist.

	The `item_code` and `quantity` fields were added later as fetched fields. Existing
	timers do not receive those values retroactively, so we keep them synchronized here
	on every save and reuse the same logic for the one-time backfill.
	"""
	if not timer.work_order:
		return

	timer_meta = getattr(timer, "meta", None) or frappe.get_meta("Timer Production")
	available_field_map = {
		target_field: source_field
		for target_field, source_field in TIMER_PRODUCTION_WORK_ORDER_FIELD_MAP.items()
		if timer_meta.get_field(target_field)
	}
	if not available_field_map:
		return

	work_order_values = get_timer_production_work_order_values(timer.work_order)
	if not work_order_values:
		return

	for target_field, source_field in available_field_map.items():
		value = normalize_timer_production_work_order_value(
			target_field, work_order_values.get(source_field)
		)
		timer.set(target_field, value)


@frappe.whitelist()
def backfill_timer_production_work_order_fields():
	"""Retroactively populate fetched Work Order values on existing Timer Production rows."""
	timer_meta = frappe.get_meta("Timer Production")
	available_field_map = {
		target_field: source_field
		for target_field, source_field in TIMER_PRODUCTION_WORK_ORDER_FIELD_MAP.items()
		if timer_meta.get_field(target_field)
	}
	if not available_field_map:
		return {
			"updated": 0,
			"skipped": 0,
			"missing_work_orders": 0,
			"message": "No Timer Production target fields are available on this site.",
		}

	timers = frappe.get_all(
		"Timer Production",
		filters={"work_order": ["is", "set"]},
		fields=["name", "work_order"] + list(available_field_map.keys()),
		limit_page_length=0,
	)

	updated = 0
	skipped = 0
	missing_work_orders = 0

	for timer in timers:
		work_order_values = get_timer_production_work_order_values(timer.get("work_order"))
		if not work_order_values:
			missing_work_orders += 1
			continue

		values_to_update = {}
		for target_field, source_field in available_field_map.items():
			new_value = normalize_timer_production_work_order_value(
				target_field, work_order_values.get(source_field)
			)
			current_value = normalize_timer_production_work_order_value(
				target_field, timer.get(target_field)
			)

			if current_value != new_value:
				values_to_update[target_field] = new_value

		if values_to_update:
			frappe.db.set_value(
				"Timer Production",
				timer.get("name"),
				values_to_update,
				update_modified=False,
			)
			updated += 1
		else:
			skipped += 1

	frappe.db.commit()
	return {
		"updated": updated,
		"skipped": skipped,
		"missing_work_orders": missing_work_orders,
		"total": len(timers),
	}


def _timer_alert_fallback_recipients():
	"""Read optional supervisor addresses from site config."""
	configured = frappe.conf.get("timer_production_alert_recipients") or []
	if isinstance(configured, str):
		configured = configured.replace(";", ",").replace("\n", ",").split(",")

	recipients = []
	for address in configured:
		address = validate_email_address(cstr(address).strip())
		if address and address not in recipients:
			recipients.append(address)
	return recipients


def _timer_alert_delivery(operator):
	"""Resolve the session's operator trigram to a User and an email destination."""
	user = None
	if operator:
		user = frappe.db.get_value(
			"User", {"username": operator, "enabled": 1}, ["name", "email"], as_dict=True
		)

	operator_email = validate_email_address(user.email) if user else None
	recipients = [operator_email] if operator_email else _timer_alert_fallback_recipients()
	return user, recipients


def _timer_alert_message(timer, session, elapsed):
	work_order = escape(cstr(timer.work_order))
	operator = escape(cstr(session.operator or "inconnu"))
	started = escape(cstr(session.start_time))
	base_url = cstr(frappe.conf.get("timer_production_alert_base_url") or "").rstrip("/")
	if base_url:
		web_url = base_url + "/production-timer?param=" + quote(cstr(timer.work_order), safe="")
		desk_url = base_url + "/desk#Form/Timer%20Production/" + quote(cstr(timer.name), safe="/")
	else:
		web_url = get_url("/production-timer?param=" + quote(cstr(timer.work_order), safe=""))
		desk_url = get_url_to_form("Timer Production", timer.name)
	web_url = escape(web_url, quote=True)
	desk_url = escape(desk_url, quote=True)
	return (
		f"<p>Bonjour,</p><p>Le timer de production pour l'ordre de fabrication "
		f"<b>{work_order}</b> est toujours en cours pour l'opérateur <b>{operator}</b>. "
		f"La session a commencé le {started} et dure depuis {elapsed:.1f} heures.</p>"
		f"<p>Veuillez vérifier que tout va bien et mettre le timer en pause si nécessaire.</p>"
		f'<p><a href="{web_url}">Ouvrir le timer de production</a><br>'
		f'<a href="{desk_url}">Ouvrir le document ERP</a></p>'
	)


def _send_timer_session_alert(session_name, now, cutoff):
	"""Lock and recheck a session before creating its one durable alert."""
	rows = frappe.db.sql(
		"""SELECT name, parent, operator, start_time, stop_time
		FROM `tabWork Order Timer Table` WHERE name = %s FOR UPDATE""",
		(session_name,), as_dict=True,
	)
	if not rows:
		return False

	session = rows[0]
	if session.stop_time or not session.start_time or get_datetime(session.start_time) > cutoff:
		return False
	if frappe.db.exists("Timer Production Alert", session.name):
		return False

	timer = frappe.db.get_value(
		"Timer Production", session.parent, ["name", "work_order", "status"], as_dict=True
	)
	if not timer or timer.status != "IN PROCESS" or not timer.work_order:
		return False
	work_order_status = frappe.db.get_value("Work Order", timer.work_order, "status")
	if not work_order_status or work_order_status in TERMINAL_WORK_ORDER_STATUSES:
		return False

	user, recipients = _timer_alert_delivery(session.operator)
	if not user and not recipients:
		frappe.logger("timer_production_alert").warning(
			"No operator User or fallback recipient for timer session %s", session.name
		)
		return False

	elapsed = (now - get_datetime(session.start_time)).total_seconds() / SECONDS_PER_HOUR
	message = _timer_alert_message(timer, session, elapsed)
	todo = None
	if user:
		todo = frappe.get_doc({
			"doctype": "ToDo",
			"owner": user.name,
			"assigned_by": frappe.session.user or "Administrator",
			"date": nowdate(),
			"status": "Open",
			"priority": "Medium",
			"description": message,
			"reference_type": "Timer Production",
			"reference_name": timer.name,
		}).insert(ignore_permissions=True)

	if recipients:
		frappe.sendmail(
			recipients=recipients,
			subject="Timer de production en cours depuis plus de 4 heures: {0}".format(timer.work_order),
			message=message,
			reference_doctype="Timer Production",
			reference_name=timer.name,
		)

	frappe.get_doc({
		"doctype": "Timer Production Alert",
		"session_id": session.name,
		"timer": timer.name,
		"work_order": timer.work_order,
		"operator": session.operator,
		"status": "Open",
		"alerted_at": now,
		"email_recipients": ", ".join(recipients),
		"todo": todo.name if todo else None,
	}).insert(ignore_permissions=True)
	return True


def send_timer_alert():
	"""Alert once per continuously running operator session after four hours."""
	now = now_datetime()
	cutoff = now - TIMER_ALERT_AFTER
	sessions = frappe.get_all(
		"Work Order Timer Table",
		filters={
			"parenttype": "Timer Production",
			"parentfield": "sessions_list",
			"stop_time": ["is", "not set"],
			"start_time": ["<=", cutoff],
		},
		fields=["name"],
		limit_page_length=0,
	)
	alerted = 0
	for session in sessions:
		alerted += int(_send_timer_session_alert(session.name, now, cutoff))
	return {"checked": len(sessions), "alerted": alerted}


def close_timer_alerts(timer, method=None):
	"""Resolve only alerts whose sessions stopped or whose timer finished."""
	if not timer.name:
		return

	active_sessions = {
		session.name for session in timer.sessions_list if not session.stop_time
	} if timer.status == "IN PROCESS" else set()
	alerts = frappe.get_all(
		"Timer Production Alert",
		filters={"timer": timer.name, "status": "Open"},
		fields=["name", "session_id", "todo"],
		limit_page_length=0,
	)
	for alert in alerts:
		if alert.session_id in active_sessions:
			continue
		if alert.todo and frappe.db.get_value("ToDo", alert.todo, "status") == "Open":
			todo = frappe.get_doc("ToDo", alert.todo)
			todo.status = "Closed"
			todo.save(ignore_permissions=True)
		frappe.db.set_value(
			"Timer Production Alert", alert.name,
			{"status": "Closed", "closed_at": now_datetime()},
			update_modified=False,
		)


def timer_before_save(timer, method = None):
	sync_timer_production_work_order_fields(timer)
	timer.total_duration = 0
	for sess in timer.sessions_list:
		if sess.start_time and sess.stop_time:
			start = get_datetime(sess.start_time)
			stop = get_datetime(sess.stop_time)
			
			delta = (stop - start).total_seconds()
			sess.duration = delta
			timer.total_duration = (timer.total_duration or 0) + delta

	costing_row = build_timer_production_assembly_cost_row(timer)
	sync_timer_production_assembly_costs(timer, costing_row=costing_row)

	if timer.status == "FINISHED":
		    # insérer la durée totale dans la doctype de l'OF
			work_order = timer.work_order
			if not work_order:
				frappe.logger().error(f"Timer {timer.name} finished but no Work Order linked.")
				return

			wo_doc = frappe.get_doc("Work Order", work_order)

			# vérifier que l'OF n'est pas annulée
			if wo_doc.docstatus == 2:
				frappe.logger().info(
					f"Timer {timer.name} finished but Work Order {wo_doc.name} is cancelled – skipped update"
				)
				return


			wo_doc.total_duration = timer.total_duration
			
			# obtenir la durée totale par opérateur ayant travaillé sur cette OF
			operator_durations = {}

			for sess in timer.sessions_list:
				operator = sess.operator or "Inconnu"
				operator_durations[operator] = operator_durations.get(operator, 0) + (sess.duration or 0)
			
			wo_doc.duration_table = []
			for operator, dur in operator_durations.items():
				wo_doc.append("duration_table", {
					"operator": operator,
					"duration": dur
				})

			wo_doc.save(ignore_permissions=True)
