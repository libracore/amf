# -*- coding: utf-8 -*-
# Copyright (c) 2026, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr, flt


WORK_ORDER_DOCTYPE = "Work Order"
ESTIMATED_TIME_FIELD = "temps_de_fabrication_estime"
ESTIMATED_TIME_DAYS_FIELD = "temps_de_fabrication_estime_jours"
MINUTES_PER_HOUR = 60.0
WORKDAY_HOURS = 8.0 + (25.0 / MINUTES_PER_HOUR)

ESTIMATED_TIME_DEPENDS_ON = (
    "eval:doc.production_item && "
    "/^(10|20)[0-9]{4}$/.test(doc.production_item)"
)


def sync_work_order_estimated_time_custom_fields():
    """Create the read-only Work Order field used for estimated production time."""
    create_custom_fields(
        {
            WORK_ORDER_DOCTYPE: [
                {
                    "fieldname": ESTIMATED_TIME_FIELD,
                    "fieldtype": "Float",
                    "label": "Temps de Fabrication Estimé",
                    "description": (
                        "Temps total estimé en heures : préparation moyenne "
                        "+ cycle moyen par pièce x quantité."
                    ),
                    "insert_after": "qty",
                    "read_only": 1,
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "print_hide_if_no_value": 1,
                    "depends_on": ESTIMATED_TIME_DEPENDS_ON,
                },
                {
                    "fieldname": ESTIMATED_TIME_DAYS_FIELD,
                    "fieldtype": "Float",
                    "label": "Temps de Fabrication Estimé [jours]",
                    "description": "Temps de fabrication estimé sur la base de 8 h 25 min par jour.",
                    "insert_after": ESTIMATED_TIME_FIELD,
                    "read_only": 1,
                    "allow_on_submit": 1,
                    "no_copy": 1,
                    "print_hide_if_no_value": 1,
                    "depends_on": ESTIMATED_TIME_DEPENDS_ON,
                },
            ]
        },
        update=True,
    )
    frappe.clear_cache(doctype=WORK_ORDER_DOCTYPE)


def is_estimated_time_item_code(item_code):
    """Return whether an item code is a six-digit 10xxxx or 20xxxx code."""
    item_code = cstr(item_code).strip()
    return len(item_code) == 6 and item_code[:2] in ("10", "20") and item_code.isdigit()


def calculate_estimated_manufacturing_time(
    preparation_hours=0,
    cycle_minutes=0,
    quantity=0,
):
    """Return the estimated total manufacturing time in hours."""
    return flt(
        flt(preparation_hours)
        + (flt(cycle_minutes) * flt(quantity) / MINUTES_PER_HOUR),
        2,
    )


def calculate_estimated_manufacturing_days(estimated_hours=0):
    """Convert estimated hours to workdays of 8 hours and 25 minutes."""
    return flt(flt(estimated_hours) / WORKDAY_HOURS, 2)


def get_planning_time_averages(item_code):
    """Get the average preparation and cycle times for an Item from all Planning rows."""
    return get_planning_time_averages_for_items([item_code]).get(item_code, {})


def get_planning_time_averages_for_items(item_codes):
    """Get Planning time averages grouped by Item for a batch of Work Orders."""
    item_codes = tuple(
        item_code for item_code in (cstr(code).strip() for code in item_codes) if item_code
    )
    if not item_codes:
        return {}

    placeholders = ", ".join(["%s"] * len(item_codes))
    rows = frappe.db.sql(
        """
        SELECT
            item_code,
            AVG(
                COALESCE(temps_de_programmation_hr, 0)
                + COALESCE(temps_de_reglage_hr, 0)
            ) AS preparation_hours,
            AVG(COALESCE(temps_de_cycle_min, 0)) AS cycle_minutes
        FROM `tabPlanning`
        WHERE item_code IN ({})
        GROUP BY item_code
        """.format(placeholders),
        item_codes,
        as_dict=True,
    )
    return {row.item_code: row for row in rows}


def get_estimated_time_values(item_code, quantity, planning_averages=None):
    """Calculate both estimated-time values for one Work Order."""
    estimated_time = 0
    if is_estimated_time_item_code(item_code):
        if planning_averages is None:
            planning_averages = get_planning_time_averages(item_code)

        estimated_time = calculate_estimated_manufacturing_time(
            preparation_hours=planning_averages.get("preparation_hours"),
            cycle_minutes=planning_averages.get("cycle_minutes"),
            quantity=quantity,
        )

    return {
        ESTIMATED_TIME_FIELD: estimated_time,
        ESTIMATED_TIME_DAYS_FIELD: calculate_estimated_manufacturing_days(estimated_time),
    }


def update_work_order_estimated_time(doc, method=None):
    """
    Calculate the estimated time after the Work Order has been saved.

    Frappe V12 calls ``on_update`` after both insert and update, so this handler
    is registered there as the V12 equivalent of an after-save hook.
    """
    meta = frappe.get_meta(WORK_ORDER_DOCTYPE)
    if not meta.get_field(ESTIMATED_TIME_FIELD):
        return

    has_days_field = bool(meta.get_field(ESTIMATED_TIME_DAYS_FIELD))

    item_code = cstr(doc.get("production_item")).strip()
    values = get_estimated_time_values(item_code, doc.get("qty"))
    estimated_time = values[ESTIMATED_TIME_FIELD]

    doc.set(ESTIMATED_TIME_FIELD, estimated_time)
    if has_days_field:
        doc.set(ESTIMATED_TIME_DAYS_FIELD, values[ESTIMATED_TIME_DAYS_FIELD])

    if not doc.name:
        return

    field_values = [ESTIMATED_TIME_FIELD]
    if has_days_field:
        field_values.append(ESTIMATED_TIME_DAYS_FIELD)

    current_values = frappe.db.get_value(
        WORK_ORDER_DOCTYPE,
        doc.name,
        field_values,
        as_dict=True,
    )
    updates = {}
    if current_values.get(ESTIMATED_TIME_FIELD) != estimated_time:
        updates[ESTIMATED_TIME_FIELD] = estimated_time
    if has_days_field:
        estimated_days = doc.get(ESTIMATED_TIME_DAYS_FIELD)
        if current_values.get(ESTIMATED_TIME_DAYS_FIELD) != estimated_days:
            updates[ESTIMATED_TIME_DAYS_FIELD] = estimated_days

    if updates:
        frappe.db.set_value(
            WORK_ORDER_DOCTYPE,
            doc.name,
            updates,
            update_modified=False,
        )


def sync_all_work_order_estimated_times():
    """Backfill estimated times for saved Work Orders that are not completed."""
    meta = frappe.get_meta(WORK_ORDER_DOCTYPE)
    if not meta.get_field(ESTIMATED_TIME_FIELD):
        return {"updated": 0, "skipped": "missing_estimated_time_field"}

    has_days_field = bool(meta.get_field(ESTIMATED_TIME_DAYS_FIELD))
    fields = ["name", "production_item", "qty", ESTIMATED_TIME_FIELD]
    if has_days_field:
        fields.append(ESTIMATED_TIME_DAYS_FIELD)

    work_orders = frappe.get_all(
        WORK_ORDER_DOCTYPE,
        filters={"status": ["!=", "Completed"]},
        fields=fields,
    )
    item_codes = {
        cstr(work_order.get("production_item")).strip()
        for work_order in work_orders
        if is_estimated_time_item_code(work_order.get("production_item"))
    }
    planning_averages = get_planning_time_averages_for_items(item_codes)

    updated = 0
    for work_order in work_orders:
        item_code = cstr(work_order.get("production_item")).strip()
        values = get_estimated_time_values(
            item_code,
            work_order.get("qty"),
            planning_averages=planning_averages.get(item_code, {}),
        )
        updates = {}
        if work_order.get(ESTIMATED_TIME_FIELD) != values[ESTIMATED_TIME_FIELD]:
            updates[ESTIMATED_TIME_FIELD] = values[ESTIMATED_TIME_FIELD]
        if has_days_field and work_order.get(ESTIMATED_TIME_DAYS_FIELD) != values[
            ESTIMATED_TIME_DAYS_FIELD
        ]:
            updates[ESTIMATED_TIME_DAYS_FIELD] = values[ESTIMATED_TIME_DAYS_FIELD]

        if not updates:
            continue

        frappe.db.set_value(
            WORK_ORDER_DOCTYPE,
            work_order.name,
            updates,
            update_modified=False,
        )
        updated += 1

    return {"updated": updated, "processed": len(work_orders)}
