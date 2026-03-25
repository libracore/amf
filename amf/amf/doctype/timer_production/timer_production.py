# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt


from __future__ import unicode_literals
from decimal import Decimal, InvalidOperation
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


class TimerProduction(Document):
	pass


import frappe
from frappe.utils import cstr, flt, get_datetime, now_datetime, time_diff_in_hours


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


# ==================================================
#  send mail alert for timers running more than 4 hours
# ==================================================
def send_timer_alert():
	timers = frappe.get_all("Timer Production",
		filters={
			"status": "IN PROCESS",
		},
		fields=["name", "work_order", "operator"]
	)

	

	for t in timers:
		
		already = frappe.db.exists("ToDo", {
			"reference_type": "Timer Production",
			"reference_name": t.name,
			"status": "Open"
		})
		if already:
			continue

		session = frappe.db.get_value(
            "Work Order Timer Table",
            {
                "parent": t.name,
                "stop_time": ["is", "not set"]
            },
            ["start_time"],
            as_dict=True
        )

		if not session or not session.start_time:
			continue
		hours_running = time_diff_in_hours(now_datetime(), session.start_time)
		if hours_running > 4:
			frappe.sendmail(
				recipients=frappe.db.get_value("User", {"username": t.operator}, "email"),
				subject="Timer de production en cours depuis plus de 4 heures",
				message=f"""
					<p>Bonjour {t.operator},</p>
					<p>La minuterie de production <b>{t.name}</b> pour l'ordre de fabrication <b>{t.work_order}</b> fonctionne depuis plus de 4 heures.</p>

					<p>Veuillez vérifier que tout va bien.</p>

					<a href="https://amf.libracore.ch/production-timer?param={t.work_order}"
						style="font-size:16px; font-weight:bold; color:#1a73e8;">
					Ouvrir le timer dans la webpage
					</a><br><br>

					<a href="https://amf.libracore.ch/desk#Form/Timer%20Production/{t.name}"
						style="font-size:16px; font-weight:bold; color:#1a73e8;">
					Ouvrir le timer dans le système ERP
					</a><br><br>
					
					<p>Cordialement,<br/>Votre système ERP</p>
				"""
			)

			# create ToDo
			frappe.get_doc({
				"doctype": "ToDo",
				"owner": t.operator,
				"date": frappe.utils.nowdate(),
				"description": f"Le timer de production {t.name} pour l'ordre de fabrication {t.work_order} fonctionne depuis plus de 4 heures. Veuillez vérifier que tout va bien.",
				"reference_type": "Timer Production",
				"reference_name": t.name,
			}).insert(ignore_permissions=True)


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