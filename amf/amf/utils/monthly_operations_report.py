# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import re
import statistics
from collections import defaultdict
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_months,
    cint,
    flt,
    get_first_day,
    get_last_day,
    getdate,
    md_to_html,
    now_datetime,
    today,
)
from frappe.utils.file_manager import save_file
from frappe.utils.pdf import get_pdf

from amf.amf.dashboard_chart_source.purchased_item_price_ratio.purchased_item_price_ratio import (
    EXCLUDED_COMPANY,
    EXCLUDED_ITEM_CODE_REGEX,
    EXCLUDED_SUPPLIER,
    get_anomaly_decisions,
)
from amf.amf.report.on_time_delivery_kpis.on_time_delivery_kpis import (
    get_data as get_otd_rows,
)


REPORT_DOCTYPE = "Operations KPI Report"
SETTINGS_DOCTYPE = "Operations KPI Report Settings"
MACHINING_ITEM_PATTERN = r"^(10|20)[0-9]{4}$"

OTIF_TARGET = 90.0
STRICT_OTIF_TARGET = 88.0
SCRAP_TARGET = 8.0
ISSUE_AGE_TARGET_DAYS = 30
PRICE_REVIEW_PERCENT = 10.0
PRICE_REVIEW_IMPACT = 500.0


def generate_previous_month_report(force=False, source="Scheduled"):
    settings = get_settings()
    if source == "Scheduled" and not cint(settings.enabled):
        return {"skipped": True, "reason": "Monthly generation is disabled."}

    period_end = add_days(get_first_day(today()), -1)
    period_start = get_first_day(period_end)
    doc = get_or_create_report(
        company=settings.company,
        reporting_month=period_start,
        period_type="Monthly",
        source=source,
        settings=settings,
    )

    if doc.status in ("Completed", "Completed with Warnings") and not force:
        return {"name": doc.name, "status": doc.status, "skipped": True}

    if doc.source != source:
        doc.db_set("source", source, update_modified=False)
    return generate_report(doc.name, force=force)


def generate_previous_semester_report(force=False, source="Manual"):
    settings = get_settings()
    current_date = getdate(today())
    current_semester_start = date(
        current_date.year,
        1 if current_date.month <= 6 else 7,
        1,
    )
    period_end = add_days(current_semester_start, -1)
    period_start = date(
        period_end.year,
        1 if period_end.month <= 6 else 7,
        1,
    )
    doc = get_or_create_report(
        company=settings.company,
        reporting_month=period_start,
        period_type="Semester",
        source=source,
        settings=settings,
    )
    if doc.status in ("Completed", "Completed with Warnings") and not force:
        return {"name": doc.name, "status": doc.status, "skipped": True}
    return generate_report(doc.name, force=force)


def generate_current_semester_report(force=False, source="Manual"):
    settings = get_settings()
    current_date = getdate(today())
    period_start = date(
        current_date.year,
        1 if current_date.month <= 6 else 7,
        1,
    )
    doc = get_or_create_report(
        company=settings.company,
        reporting_month=period_start,
        period_type="Semester",
        source=source,
        settings=settings,
    )
    if doc.status in ("Completed", "Completed with Warnings") and not force:
        return {"name": doc.name, "status": doc.status, "skipped": True}
    return generate_report(doc.name, force=force)


def get_settings():
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    if not settings.company:
        settings.company = frappe.defaults.get_global_default("company")
    return settings


def get_or_create_report(
    company,
    reporting_month,
    period_type="Monthly",
    source="Manual",
    settings=None,
):
    reporting_month = get_first_day(getdate(reporting_month))
    existing_name = frappe.db.get_value(
        REPORT_DOCTYPE,
        {
            "company": company,
            "reporting_month": reporting_month,
            "period_type": period_type,
        },
        "name",
    )
    if existing_name:
        doc = frappe.get_doc(REPORT_DOCTYPE, existing_name)
    else:
        doc = frappe.get_doc(
            {
                "doctype": REPORT_DOCTYPE,
                "company": company,
                "reporting_month": reporting_month,
                "period_type": period_type,
                "source": source,
            }
        )
        if settings:
            doc.send_email = cint(settings.send_email)
            doc.email_recipients = settings.email_recipients
            doc.generate_ai_insights = cint(settings.enable_ai_insights)
        doc.insert(ignore_permissions=True)

    if settings:
        updates = {}
        if source == "Scheduled":
            updates["send_email"] = cint(settings.send_email)
            updates["email_recipients"] = settings.email_recipients
        for fieldname, value in updates.items():
            if doc.get(fieldname) != value:
                doc.db_set(fieldname, value, update_modified=False)
                doc.set(fieldname, value)

    return doc


def generate_report(report_name, force=False):
    warnings = []
    try:
        doc = frappe.get_doc(REPORT_DOCTYPE, report_name)
        if doc.status in ("Completed", "Completed with Warnings") and not force:
            return {"name": doc.name, "status": doc.status, "skipped": True}

        doc.db_set("status", "Generating", update_modified=True)
        settings = get_settings()
        data = collect_report_data(
            company=doc.company,
            period_start=getdate(doc.period_start),
            period_end=getdate(doc.period_end),
            period_type=doc.period_type,
        )

        ai_result = None
        ai_error = ""
        ai_insights_for_report = None
        if cint(doc.generate_ai_insights):
            doc.db_set("ai_status", "Generating", update_modified=False)
            try:
                from amf.amf.utils.operations_ai_insights import generate_ai_insights

                ai_result = generate_ai_insights(data, settings)
                if not cint(settings.get("require_human_approval", 1)):
                    ai_insights_for_report = ai_result["insights"]
            except Exception:
                ai_error = frappe.get_traceback()
                if not cint(settings.get("fallback_to_rule_based_report", 1)):
                    raise
                warnings.append(
                    "AI insight generation failed; the deterministic report was "
                    "completed without AI content."
                )

        english_markdown = (
            render_report(data, "en", ai_insights_for_report)
            if cint(settings.generate_english)
            else ""
        )
        french_markdown = (
            render_report(data, "fr", ai_insights_for_report)
            if cint(settings.generate_french)
            else ""
        )

        doc.reload()
        set_snapshot_fields(doc, data)
        set_ai_fields(
            doc,
            settings,
            ai_enabled=cint(doc.generate_ai_insights),
            ai_result=ai_result,
            ai_error=ai_error,
        )
        doc.english_markdown = english_markdown
        doc.french_markdown = french_markdown
        doc.kpi_data_json = json.dumps(
            data,
            indent=2,
            sort_keys=True,
            default=json_default,
        )
        doc.generated_on = now_datetime()
        doc.generated_by = frappe.session.user
        doc.generation_log = ""
        doc.save(ignore_permissions=True)

        remove_generated_files(doc)
        file_updates = create_report_files(
            doc,
            english_markdown,
            french_markdown,
            settings,
            warnings,
        )
        for fieldname, file_url in file_updates.items():
            doc.db_set(fieldname, file_url, update_modified=False)

        approval_required = (
            cint(doc.generate_ai_insights)
            and cint(settings.get("require_human_approval", 1))
            and doc.ai_status == "Approval Required"
        )
        if cint(doc.send_email) and not approval_required:
            try:
                email_report(doc.name)
            except Exception:
                warnings.append(
                    "Email distribution failed: {0}".format(frappe.get_traceback())
                )

        final_status = "Completed with Warnings" if warnings else "Completed"
        frappe.db.set_value(
            REPORT_DOCTYPE,
            doc.name,
            {
                "status": final_status,
                "generation_log": "\n\n".join(warnings),
            },
            update_modified=True,
        )
        return {"name": doc.name, "status": final_status, "warnings": warnings}
    except Exception:
        error = frappe.get_traceback()
        frappe.db.rollback()
        if frappe.db.exists(REPORT_DOCTYPE, report_name):
            frappe.db.set_value(
                REPORT_DOCTYPE,
                report_name,
                {
                    "status": "Failed",
                    "generation_log": error,
                },
                update_modified=True,
            )
        frappe.log_error(error, "Monthly Operations KPI Report generation failed")
        raise


def collect_report_data(company, period_start, period_end, period_type="Monthly"):
    period_start = getdate(period_start)
    period_end = getdate(period_end)
    if period_type == "Semester":
        previous_start = add_months(period_start, -6)
        previous_end = add_days(period_start, -1)
        period_label = "{0}-{1}".format(
            period_start.year,
            "H1" if period_start.month == 1 else "H2",
        )
    else:
        previous_start = get_first_day(add_months(period_start, -1))
        previous_end = get_last_day(previous_start)
        period_label = period_start.strftime("%Y-%m")
    semester_start = date(period_start.year, 1 if period_start.month <= 6 else 7, 1)

    return {
        "scope": {
            "company": company,
            "currency": frappe.db.get_value("Company", company, "default_currency") or "CHF",
            "period_type": period_type,
            "period_start": period_start,
            "period_end": period_end,
            "period_label": period_label,
            "previous_start": previous_start,
            "previous_end": previous_end,
            "semester_start": semester_start,
            "generated_on": now_datetime(),
        },
        "otif": collect_otif(
            period_start,
            period_end,
            previous_start,
            previous_end,
            semester_start,
        ),
        "machining": collect_machining(period_start, period_end, semester_start),
        "shipping": collect_shipping_issues(period_start, period_end),
        "procurement": collect_procurement_prices(period_start, period_end),
    }


def collect_otif(period_start, period_end, previous_start, previous_end, semester_start):
    current_rows = get_otif_rows(period_start, period_end)
    previous_rows = get_otif_rows(previous_start, previous_end)
    semester_rows = get_otif_rows(semester_start, period_end)

    current = summarize_delivered_rows(current_rows)
    previous = summarize_delivered_rows(previous_rows)
    semester = summarize_delivered_rows(semester_rows)
    strict = get_strict_otif(period_start, period_end)

    customers = defaultdict(lambda: {"lines": 0, "on_time": 0, "late_days": []})
    item_groups = defaultdict(lambda: {"lines": 0, "on_time": 0, "late_days": []})
    for row in current_rows:
        customer = row.customer_name or row.customer or "Unknown"
        item_group = row.item_group or "Unspecified"
        delay = cint(row.delay)
        for bucket in (customers[customer], item_groups[item_group]):
            bucket["lines"] += 1
            bucket["on_time"] += cint(row["0d"])
            if delay > 0:
                bucket["late_days"].append(delay)

    return {
        "current": current,
        "previous": previous,
        "semester_to_date": semester,
        "change_vs_previous_points": round(
            current["rate"] - previous["rate"], 1
        ) if previous["total"] else None,
        "strict": strict,
        "top_customers": finalize_otif_breakdown(customers)[:10],
        "top_item_groups": finalize_otif_breakdown(item_groups)[:10],
        "worst_deliveries": [
            {
                "delivery_note": row.DN,
                "sales_order": row.SO,
                "customer": row.customer_name or row.customer,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "planned_date": row.planned_date,
                "shipped_date": row.shipped_date,
                "delay_days": cint(row.delay),
            }
            for row in sorted(
                current_rows,
                key=lambda value: cint(value.delay),
                reverse=True,
            )[:10]
            if cint(row.delay) > 0
        ],
    }


def get_otif_rows(from_date, to_date):
    return get_otd_rows(
        frappe._dict(
            {
                "from_date": from_date,
                "to_date": to_date,
                "item_group": None,
                "include_rd": 0,
            }
        )
    )


def summarize_delivered_rows(rows):
    delays = [cint(row.delay) for row in rows]
    late_delays = [delay for delay in delays if delay > 0]
    on_time = sum(cint(row["0d"]) for row in rows)
    return {
        "total": len(rows),
        "on_time": on_time,
        "late": len(rows) - on_time,
        "rate": percent(on_time, len(rows)),
        "late_1_2_days": sum(1 for delay in delays if 1 <= delay <= 2),
        "late_3_7_days": sum(1 for delay in delays if 3 <= delay <= 7),
        "late_over_7_days": sum(1 for delay in delays if delay > 7),
        "average_lateness_days": rounded(
            sum(late_delays) / len(late_delays) if late_delays else 0
        ),
        "maximum_lateness_days": max(late_delays) if late_delays else 0,
    }


def finalize_otif_breakdown(values):
    result = []
    for name, row in values.items():
        late = row["lines"] - row["on_time"]
        result.append(
            {
                "name": name,
                "lines": row["lines"],
                "on_time": row["on_time"],
                "late": late,
                "rate": percent(row["on_time"], row["lines"]),
                "average_lateness_days": rounded(
                    sum(row["late_days"]) / len(row["late_days"])
                    if row["late_days"]
                    else 0
                ),
            }
        )
    return sorted(result, key=lambda row: (-row["late"], row["rate"], row["name"]))


def get_strict_otif(period_start, period_end):
    rows = frappe.db.sql(
        """
        SELECT
            soi.name AS sales_order_item,
            so.name AS sales_order,
            so.status AS sales_order_status,
            so.customer_name,
            soi.item_code,
            item.item_name,
            item.item_group,
            soi.delivery_date,
            COALESCE(
                NULLIF(soi.stock_qty, 0),
                soi.qty * IFNULL(soi.conversion_factor, 1)
            ) AS ordered_stock_qty,
            IFNULL(delivered.delivered_by_due, 0) AS delivered_by_due,
            IFNULL(delivered.delivered_by_cutoff, 0) AS delivered_by_cutoff
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON so.name = soi.parent
        INNER JOIN `tabItem` item ON item.name = soi.item_code
        LEFT JOIN (
            SELECT
                dni.so_detail,
                SUM(
                    CASE
                        WHEN dn.posting_date <= due_item.delivery_date
                        THEN COALESCE(
                            NULLIF(dni.stock_qty, 0),
                            dni.qty * IFNULL(dni.conversion_factor, 1)
                        )
                        ELSE 0
                    END
                ) AS delivered_by_due,
                SUM(
                    CASE
                        WHEN dn.posting_date <= %(period_end)s
                        THEN COALESCE(
                            NULLIF(dni.stock_qty, 0),
                            dni.qty * IFNULL(dni.conversion_factor, 1)
                        )
                        ELSE 0
                    END
                ) AS delivered_by_cutoff
            FROM `tabDelivery Note Item` dni
            INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
            INNER JOIN `tabSales Order Item` due_item ON due_item.name = dni.so_detail
            WHERE dn.docstatus = 1
                AND IFNULL(dn.is_return, 0) = 0
                AND dn.posting_date <= %(period_end)s
            GROUP BY dni.so_detail
        ) delivered ON delivered.so_detail = soi.name
        WHERE so.docstatus = 1
            AND soi.delivery_date BETWEEN %(period_start)s AND %(period_end)s
            AND soi.item_code NOT RLIKE '^Di-'
            AND soi.item_code NOT RLIKE '^ENC-'
            AND (
                so.sales_order_type IS NULL
                OR so.sales_order_type NOT IN ('R&D', 'Hybrid')
            )
            AND COALESCE(
                NULLIF(soi.stock_qty, 0),
                soi.qty * IFNULL(soi.conversion_factor, 1)
            ) > 0
        """,
        {
            "period_start": period_start,
            "period_end": period_end,
        },
        as_dict=True,
    )

    tolerance = 0.000001
    delivered_in_full = 0
    full_by_cutoff = 0
    shortfalls = []
    for row in rows:
        ordered = flt(row.ordered_stock_qty)
        delivered_due = flt(row.delivered_by_due)
        delivered_cutoff = flt(row.delivered_by_cutoff)
        delivered_in_full += int(delivered_due + tolerance >= ordered)
        full_by_cutoff += int(delivered_cutoff + tolerance >= ordered)
        if delivered_cutoff + tolerance < ordered:
            shortfalls.append(
                {
                    "sales_order": row.sales_order,
                    "status": row.sales_order_status,
                    "customer": row.customer_name,
                    "item_code": row.item_code,
                    "item_name": row.item_name,
                    "due_date": row.delivery_date,
                    "ordered_qty": rounded(ordered, 3),
                    "delivered_qty": rounded(delivered_cutoff, 3),
                    "remaining_qty": rounded(ordered - delivered_cutoff, 3),
                }
            )

    open_shortfalls = [
        row for row in shortfalls if row["status"] != "Closed"
    ]
    closed_shortfalls = [
        row for row in shortfalls if row["status"] == "Closed"
    ]
    open_shortfalls.sort(key=lambda row: row["remaining_qty"], reverse=True)

    return {
        "eligible_lines": len(rows),
        "delivered_in_full_by_due": delivered_in_full,
        "rate": percent(delivered_in_full, len(rows)),
        "full_by_cutoff": full_by_cutoff,
        "full_by_cutoff_rate": percent(full_by_cutoff, len(rows)),
        "open_shortfall_lines": len(open_shortfalls),
        "open_shortfall_qty": rounded(
            sum(row["remaining_qty"] for row in open_shortfalls), 3
        ),
        "closed_shortfall_lines": len(closed_shortfalls),
        "closed_shortfall_qty": rounded(
            sum(row["remaining_qty"] for row in closed_shortfalls), 3
        ),
        "open_shortfalls": open_shortfalls[:20],
    }


def collect_machining(period_start, period_end, semester_start):
    current = get_machining_period(period_start, period_end)
    semester = get_machining_period(semester_start, period_end)
    return {
        "current": current,
        "semester_to_date": semester,
    }


def get_machining_period(period_start, period_end):
    planning_rows = frappe.db.sql(
        """
        SELECT
            p.name,
            p.item_code,
            COALESCE(NULLIF(p.item_name, ''), item.item_name) AS item_name,
            IFNULL(p.quantite_validee, 0) AS valid_qty,
            IFNULL(p.quantite_scrap, 0) AS scrap_qty
        FROM `tabPlanning` p
        LEFT JOIN `tabItem` item ON item.name = p.item_code
        WHERE p.docstatus = 1
            AND DATE(p.date_de_fin) BETWEEN %(period_start)s AND %(period_end)s
            AND p.item_code REGEXP %(item_pattern)s
        """,
        {
            "period_start": period_start,
            "period_end": period_end,
            "item_pattern": MACHINING_ITEM_PATTERN,
        },
        as_dict=True,
    )
    external_rows = frappe.db.sql(
        """
        SELECT
            pri.item_code,
            SUM(pri.qty) AS qty
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pr.docstatus = 1
            AND IFNULL(pr.is_return, 0) = 0
            AND pr.posting_date BETWEEN %(period_start)s AND %(period_end)s
            AND pri.item_code REGEXP %(item_pattern)s
            AND IFNULL(pri.qty, 0) > 0
        GROUP BY pri.item_code
        """,
        {
            "period_start": period_start,
            "period_end": period_end,
            "item_pattern": MACHINING_ITEM_PATTERN,
        },
        as_dict=True,
    )

    families = {
        "plugs": {"internal": 0.0, "external": 0.0, "scrap": 0.0},
        "seats": {"internal": 0.0, "external": 0.0, "scrap": 0.0},
    }
    items = defaultdict(
        lambda: {
            "item_name": "",
            "valid_qty": 0.0,
            "scrap_qty": 0.0,
            "planning_rows": 0,
        }
    )
    for row in planning_rows:
        family = "plugs" if row.item_code.startswith("10") else "seats"
        families[family]["internal"] += flt(row.valid_qty)
        families[family]["scrap"] += flt(row.scrap_qty)
        items[row.item_code]["item_name"] = row.item_name or ""
        items[row.item_code]["valid_qty"] += flt(row.valid_qty)
        items[row.item_code]["scrap_qty"] += flt(row.scrap_qty)
        items[row.item_code]["planning_rows"] += 1

    for row in external_rows:
        family = "plugs" if row.item_code.startswith("10") else "seats"
        families[family]["external"] += flt(row.qty)

    valid_total = 0.0
    scrap_total = 0.0
    for values in families.values():
        source_total = values["internal"] + values["external"]
        processed_total = values["internal"] + values["scrap"]
        values["internal_ratio"] = percent(values["internal"], source_total)
        values["external_ratio"] = percent(values["external"], source_total)
        values["scrap_rate"] = percent(values["scrap"], processed_total)
        values["internal"] = rounded(values["internal"], 3)
        values["external"] = rounded(values["external"], 3)
        values["scrap"] = rounded(values["scrap"], 3)
        valid_total += values["internal"]
        scrap_total += values["scrap"]

    item_rows = []
    for item_code, values in items.items():
        total = values["valid_qty"] + values["scrap_qty"]
        item_rows.append(
            {
                "item_code": item_code,
                "item_name": values["item_name"],
                "valid_qty": rounded(values["valid_qty"], 3),
                "scrap_qty": rounded(values["scrap_qty"], 3),
                "scrap_rate": percent(values["scrap_qty"], total),
                "planning_rows": values["planning_rows"],
            }
        )

    return {
        "families": families,
        "valid_qty": rounded(valid_total, 3),
        "scrap_qty": rounded(scrap_total, 3),
        "scrap_rate": percent(scrap_total, valid_total + scrap_total),
        "planning_rows": len(planning_rows),
        "top_scrap_items": sorted(
            item_rows,
            key=lambda row: (-row["scrap_qty"], -row["scrap_rate"]),
        )[:10],
    }


def collect_shipping_issues(period_start, period_end):
    meta = frappe.get_meta("Issue")
    available_fields = {field.fieldname for field in meta.fields}
    requested_fields = [
        "subject",
        "status",
        "opening_date",
        "resolution_date",
        "resolution_date_issue",
        "issue_type",
        "customer",
        "customer_issue",
        "delivery_note",
        "process_owner",
        "priority",
        "priority_result",
        "root_cause_description",
        "root_cause_description_issue",
    ]
    selected_fields = [
        fieldname for fieldname in requested_fields if fieldname in available_fields
    ]
    selected_sql = "".join(
        ", issue.`{0}`".format(fieldname) for fieldname in selected_fields
    )
    rows = frappe.db.sql(
        """
        SELECT issue.name, issue.creation {selected_sql}
        FROM `tabIssue` issue
        WHERE issue.process_involved = 'Packaging & Shipping'
            AND COALESCE(issue.opening_date, DATE(issue.creation))
                BETWEEN %(period_start)s AND %(period_end)s
        ORDER BY COALESCE(issue.opening_date, DATE(issue.creation)), issue.name
        """.format(selected_sql=selected_sql),
        {
            "period_start": period_start,
            "period_end": period_end,
        },
        as_dict=True,
    )
    denominator = frappe.db.sql(
        """
        SELECT
            COUNT(DISTINCT dn.name) AS delivery_notes,
            COUNT(dni.name) AS delivery_note_lines
        FROM `tabDelivery Note` dn
        LEFT JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE dn.docstatus = 1
            AND IFNULL(dn.is_return, 0) = 0
            AND dn.posting_date BETWEEN %(period_start)s AND %(period_end)s
        """,
        {
            "period_start": period_start,
            "period_end": period_end,
        },
        as_dict=True,
    )[0]

    details = []
    for row in rows:
        opened = getdate(row.get("opening_date") or row.creation)
        resolution_value = row.get("resolution_date_issue") or row.get("resolution_date")
        resolved = getdate(resolution_value) if resolution_value else None
        age = (resolved - opened).days if resolved else (period_end - opened).days
        customer = row.get("customer_issue") or row.get("customer")
        customer_name = (
            frappe.db.get_value("Customer", customer, "customer_name")
            if customer
            else None
        )
        details.append(
            {
                "issue": row.name,
                "opened": opened,
                "status": row.get("status"),
                "issue_type": row.get("issue_type"),
                "subject": clean_text(row.get("subject")),
                "customer": customer_name or customer,
                "delivery_note": row.get("delivery_note"),
                "process_owner": row.get("process_owner"),
                "priority": row.get("priority_result") or row.get("priority"),
                "resolved": resolved,
                "age_days": age,
                "root_cause": clean_text(
                    row.get("root_cause_description_issue")
                    or row.get("root_cause_description")
                ),
            }
        )

    dashboard_rows = [
        row for row in details if row["status"] in ("Open", "Closed")
    ]
    overdue_open = [
        row
        for row in details
        if row["status"] != "Closed"
        and not row["resolved"]
        and row["age_days"] > ISSUE_AGE_TARGET_DAYS
    ]
    inconsistent = [
        row
        for row in details
        if row["status"] != "Closed" and row["resolved"]
    ]

    return {
        "issue_count": len(details),
        "dashboard_issue_count": len(dashboard_rows),
        "delivery_note_count": cint(denominator.delivery_notes),
        "delivery_note_line_count": cint(denominator.delivery_note_lines),
        "issue_rate_per_100_delivery_notes": percent(
            len(details),
            cint(denominator.delivery_notes),
            digits=2,
        ),
        "overdue_open_count": len(overdue_open),
        "status_resolution_inconsistency_count": len(inconsistent),
        "missing_delivery_note_link_count": sum(
            1 for row in details if not row["delivery_note"]
        ),
        "issues": details,
    }


def collect_procurement_prices(period_start, period_end):
    rows = frappe.db.sql(
        """
        SELECT
            pri.item_code,
            item.item_name,
            item.item_group,
            item.is_stock_item,
            pr.posting_date,
            pr.posting_time,
            pr.name AS purchase_receipt,
            pr.supplier,
            pri.idx,
            IFNULL(
                NULLIF(pri.stock_qty, 0),
                pri.qty * pri.conversion_factor
            ) AS stock_qty,
            (
                COALESCE(
                    NULLIF(pri.base_net_rate, 0),
                    NULLIF(pri.base_rate, 0),
                    NULLIF(pri.net_rate, 0),
                    NULLIF(pri.rate, 0),
                    0
                ) / pri.conversion_factor
            ) AS normalized_rate
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        INNER JOIN `tabItem` item ON item.name = pri.item_code
        WHERE pr.docstatus = 1
            AND IFNULL(pr.is_return, 0) = 0
            AND pr.posting_date <= %(period_end)s
            AND IFNULL(pri.item_code, '') != ''
            AND IFNULL(pri.qty, 0) > 0
            AND IFNULL(pri.conversion_factor, 0) > 0
            AND IFNULL(pr.supplier, '') != %(excluded_supplier)s
            AND IFNULL(pr.company, '') != %(excluded_company)s
            AND pri.item_code NOT RLIKE %(excluded_item_regex)s
            AND COALESCE(
                NULLIF(pri.base_net_rate, 0),
                NULLIF(pri.base_rate, 0),
                NULLIF(pri.net_rate, 0),
                NULLIF(pri.rate, 0),
                0
            ) > 0
        ORDER BY
            pri.item_code,
            pr.posting_date,
            pr.posting_time,
            pr.creation,
            pr.name,
            pri.idx
        """,
        {
            "period_end": period_end,
            "excluded_supplier": EXCLUDED_SUPPLIER,
            "excluded_company": EXCLUDED_COMPANY,
            "excluded_item_regex": EXCLUDED_ITEM_CODE_REGEX,
        },
        as_dict=True,
    )

    previous_by_item = {}
    latest_comparison = {}
    for row in rows:
        previous = previous_by_item.get(row.item_code)
        if (
            period_start <= getdate(row.posting_date) <= period_end
            and previous
            and flt(previous.normalized_rate) > 0
            and flt(row.normalized_rate) > 0
        ):
            latest_comparison[row.item_code] = {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "item_group": row.item_group or "Unspecified",
                "is_stock_item": cint(row.is_stock_item),
                "latest_date": row.posting_date,
                "latest_purchase_receipt": row.purchase_receipt,
                "latest_supplier": row.supplier,
                "latest_rate": flt(row.normalized_rate),
                "latest_stock_qty": flt(row.stock_qty),
                "previous_date": previous.posting_date,
                "previous_purchase_receipt": previous.purchase_receipt,
                "previous_supplier": previous.supplier,
                "previous_rate": flt(previous.normalized_rate),
                "ratio": flt(row.normalized_rate) / flt(previous.normalized_rate),
            }
        previous_by_item[row.item_code] = row

    comparisons = list(latest_comparison.values())
    decisions = get_anomaly_decisions([row["ratio"] for row in comparisons])
    for row, decision in zip(comparisons, decisions):
        row["is_anomaly"] = bool(decision["is_anomaly"])
        row["anomaly_score"] = rounded(decision["anomaly_score"])
        row["ratio_percent"] = rounded(row["ratio"] * 100, 1)
        row["change_percent"] = rounded((row["ratio"] - 1) * 100, 1)
        row["estimated_latest_value"] = (
            row["latest_rate"] * row["latest_stock_qty"]
        )
        row["estimated_price_impact"] = (
            row["latest_rate"] - row["previous_rate"]
        ) * row["latest_stock_qty"]

    included = [row for row in comparisons if not row["is_anomaly"]]
    anomalies = [row for row in comparisons if row["is_anomaly"]]
    ratios = [row["ratio"] for row in included]
    latest_value = sum(row["estimated_latest_value"] for row in included)
    previous_basis = sum(
        row["previous_rate"] * row["latest_stock_qty"] for row in included
    )
    impact = sum(row["estimated_price_impact"] for row in included)

    review_items = [
        row
        for row in included
        if abs(row["change_percent"]) >= PRICE_REVIEW_PERCENT
        or abs(row["estimated_price_impact"]) >= PRICE_REVIEW_IMPACT
    ]
    review_items.sort(
        key=lambda row: abs(row["estimated_price_impact"]),
        reverse=True,
    )

    return {
        "item_count": len(comparisons),
        "included_item_count": len(included),
        "anomaly_count": len(anomalies),
        "ratio_percent": rounded(
            sum(ratios) / len(ratios) * 100 if ratios else 0,
            1,
        ),
        "median_ratio_percent": rounded(
            statistics.median(ratios) * 100 if ratios else 0,
            1,
        ),
        "weighted_ratio_percent": percent(latest_value, previous_basis),
        "estimated_price_impact": rounded(impact, 2),
        "estimated_latest_value": rounded(latest_value, 2),
        "increased_over_2_percent": sum(row["ratio"] > 1.02 for row in included),
        "stable_within_2_percent": sum(
            0.98 <= row["ratio"] <= 1.02 for row in included
        ),
        "decreased_over_2_percent": sum(row["ratio"] < 0.98 for row in included),
        "supplier_switch_count": sum(
            row["latest_supplier"] != row["previous_supplier"]
            for row in included
        ),
        "review_items": [present_price_row(row) for row in review_items[:15]],
        "anomalies": [
            present_price_row(row)
            for row in sorted(
                anomalies,
                key=lambda value: value["anomaly_score"],
                reverse=True,
            )
        ],
    }


def present_price_row(row):
    return {
        "item_code": row["item_code"],
        "item_name": row["item_name"],
        "item_group": row["item_group"],
        "is_stock_item": row["is_stock_item"],
        "latest_date": row["latest_date"],
        "latest_purchase_receipt": row["latest_purchase_receipt"],
        "latest_supplier": row["latest_supplier"],
        "latest_rate": rounded(row["latest_rate"], 6),
        "latest_stock_qty": rounded(row["latest_stock_qty"], 3),
        "previous_date": row["previous_date"],
        "previous_purchase_receipt": row["previous_purchase_receipt"],
        "previous_supplier": row["previous_supplier"],
        "previous_rate": rounded(row["previous_rate"], 6),
        "ratio_percent": row["ratio_percent"],
        "change_percent": row["change_percent"],
        "estimated_price_impact": rounded(row["estimated_price_impact"], 2),
        "anomaly_score": row["anomaly_score"],
    }


def render_report(data, language, ai_insights=None):
    if language == "fr":
        return render_french_report(data, ai_insights)
    return render_english_report(data, ai_insights)


def is_semester_report(data):
    return data.get("scope", {}).get("period_type") == "Semester"


def period_terms(data, language="en"):
    semester = is_semester_report(data)
    if language == "fr":
        return {
            "title": (
                "Rapport semestriel de performance opérationnelle"
                if semester
                else "Rapport mensuel de performance opérationnelle"
            ),
            "result": "Résultat semestriel" if semester else "Résultat mensuel",
            "current": "semestre" if semester else "mois",
            "previous": "semestre précédent" if semester else "mois précédent",
            "end": "fin du semestre" if semester else "fin du mois",
            "snapshot": "semestriel" if semester else "mensuel",
        }
    return {
        "title": (
            "Semester Operations Performance Report"
            if semester
            else "Monthly Operations Performance Report"
        ),
        "result": "Semester result" if semester else "Monthly result",
        "current": "semester" if semester else "month",
        "previous": "previous semester" if semester else "previous month",
        "end": "semester-end" if semester else "month-end",
        "snapshot": "semester" if semester else "monthly",
    }


def render_english_report(data, ai_insights=None):
    scope = data["scope"]
    otif = data["otif"]
    machining = data["machining"]["current"]
    shipping = data["shipping"]
    procurement = data["procurement"]
    strict = otif["strict"]
    currency = scope["currency"]
    terms = period_terms(data, "en")
    lines = [
        "# {0}".format(terms["title"]),
        "",
        "## {0}".format(scope["period_label"]),
        "",
        "**Company:** {0}  ".format(scope["company"]),
        "**Period:** {0} to {1}  ".format(scope["period_start"], scope["period_end"]),
        "**Generated:** {0}".format(scope["generated_on"]),
        "",
        "## Executive Assessment",
        "",
    ]
    lines.extend(get_english_executive_findings(data))
    lines.extend(
        [
            "",
            "## KPI Scorecard",
            "",
            "| KPI | {0} | Assessment |".format(terms["result"]),
            "|---|---:|---|",
            "| On-time delivered-line rate | {0:.1f}% | {1} |".format(
                otif["current"]["rate"],
                kpi_assessment(otif["current"]["rate"], OTIF_TARGET, higher_is_better=True),
            ),
            "| Strict delivered-in-full by due date | {0:.1f}% | {1} |".format(
                strict["rate"],
                kpi_assessment(strict["rate"], STRICT_OTIF_TARGET, higher_is_better=True),
            ),
            "| Open shortfall | {0} lines / {1:g} units | {2} |".format(
                strict["open_shortfall_lines"],
                strict["open_shortfall_qty"],
                "Action required" if strict["open_shortfall_lines"] else "Controlled",
            ),
            "| Plug internal machining | {0:.1f}% | Source mix |".format(
                machining["families"]["plugs"]["internal_ratio"]
            ),
            "| Valve-seat internal machining | {0:.1f}% | Source mix |".format(
                machining["families"]["seats"]["internal_ratio"]
            ),
            "| Machining scrap rate | {0:.1f}% | {1} |".format(
                machining["scrap_rate"],
                kpi_assessment(machining["scrap_rate"], SCRAP_TARGET, higher_is_better=False),
            ),
            "| Packaging and shipping issues | {0} | {1:.2f} per 100 Delivery Notes |".format(
                shipping["issue_count"],
                shipping["issue_rate_per_100_delivery_notes"],
            ),
            "| Purchase price ratio | {0:.1f}% | 100% = unchanged |".format(
                procurement["ratio_percent"]
            ),
            "| Weighted purchase price ratio | {0:.1f}% | Estimated impact: {1} {2:,.2f} |".format(
                procurement["weighted_ratio_percent"],
                currency,
                procurement["estimated_price_impact"],
            ),
            "| Procurement anomalies | {0} / {1} | Review required |".format(
                procurement["anomaly_count"],
                procurement["item_count"],
            ),
            "",
        ]
    )
    lines.extend(render_english_otif(data))
    lines.extend(render_english_machining(data))
    lines.extend(render_english_shipping(data))
    lines.extend(render_english_procurement(data))
    if ai_insights:
        lines.extend(render_english_ai_insights(ai_insights))
    lines.extend(render_english_actions(data, 6 if ai_insights else 5))
    lines.extend(render_english_notes(data, 7 if ai_insights else 6))
    return "\n".join(lines).strip() + "\n"


def get_english_executive_findings(data):
    otif = data["otif"]
    strict = otif["strict"]
    machining = data["machining"]["current"]
    shipping = data["shipping"]
    procurement = data["procurement"]
    findings = []
    terms = period_terms(data, "en")

    change = otif["change_vs_previous_points"]
    if change is None:
        change_text = "No comparable delivered rows were available for the {0}.".format(
            terms["previous"]
        )
    else:
        direction = "improved" if change >= 0 else "declined"
        change_text = "The rate {0} by {1:.1f} points versus the {2}.".format(
            direction,
            abs(change),
            terms["previous"],
        )
    findings.append(
        "1. **Delivery performance:** the delivered-line rate was **{0:.1f}%** and strict OTIF was **{1:.1f}%**. {2}".format(
            otif["current"]["rate"],
            strict["rate"],
            change_text,
        )
    )
    findings.append(
        "2. **Open fulfillment:** {0} due lines representing {1:g} stock units remained incomplete at {2}.".format(
            strict["open_shortfall_lines"],
            strict["open_shortfall_qty"],
            terms["end"],
        )
    )
    findings.append(
        "3. **Machining:** plugs were {0:.1f}% internal and valve seats were {1:.1f}% internal. The combined scrap rate was **{2:.1f}%**.".format(
            machining["families"]["plugs"]["internal_ratio"],
            machining["families"]["seats"]["internal_ratio"],
            machining["scrap_rate"],
        )
    )
    findings.append(
        "4. **Shipping control:** {0} packaging/shipping issues were opened, including {1} unresolved issues older than {2} days.".format(
            shipping["issue_count"],
            shipping["overdue_open_count"],
            ISSUE_AGE_TARGET_DAYS,
        )
    )
    findings.append(
        "5. **Procurement:** the arithmetic price ratio was **{0:.1f}%**, the weighted ratio was **{1:.1f}%**, and the estimated impact on latest quantities was **{2} {3:,.2f}**. {4} statistical anomalies require classification.".format(
            procurement["ratio_percent"],
            procurement["weighted_ratio_percent"],
            data["scope"]["currency"],
            procurement["estimated_price_impact"],
            procurement["anomaly_count"],
        )
    )
    return findings


def render_english_otif(data):
    otif = data["otif"]
    current = otif["current"]
    strict = otif["strict"]
    terms = period_terms(data, "en")
    lines = [
        "## 1. OTIF and Delivery Performance",
        "",
        "The dashboard measure counts submitted, non-return Delivery Note item rows and compares their posting date with the Sales Order Item delivery date. The strict measure additionally requires the full ordered stock quantity to have been delivered by the due date.",
        "",
        "| View | On time / complete | Eligible rows | Rate |",
        "|---|---:|---:|---:|",
        "| Current {0} delivered-line rate | {1} | {2} | {3:.1f}% |".format(
            terms["current"],
            current["on_time"], current["total"], current["rate"]
        ),
        "| {0} delivered-line rate | {1} | {2} | {3:.1f}% |".format(
            terms["previous"].title(),
            otif["previous"]["on_time"],
            otif["previous"]["total"],
            otif["previous"]["rate"],
        ),
    ]
    if not is_semester_report(data):
        lines.append(
            "| Semester-to-date delivered-line rate | {0} | {1} | {2:.1f}% |".format(
                otif["semester_to_date"]["on_time"],
                otif["semester_to_date"]["total"],
                otif["semester_to_date"]["rate"],
            )
        )
    lines.extend(
        [
        "| Strict delivered-in-full by due date | {0} | {1} | {2:.1f}% |".format(
            strict["delivered_in_full_by_due"],
            strict["eligible_lines"],
            strict["rate"],
        ),
        "",
        "Late delivered rows were distributed as follows: {0} were 1-2 days late, {1} were 3-7 days late, and {2} were more than 7 days late. Average lateness among late rows was {3:.1f} days.".format(
            current["late_1_2_days"],
            current["late_3_7_days"],
            current["late_over_7_days"],
            current["average_lateness_days"],
        ),
        "",
        "### Main Customer Contributors",
        "",
        "| Customer | Delivered rows | Late rows | Rate | Average lateness |",
        "|---|---:|---:|---:|---:|",
        ]
    )
    for row in otif["top_customers"][:8]:
        lines.append(
            "| {0} | {1} | {2} | {3:.1f}% | {4:.1f} days |".format(
                md(row["name"]),
                row["lines"],
                row["late"],
                row["rate"],
                row["average_lateness_days"],
            )
        )
    lines.extend(
        [
            "",
            "### Open Shortfall at {0}".format(terms["end"].title()),
            "",
            "| Sales Order | Customer | Item | Due date | Remaining qty |",
            "|---|---|---|---|---:|",
        ]
    )
    if strict["open_shortfalls"]:
        for row in strict["open_shortfalls"]:
            lines.append(
                "| {0} | {1} | `{2}` {3} | {4} | {5:g} |".format(
                    md(row["sales_order"]),
                    md(row["customer"]),
                    md(row["item_code"]),
                    md(row["item_name"]),
                    row["due_date"],
                    row["remaining_qty"],
                )
            )
    else:
        lines.append("| - | - | No open shortfall | - | 0 |")
    lines.append("")
    return lines


def render_english_machining(data):
    current = data["machining"]["current"]
    semester = data["machining"]["semester_to_date"]
    terms = period_terms(data, "en")
    lines = [
        "## 2. Internal vs External Machining",
        "",
        "| Family | Internal valid qty | External received qty | Internal ratio | Scrap qty | Scrap rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for family, label in (("plugs", "Plugs"), ("seats", "Valve seats")):
        row = current["families"][family]
        lines.append(
            "| {0} | {1:g} | {2:g} | {3:.1f}% | {4:g} | {5:.1f}% |".format(
                label,
                row["internal"],
                row["external"],
                row["internal_ratio"],
                row["scrap"],
                row["scrap_rate"],
            )
        )
    lines.extend(
        [
            "",
            "The {0} recorded {1:g} accepted pieces and {2:g} scrap pieces, for a combined scrap rate of **{3:.1f}%**. Semester-to-date accepted quantity is {4:g}, with a scrap rate of {5:.1f}%.".format(
                terms["current"],
                current["valid_qty"],
                current["scrap_qty"],
                current["scrap_rate"],
                semester["valid_qty"],
                semester["scrap_rate"],
            ),
            "",
            "### Scrap Pareto",
            "",
            "| Item | Valid qty | Scrap qty | Scrap rate |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in current["top_scrap_items"][:8]:
        lines.append(
            "| `{0}` {1} | {2:g} | {3:g} | {4:.1f}% |".format(
                md(row["item_code"]),
                md(row["item_name"]),
                row["valid_qty"],
                row["scrap_qty"],
                row["scrap_rate"],
            )
        )
    if not current["top_scrap_items"]:
        lines.append("| - | 0 | 0 | 0.0% |")
    lines.append("")
    return lines


def render_english_shipping(data):
    shipping = data["shipping"]
    terms = period_terms(data, "en")
    lines = [
        "## 3. Packaging and Shipping Issues",
        "",
        "{0} issues were opened during the {1}, equal to **{2:.2f} issues per 100 Delivery Notes**. {3} issues were unresolved beyond {4} days, {5} had a status/resolution inconsistency, and {6} lacked a dedicated Delivery Note link.".format(
            shipping["issue_count"],
            terms["current"],
            shipping["issue_rate_per_100_delivery_notes"],
            shipping["overdue_open_count"],
            ISSUE_AGE_TARGET_DAYS,
            shipping["status_resolution_inconsistency_count"],
            shipping["missing_delivery_note_link_count"],
        ),
        "",
        "| Issue | Opened | Status | Subject | Customer | Delivery Note | Age |",
        "|---|---|---|---|---|---|---:|",
    ]
    for row in shipping["issues"]:
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} days |".format(
                md(row["issue"]),
                row["opened"],
                md(row["status"]),
                md(row["subject"]),
                md(row["customer"]),
                md(row["delivery_note"] or "-"),
                row["age_days"],
            )
        )
    if not shipping["issues"]:
        lines.append("| - | - | - | No recorded issue | - | - | 0 days |")
    lines.append("")
    return lines


def render_english_procurement(data):
    procurement = data["procurement"]
    currency = data["scope"]["currency"]
    terms = period_terms(data, "en")
    lines = [
        "## 4. Procurement Price Evolution",
        "",
        "The KPI compares each item's latest Purchase Receipt in the {0} with its immediately preceding receipt. Statistical anomalies are excluded from the headline average but remain listed for review.".format(
            terms["current"]
        ),
        "",
        "| Measure | Result |",
        "|---|---:|",
        "| Item comparisons | {0} |".format(procurement["item_count"]),
        "| Included comparisons | {0} |".format(procurement["included_item_count"]),
        "| Statistical anomalies | {0} |".format(procurement["anomaly_count"]),
        "| Arithmetic price ratio | {0:.1f}% |".format(procurement["ratio_percent"]),
        "| Median price ratio | {0:.1f}% |".format(procurement["median_ratio_percent"]),
        "| Weighted price ratio | {0:.1f}% |".format(procurement["weighted_ratio_percent"]),
        "| Estimated impact on latest quantities | {0} {1:,.2f} |".format(
            currency,
            procurement["estimated_price_impact"],
        ),
        "",
        "### Items Requiring Commercial Review",
        "",
        "| Item | Change | Estimated impact | Latest supplier | Previous supplier |",
        "|---|---:|---:|---|---|",
    ]
    for row in procurement["review_items"][:10]:
        lines.append(
            "| `{0}` {1} | {2:+.1f}% | {3} {4:,.2f} | {5} | {6} |".format(
                md(row["item_code"]),
                md(row["item_name"]),
                row["change_percent"],
                currency,
                row["estimated_price_impact"],
                md(row["latest_supplier"]),
                md(row["previous_supplier"]),
            )
        )
    if not procurement["review_items"]:
        lines.append("| - | 0.0% | {0} 0.00 | - | - |".format(currency))
    lines.extend(
        [
            "",
            "### Statistical Anomalies",
            "",
            "| Item | Change | Latest qty | Latest supplier | Previous supplier |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in procurement["anomalies"][:10]:
        lines.append(
            "| `{0}` {1} | {2:+.1f}% | {3:g} | {4} | {5} |".format(
                md(row["item_code"]),
                md(row["item_name"]),
                row["change_percent"],
                row["latest_stock_qty"],
                md(row["latest_supplier"]),
                md(row["previous_supplier"]),
            )
        )
    if not procurement["anomalies"]:
        lines.append("| - | 0.0% | 0 | - | - |")
    lines.append("")
    return lines


def render_english_ai_insights(ai_insights):
    lines = [
        "## 5. AI-Assisted Operational Insights",
        "",
        "> Decision support generated from the KPI snapshot and validated against "
        "the cited source paths. Management approval remains authoritative.",
        "",
        clean_text(ai_insights.get("executive_summary_en")),
        "",
    ]
    for index, insight in enumerate(ai_insights.get("insights", []), 1):
        finding_type = clean_text(insight.get("finding_type"))
        lines.extend(
            [
                "### 5.{0} {1}".format(
                    index,
                    clean_text(insight.get("title_en")),
                ),
                "",
                "**Severity:** {0}  ".format(
                    clean_text(insight.get("severity"))
                ),
                "**Classification:** {0}  ".format(finding_type),
                "**Confidence:** {0:.0f}%".format(
                    flt(insight.get("confidence")) * 100
                ),
                "",
                "**Finding:** {0}".format(
                    clean_text(insight.get("finding_en"))
                ),
                "",
                "**Operational impact:** {0}".format(
                    clean_text(insight.get("operational_impact_en"))
                ),
                "",
                "**Recommended action:** {0}".format(
                    clean_text(insight.get("recommendation_en"))
                ),
                "",
                "**Evidence:**",
            ]
        )
        for evidence in insight.get("evidence", []):
            lines.append(
                "- `{0}` = **{1}**".format(
                    md(evidence.get("source_path")),
                    md(evidence.get("value")),
                )
            )
        lines.append("")

    questions = ai_insights.get("management_questions_en", [])
    if questions:
        lines.extend(["### Management Questions", ""])
        lines.extend(
            "- {0}".format(clean_text(question))
            for question in questions
        )
        lines.append("")

    warnings = ai_insights.get("data_quality_warnings", [])
    if warnings:
        lines.extend(["### Data Quality Warnings", ""])
        lines.extend(
            "- {0}".format(clean_text(warning))
            for warning in warnings
        )
        lines.append("")
    return lines


def render_english_actions(data, section_number=5):
    actions = build_actions(data, "en")
    lines = [
        "## {0}. Improvement Plan".format(section_number),
        "",
        "| Priority action | Owner | Deadline | Success measure |",
        "|---|---|---|---|",
    ]
    for action in actions:
        lines.append(
            "| {0} | {1} | {2} | {3} |".format(
                md(action["action"]),
                md(action["owner"]),
                md(action["deadline"]),
                md(action["measure"]),
            )
        )
    lines.extend(
        [
            "",
            "### Recommended Management Cadence",
            "",
            "- **Twice weekly:** due-line exceptions, material constraints, production readiness, shipment documentation and customer communication.",
            "- **Weekly:** customer/root-cause OTIF, machining schedule adherence, scrap Pareto, supplier shortages and issue aging.",
            "- **Monthly:** capacity and demand by product family, supplier scorecards, cost per accepted machined piece and purchase-price impact.",
            "",
        ]
    )
    return lines


def render_english_notes(data, section_number=6):
    terms = period_terms(data, "en")
    return [
        "## {0}. Calculation and Data Notes".format(section_number),
        "",
        "1. The report is an immutable {0} snapshot generated from submitted ERPNext transactions.".format(
            terms["snapshot"]
        ),
        "2. The delivered-line KPI is the existing dashboard logic; strict OTIF additionally checks full quantity by the Sales Order Item due date.",
        "3. Internal machining uses submitted Planning `quantite_validee`; external machining uses submitted, non-return Purchase Receipts.",
        "4. Scrap rate is `scrap / (valid + scrap)`.",
        "5. Procurement rates are normalized base rates in {0}; estimated impact applies only to the latest quantities represented by included comparisons.".format(
            data["scope"]["currency"]
        ),
        "6. Statistical anomalies can represent either data defects or valid commercial changes and require classification.",
        "",
    ]


def render_french_report(data, ai_insights=None):
    scope = data["scope"]
    otif = data["otif"]
    machining = data["machining"]["current"]
    shipping = data["shipping"]
    procurement = data["procurement"]
    strict = otif["strict"]
    currency = scope["currency"]
    terms = period_terms(data, "fr")
    lines = [
        "# {0}".format(terms["title"]),
        "",
        "## {0}".format(scope["period_label"]),
        "",
        "**Société :** {0}  ".format(scope["company"]),
        "**Période :** du {0} au {1}  ".format(scope["period_start"], scope["period_end"]),
        "**Généré le :** {0}".format(scope["generated_on"]),
        "",
        "## Synthèse",
        "",
    ]
    lines.extend(get_french_executive_findings(data))
    lines.extend(
        [
            "",
            "## Tableau de synthèse des KPI",
            "",
            "| KPI | {0} | Évaluation |".format(terms["result"]),
            "|---|---:|---|",
            "| Taux de lignes livrées à temps | {0:.1f}% | {1} |".format(
                otif["current"]["rate"],
                kpi_assessment_fr(otif["current"]["rate"], OTIF_TARGET, True),
            ),
            "| Livraison stricte, complète à la date prévue | {0:.1f}% | {1} |".format(
                strict["rate"],
                kpi_assessment_fr(strict["rate"], STRICT_OTIF_TARGET, True),
            ),
            "| Quantité échue ouverte | {0} lignes / {1:g} unités | {2} |".format(
                strict["open_shortfall_lines"],
                strict["open_shortfall_qty"],
                "Action requise" if strict["open_shortfall_lines"] else "Maîtrisé",
            ),
            "| Usinage interne des plugs | {0:.1f}% | Mix de production |".format(
                machining["families"]["plugs"]["internal_ratio"]
            ),
            "| Usinage interne des sièges | {0:.1f}% | Mix de production |".format(
                machining["families"]["seats"]["internal_ratio"]
            ),
            "| Taux de rebut d'usinage | {0:.1f}% | {1} |".format(
                machining["scrap_rate"],
                kpi_assessment_fr(machining["scrap_rate"], SCRAP_TARGET, False),
            ),
            "| Problèmes d'emballage et d'expédition | {0} | {1:.2f} pour 100 Delivery Notes |".format(
                shipping["issue_count"],
                shipping["issue_rate_per_100_delivery_notes"],
            ),
            "| Ratio des prix d'achat | {0:.1f}% | 100% = prix inchangé |".format(
                procurement["ratio_percent"]
            ),
            "| Ratio des prix d'achat pondéré | {0:.1f}% | Impact estimé : {1} {2:,.2f} |".format(
                procurement["weighted_ratio_percent"],
                currency,
                procurement["estimated_price_impact"],
            ),
            "| Anomalies d'achat | {0} / {1} | Revue requise |".format(
                procurement["anomaly_count"],
                procurement["item_count"],
            ),
            "",
        ]
    )
    lines.extend(render_french_otif(data))
    lines.extend(render_french_machining(data))
    lines.extend(render_french_shipping(data))
    lines.extend(render_french_procurement(data))
    if ai_insights:
        lines.extend(render_french_ai_insights(ai_insights))
    lines.extend(render_french_actions(data, 6 if ai_insights else 5))
    lines.extend(render_french_notes(data, 7 if ai_insights else 6))
    return "\n".join(lines).strip() + "\n"


def get_french_executive_findings(data):
    otif = data["otif"]
    strict = otif["strict"]
    machining = data["machining"]["current"]
    shipping = data["shipping"]
    procurement = data["procurement"]
    terms = period_terms(data, "fr")
    change = otif["change_vs_previous_points"]
    if change is None:
        change_text = "Aucune ligne livrée comparable n'était disponible pour le {0}.".format(
            terms["previous"]
        )
    else:
        direction = "progressé" if change >= 0 else "reculé"
        change_text = "Le taux a {0} de {1:.1f} points par rapport au {2}.".format(
            direction,
            abs(change),
            terms["previous"],
        )
    return [
        "1. **Performance de livraison :** le taux de lignes livrées à temps est de **{0:.1f}%** et l'OTIF strict de **{1:.1f}%**. {2}".format(
            otif["current"]["rate"],
            strict["rate"],
            change_text,
        ),
        "2. **Reste à livrer :** {0} lignes échues représentant {1:g} unités de stock restaient incomplètes à la {2}.".format(
            strict["open_shortfall_lines"],
            strict["open_shortfall_qty"],
            terms["end"],
        ),
        "3. **Usinage :** les plugs sont produits à {0:.1f}% en interne et les sièges à {1:.1f}% en interne. Le taux de rebut combiné est de **{2:.1f}%**.".format(
            machining["families"]["plugs"]["internal_ratio"],
            machining["families"]["seats"]["internal_ratio"],
            machining["scrap_rate"],
        ),
        "4. **Maîtrise des expéditions :** {0} problèmes d'emballage ou d'expédition ont été ouverts, dont {1} non résolus depuis plus de {2} jours.".format(
            shipping["issue_count"],
            shipping["overdue_open_count"],
            ISSUE_AGE_TARGET_DAYS,
        ),
        "5. **Achats :** le ratio arithmétique est de **{0:.1f}%**, le ratio pondéré de **{1:.1f}%** et l'impact estimé sur les dernières quantités de **{2} {3:,.2f}**. {4} anomalies statistiques doivent être classées.".format(
            procurement["ratio_percent"],
            procurement["weighted_ratio_percent"],
            data["scope"]["currency"],
            procurement["estimated_price_impact"],
            procurement["anomaly_count"],
        ),
    ]


def render_french_otif(data):
    otif = data["otif"]
    current = otif["current"]
    strict = otif["strict"]
    terms = period_terms(data, "fr")
    lines = [
        "## 1. OTIF et performance de livraison",
        "",
        "La mesure du tableau de bord compte les lignes d'articles de Delivery Notes soumis et hors retours, puis compare leur date de comptabilisation à la date prévue sur la ligne du Sales Order. La mesure stricte exige en plus que toute la quantité de stock commandée soit livrée à la date prévue.",
        "",
        "| Vue | À temps / complet | Lignes éligibles | Taux |",
        "|---|---:|---:|---:|",
        "| Taux des lignes livrées du {0} | {1} | {2} | {3:.1f}% |".format(
            terms["current"],
            current["on_time"], current["total"], current["rate"]
        ),
        "| Taux des lignes livrées du {0} | {1} | {2} | {3:.1f}% |".format(
            terms["previous"],
            otif["previous"]["on_time"],
            otif["previous"]["total"],
            otif["previous"]["rate"],
        ),
    ]
    if not is_semester_report(data):
        lines.append(
            "| Taux des lignes livrées depuis le début du semestre | {0} | {1} | {2:.1f}% |".format(
                otif["semester_to_date"]["on_time"],
                otif["semester_to_date"]["total"],
                otif["semester_to_date"]["rate"],
            )
        )
    lines.extend(
        [
        "| Livraison stricte et complète à la date prévue | {0} | {1} | {2:.1f}% |".format(
            strict["delivered_in_full_by_due"],
            strict["eligible_lines"],
            strict["rate"],
        ),
        "",
        "Parmi les lignes livrées en retard, {0} avaient 1 à 2 jours de retard, {1} avaient 3 à 7 jours et {2} dépassaient 7 jours. Le retard moyen des lignes en retard était de {3:.1f} jours.".format(
            current["late_1_2_days"],
            current["late_3_7_days"],
            current["late_over_7_days"],
            current["average_lateness_days"],
        ),
        "",
        "### Principaux contributeurs par client",
        "",
        "| Client | Lignes livrées | Lignes en retard | Taux | Retard moyen |",
        "|---|---:|---:|---:|---:|",
        ]
    )
    for row in otif["top_customers"][:8]:
        lines.append(
            "| {0} | {1} | {2} | {3:.1f}% | {4:.1f} jours |".format(
                md(row["name"]),
                row["lines"],
                row["late"],
                row["rate"],
                row["average_lateness_days"],
            )
        )
    lines.extend(
        [
            "",
            "### Quantités ouvertes à la {0}".format(terms["end"]),
            "",
            "| Sales Order | Client | Article | Date prévue | Quantité restante |",
            "|---|---|---|---|---:|",
        ]
    )
    if strict["open_shortfalls"]:
        for row in strict["open_shortfalls"]:
            lines.append(
                "| {0} | {1} | `{2}` {3} | {4} | {5:g} |".format(
                    md(row["sales_order"]),
                    md(row["customer"]),
                    md(row["item_code"]),
                    md(row["item_name"]),
                    row["due_date"],
                    row["remaining_qty"],
                )
            )
    else:
        lines.append("| - | - | Aucun reste à livrer ouvert | - | 0 |")
    lines.append("")
    return lines


def render_french_machining(data):
    current = data["machining"]["current"]
    semester = data["machining"]["semester_to_date"]
    terms = period_terms(data, "fr")
    lines = [
        "## 2. Usinage interne et externe",
        "",
        "| Famille | Quantité interne validée | Quantité externe reçue | Ratio interne | Rebut | Taux de rebut |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for family, label in (("plugs", "Plugs"), ("seats", "Sièges de vanne")):
        row = current["families"][family]
        lines.append(
            "| {0} | {1:g} | {2:g} | {3:.1f}% | {4:g} | {5:.1f}% |".format(
                label,
                row["internal"],
                row["external"],
                row["internal_ratio"],
                row["scrap"],
                row["scrap_rate"],
            )
        )
    lines.extend(
        [
            "",
            "Le {0} comprend {1:g} pièces acceptées et {2:g} pièces rebutées, soit un taux de rebut combiné de **{3:.1f}%**. Depuis le début du semestre, la quantité acceptée est de {4:g}, avec un taux de rebut de {5:.1f}%.".format(
                terms["current"],
                current["valid_qty"],
                current["scrap_qty"],
                current["scrap_rate"],
                semester["valid_qty"],
                semester["scrap_rate"],
            ),
            "",
            "### Pareto des rebuts",
            "",
            "| Article | Quantité valide | Rebut | Taux de rebut |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in current["top_scrap_items"][:8]:
        lines.append(
            "| `{0}` {1} | {2:g} | {3:g} | {4:.1f}% |".format(
                md(row["item_code"]),
                md(row["item_name"]),
                row["valid_qty"],
                row["scrap_qty"],
                row["scrap_rate"],
            )
        )
    if not current["top_scrap_items"]:
        lines.append("| - | 0 | 0 | 0.0% |")
    lines.append("")
    return lines


def render_french_shipping(data):
    shipping = data["shipping"]
    terms = period_terms(data, "fr")
    lines = [
        "## 3. Problèmes d'emballage et d'expédition",
        "",
        "{0} problèmes ont été ouverts pendant le {1}, soit **{2:.2f} problèmes pour 100 Delivery Notes**. {3} problèmes sont restés non résolus au-delà de {4} jours, {5} présentent une incohérence entre statut et résolution et {6} ne possèdent pas de lien Delivery Note dédié.".format(
            shipping["issue_count"],
            terms["current"],
            shipping["issue_rate_per_100_delivery_notes"],
            shipping["overdue_open_count"],
            ISSUE_AGE_TARGET_DAYS,
            shipping["status_resolution_inconsistency_count"],
            shipping["missing_delivery_note_link_count"],
        ),
        "",
        "| Issue | Ouverture | Statut | Sujet | Client | Delivery Note | Ancienneté |",
        "|---|---|---|---|---|---|---:|",
    ]
    for row in shipping["issues"]:
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} jours |".format(
                md(row["issue"]),
                row["opened"],
                md(row["status"]),
                md(row["subject"]),
                md(row["customer"]),
                md(row["delivery_note"] or "-"),
                row["age_days"],
            )
        )
    if not shipping["issues"]:
        lines.append("| - | - | - | Aucun problème enregistré | - | - | 0 jour |")
    lines.append("")
    return lines


def render_french_procurement(data):
    procurement = data["procurement"]
    currency = data["scope"]["currency"]
    terms = period_terms(data, "fr")
    lines = [
        "## 4. Évolution des prix d'achat",
        "",
        "Le KPI compare le Purchase Receipt le plus récent de chaque article pendant le {0} avec sa réception immédiatement précédente. Les anomalies statistiques sont exclues de la moyenne principale mais restent listées pour revue.".format(
            terms["current"]
        ),
        "",
        "| Mesure | Résultat |",
        "|---|---:|",
        "| Comparaisons d'articles | {0} |".format(procurement["item_count"]),
        "| Comparaisons retenues | {0} |".format(procurement["included_item_count"]),
        "| Anomalies statistiques | {0} |".format(procurement["anomaly_count"]),
        "| Ratio arithmétique des prix | {0:.1f}% |".format(procurement["ratio_percent"]),
        "| Ratio médian des prix | {0:.1f}% |".format(procurement["median_ratio_percent"]),
        "| Ratio pondéré des prix | {0:.1f}% |".format(procurement["weighted_ratio_percent"]),
        "| Impact estimé sur les dernières quantités | {0} {1:,.2f} |".format(
            currency,
            procurement["estimated_price_impact"],
        ),
        "",
        "### Articles nécessitant une revue commerciale",
        "",
        "| Article | Variation | Impact estimé | Dernier fournisseur | Fournisseur précédent |",
        "|---|---:|---:|---|---|",
    ]
    for row in procurement["review_items"][:10]:
        lines.append(
            "| `{0}` {1} | {2:+.1f}% | {3} {4:,.2f} | {5} | {6} |".format(
                md(row["item_code"]),
                md(row["item_name"]),
                row["change_percent"],
                currency,
                row["estimated_price_impact"],
                md(row["latest_supplier"]),
                md(row["previous_supplier"]),
            )
        )
    if not procurement["review_items"]:
        lines.append("| - | 0.0% | {0} 0.00 | - | - |".format(currency))
    lines.extend(
        [
            "",
            "### Anomalies statistiques",
            "",
            "| Article | Variation | Dernière quantité | Dernier fournisseur | Fournisseur précédent |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in procurement["anomalies"][:10]:
        lines.append(
            "| `{0}` {1} | {2:+.1f}% | {3:g} | {4} | {5} |".format(
                md(row["item_code"]),
                md(row["item_name"]),
                row["change_percent"],
                row["latest_stock_qty"],
                md(row["latest_supplier"]),
                md(row["previous_supplier"]),
            )
        )
    if not procurement["anomalies"]:
        lines.append("| - | 0.0% | 0 | - | - |")
    lines.append("")
    return lines


def render_french_ai_insights(ai_insights):
    lines = [
        "## 5. Analyse opérationnelle assistée par IA",
        "",
        "> Aide à la décision générée à partir de l'instantané KPI et validée "
        "contre les chemins sources cités. L'approbation managériale reste "
        "l'autorité de référence.",
        "",
        clean_text(ai_insights.get("executive_summary_fr")),
        "",
    ]
    for index, insight in enumerate(ai_insights.get("insights", []), 1):
        finding_type = {
            "Confirmed": "Fait confirmé",
            "Hypothesis": "Hypothèse à vérifier",
        }.get(
            insight.get("finding_type"),
            clean_text(insight.get("finding_type")),
        )
        severity = {
            "Critical": "Critique",
            "High": "Élevée",
            "Medium": "Moyenne",
            "Low": "Faible",
        }.get(
            insight.get("severity"),
            clean_text(insight.get("severity")),
        )
        lines.extend(
            [
                "### 5.{0} {1}".format(
                    index,
                    clean_text(insight.get("title_fr")),
                ),
                "",
                "**Sévérité :** {0}  ".format(severity),
                "**Classification :** {0}  ".format(finding_type),
                "**Confiance :** {0:.0f}%".format(
                    flt(insight.get("confidence")) * 100
                ),
                "",
                "**Constat :** {0}".format(
                    clean_text(insight.get("finding_fr"))
                ),
                "",
                "**Impact opérationnel :** {0}".format(
                    clean_text(insight.get("operational_impact_fr"))
                ),
                "",
                "**Action recommandée :** {0}".format(
                    clean_text(insight.get("recommendation_fr"))
                ),
                "",
                "**Preuves :**",
            ]
        )
        for evidence in insight.get("evidence", []):
            lines.append(
                "- `{0}` = **{1}**".format(
                    md(evidence.get("source_path")),
                    md(evidence.get("value")),
                )
            )
        lines.append("")

    questions = ai_insights.get("management_questions_fr", [])
    if questions:
        lines.extend(["### Questions de pilotage", ""])
        lines.extend(
            "- {0}".format(clean_text(question))
            for question in questions
        )
        lines.append("")

    warnings = ai_insights.get("data_quality_warnings", [])
    if warnings:
        lines.extend(["### Alertes de qualité des données", ""])
        lines.extend(
            "- {0}".format(clean_text(warning))
            for warning in warnings
        )
        lines.append("")
    return lines


def render_french_actions(data, section_number=5):
    actions = build_actions(data, "fr")
    lines = [
        "## {0}. Plan d'amélioration".format(section_number),
        "",
        "| Action prioritaire | Responsable | Échéance | Mesure de réussite |",
        "|---|---|---|---|",
    ]
    for action in actions:
        lines.append(
            "| {0} | {1} | {2} | {3} |".format(
                md(action["action"]),
                md(action["owner"]),
                md(action["deadline"]),
                md(action["measure"]),
            )
        )
    lines.extend(
        [
            "",
            "### Rythme de pilotage recommandé",
            "",
            "- **Deux fois par semaine :** exceptions sur les lignes échues, contraintes matière, préparation de la production, documentation d'expédition et communication client.",
            "- **Chaque semaine :** OTIF par client et cause, respect du programme d'usinage, Pareto des rebuts, ruptures fournisseurs et ancienneté des Issues.",
            "- **Chaque mois :** capacité et demande par famille, scorecards fournisseurs, coût par pièce usinée acceptée et impact des prix d'achat.",
            "",
        ]
    )
    return lines


def render_french_notes(data, section_number=6):
    terms = period_terms(data, "fr")
    return [
        "## {0}. Notes de calcul et de données".format(section_number),
        "",
        "1. Le rapport constitue un instantané {0} immuable généré à partir des transactions ERPNext soumises.".format(
            terms["snapshot"]
        ),
        "2. Le KPI de lignes livrées reprend la logique actuelle du tableau de bord ; l'OTIF strict vérifie également la quantité complète à la date prévue de la ligne de Sales Order.",
        "3. L'usinage interne utilise `quantite_validee` des Planning soumis ; l'usinage externe utilise les Purchase Receipts soumis et hors retours.",
        "4. Le taux de rebut est calculé selon `rebut / (valide + rebut)`.",
        "5. Les prix d'achat utilisent les taux de base normalisés en {0} ; l'impact estimé porte uniquement sur les dernières quantités des comparaisons retenues.".format(
            data["scope"]["currency"]
        ),
        "6. Les anomalies statistiques peuvent représenter des défauts de données ou des changements commerciaux valides et nécessitent une classification.",
        "",
    ]


def build_actions(data, language):
    otif = data["otif"]
    strict = otif["strict"]
    machining = data["machining"]["current"]
    shipping = data["shipping"]
    procurement = data["procurement"]
    actions = []

    if language == "fr":
        if otif["current"]["rate"] < OTIF_TARGET:
            actions.append(
                {
                    "action": "Lancer une revue des lignes à risque et attribuer une cause à chaque retard.",
                    "owner": "Responsable des opérations",
                    "deadline": "Sous 5 jours ouvrés",
                    "measure": "100% des lignes en retard avec cause, responsable et date de rattrapage.",
                }
            )
        if strict["open_shortfall_lines"]:
            actions.append(
                {
                    "action": "Rattraper ou replanifier avec accord client les lignes échues encore ouvertes.",
                    "owner": "Opérations + Administration des ventes",
                    "deadline": "Sous 10 jours ouvrés",
                    "measure": "{0} lignes / {1:g} unités ramenées à zéro ou replanifiées.".format(
                        strict["open_shortfall_lines"],
                        strict["open_shortfall_qty"],
                    ),
                }
            )
        if machining["scrap_rate"] > SCRAP_TARGET:
            actions.append(
                {
                    "action": "Ouvrir des actions de réduction du rebut sur les premières références du Pareto.",
                    "owner": "Production + Qualité",
                    "deadline": "Sous 30 jours",
                    "measure": "Taux de rebut mensuel inférieur à {0:.1f}%.".format(
                        SCRAP_TARGET
                    ),
                }
            )
        if shipping["overdue_open_count"] or shipping["status_resolution_inconsistency_count"]:
            actions.append(
                {
                    "action": "Clôturer les Issues résolus et escalader les problèmes d'expédition anciens.",
                    "owner": "Qualité + Logistique",
                    "deadline": "Sous 10 jours ouvrés",
                    "measure": "Aucun Issue incohérent et aucun problème ouvert de plus de {0} jours sans plan.".format(
                        ISSUE_AGE_TARGET_DAYS
                    ),
                }
            )
        if procurement["anomaly_count"] or procurement["review_items"]:
            actions.append(
                {
                    "action": "Classer les anomalies et valider les écarts de prix significatifs en CHF.",
                    "owner": "Achats + Données de base",
                    "deadline": "Sous 10 jours ouvrés",
                    "measure": "100% des anomalies et écarts au-dessus des seuils documentés.",
                }
            )
        actions.append(
            {
                "action": "Publier le plan d'action du mois dans la revue opérationnelle.",
                "owner": "Responsable des opérations",
                "deadline": "Avant la prochaine revue mensuelle",
                "measure": "Chaque action possède un responsable, une échéance et une preuve de clôture.",
            }
        )
        return actions

    if otif["current"]["rate"] < OTIF_TARGET:
        actions.append(
            {
                "action": "Run a due-line exception review and assign a root cause to every late line.",
                "owner": "Head of Operations",
                "deadline": "Within 5 working days",
                "measure": "100% of late lines have a cause, owner and recovery date.",
            }
        )
    if strict["open_shortfall_lines"]:
        actions.append(
            {
                "action": "Recover or customer-approve rescheduling of all open overdue lines.",
                "owner": "Operations + Sales Administration",
                "deadline": "Within 10 working days",
                "measure": "{0} lines / {1:g} units reduced to zero or rescheduled.".format(
                    strict["open_shortfall_lines"],
                    strict["open_shortfall_qty"],
                ),
            }
        )
    if machining["scrap_rate"] > SCRAP_TARGET:
        actions.append(
            {
                "action": "Open focused scrap-reduction actions for the leading Pareto references.",
                "owner": "Production + Quality",
                "deadline": "Within 30 days",
                "measure": "Monthly scrap rate below {0:.1f}%.".format(SCRAP_TARGET),
            }
        )
    if shipping["overdue_open_count"] or shipping["status_resolution_inconsistency_count"]:
        actions.append(
            {
                "action": "Close resolved Issues and escalate aged shipping problems.",
                "owner": "Quality + Logistics",
                "deadline": "Within 10 working days",
                "measure": "No inconsistent Issue and no problem older than {0} days without a plan.".format(
                    ISSUE_AGE_TARGET_DAYS
                ),
            }
        )
    if procurement["anomaly_count"] or procurement["review_items"]:
        actions.append(
            {
                "action": "Classify anomalies and approve material price variances by CHF impact.",
                "owner": "Procurement + Master Data",
                "deadline": "Within 10 working days",
                "measure": "100% of anomalies and threshold breaches documented.",
            }
        )
    actions.append(
        {
            "action": "Publish the monthly action plan in the operations review.",
            "owner": "Head of Operations",
            "deadline": "Before the next monthly review",
            "measure": "Every action has an owner, deadline and closure evidence.",
        }
    )
    return actions


def set_snapshot_fields(doc, data):
    current_machining = data["machining"]["current"]
    procurement = data["procurement"]
    shipping = data["shipping"]
    strict = data["otif"]["strict"]
    doc.otif_rate = data["otif"]["current"]["rate"]
    doc.strict_otif_rate = strict["rate"]
    doc.open_shortfall_lines = strict["open_shortfall_lines"]
    doc.open_shortfall_qty = strict["open_shortfall_qty"]
    doc.plug_internal_ratio = current_machining["families"]["plugs"]["internal_ratio"]
    doc.seat_internal_ratio = current_machining["families"]["seats"]["internal_ratio"]
    doc.machining_scrap_rate = current_machining["scrap_rate"]
    doc.shipping_issue_count = shipping["issue_count"]
    doc.shipping_issue_rate = shipping["issue_rate_per_100_delivery_notes"]
    doc.purchase_price_ratio = procurement["ratio_percent"]
    doc.weighted_purchase_price_ratio = procurement["weighted_ratio_percent"]
    doc.purchase_price_impact = procurement["estimated_price_impact"]
    doc.procurement_anomaly_count = procurement["anomaly_count"]


def set_ai_fields(
    doc,
    settings,
    ai_enabled=False,
    ai_result=None,
    ai_error="",
):
    doc.ai_approved = 0
    doc.ai_approved_by = None
    doc.ai_approved_on = None
    doc.ai_rejection_reason = ""

    if not cint(ai_enabled):
        doc.ai_status = "Disabled"
        doc.ai_model = ""
        doc.ai_response_id = ""
        doc.ai_prompt_version = ""
        doc.ai_generated_on = None
        doc.ai_latency_ms = 0
        doc.ai_input_tokens = 0
        doc.ai_output_tokens = 0
        doc.ai_total_tokens = 0
        doc.ai_payload_sha256 = ""
        doc.ai_summary_english = ""
        doc.ai_summary_french = ""
        doc.ai_insights_json = ""
        doc.ai_error = ""
        return

    if not ai_result:
        doc.ai_status = "Failed"
        doc.ai_model = settings.get("ai_model") or ""
        doc.ai_prompt_version = settings.get("ai_prompt_version") or ""
        doc.ai_generated_on = now_datetime()
        doc.ai_response_id = ""
        doc.ai_latency_ms = 0
        doc.ai_input_tokens = 0
        doc.ai_output_tokens = 0
        doc.ai_total_tokens = 0
        doc.ai_payload_sha256 = ""
        doc.ai_summary_english = ""
        doc.ai_summary_french = ""
        doc.ai_insights_json = ""
        doc.ai_error = ai_error
        return

    insights = ai_result["insights"]
    doc.ai_status = (
        "Approval Required"
        if cint(settings.get("require_human_approval", 1))
        else "Completed"
    )
    doc.ai_model = ai_result.get("model")
    doc.ai_response_id = ai_result.get("response_id")
    doc.ai_prompt_version = ai_result.get("prompt_version")
    doc.ai_generated_on = now_datetime()
    doc.ai_latency_ms = ai_result.get("latency_ms")
    doc.ai_input_tokens = ai_result.get("input_tokens")
    doc.ai_output_tokens = ai_result.get("output_tokens")
    doc.ai_total_tokens = ai_result.get("total_tokens")
    doc.ai_payload_sha256 = ai_result.get("payload_sha256")
    doc.ai_summary_english = insights.get("executive_summary_en")
    doc.ai_summary_french = insights.get("executive_summary_fr")
    doc.ai_insights_json = json.dumps(
        insights,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    doc.ai_error = ""


def rebuild_report_outputs(report_name, include_ai=False, send_email_after=False):
    warnings = []
    doc = frappe.get_doc(REPORT_DOCTYPE, report_name)
    settings = get_settings()
    if not doc.kpi_data_json:
        frappe.throw(_("The report has no KPI snapshot to rebuild."))

    data = json.loads(doc.kpi_data_json)
    ai_insights = None
    if include_ai:
        if not doc.ai_insights_json:
            frappe.throw(_("The report has no validated AI insight output."))
        ai_insights = json.loads(doc.ai_insights_json)

    english_markdown = (
        render_report(data, "en", ai_insights)
        if cint(settings.generate_english)
        else ""
    )
    french_markdown = (
        render_report(data, "fr", ai_insights)
        if cint(settings.generate_french)
        else ""
    )
    doc.english_markdown = english_markdown
    doc.french_markdown = french_markdown
    doc.save(ignore_permissions=True)

    remove_generated_files(doc)
    file_updates = create_report_files(
        doc,
        english_markdown,
        french_markdown,
        settings,
        warnings,
    )
    for fieldname, file_url in file_updates.items():
        doc.db_set(fieldname, file_url, update_modified=False)

    if send_email_after and cint(doc.send_email):
        doc.reload()
        email_report(doc.name, force=True)

    if warnings:
        frappe.db.set_value(
            REPORT_DOCTYPE,
            doc.name,
            {
                "status": "Completed with Warnings",
                "generation_log": "\n\n".join(warnings),
            },
            update_modified=True,
        )
    return {
        "name": doc.name,
        "included_ai": bool(ai_insights),
        "warnings": warnings,
    }


def create_report_files(doc, english_markdown, french_markdown, settings, warnings):
    updates = {
        "english_markdown_file": None,
        "english_pdf_file": None,
        "french_markdown_file": None,
        "french_pdf_file": None,
    }
    period = get_report_period_label(doc).replace("-", "_")
    base_name = "operations_report_{0}".format(period)

    for language, content, prefix in (
        ("english", english_markdown, base_name),
        ("french", french_markdown, "rapport_operations_{0}_fr".format(period)),
    ):
        if not content:
            continue
        if cint(settings.generate_markdown):
            file_doc = save_file(
                prefix + ".md",
                content.encode("utf-8"),
                REPORT_DOCTYPE,
                doc.name,
                is_private=1,
            )
            updates[language + "_markdown_file"] = file_doc.file_url

        if cint(settings.generate_pdf):
            try:
                html = build_pdf_html(content, language, doc.period_type)
                pdf_content = get_pdf(
                    html,
                    options={
                        "page-size": "A4",
                        "margin-top": "15mm",
                        "margin-right": "12mm",
                        "margin-bottom": "15mm",
                        "margin-left": "12mm",
                        "encoding": "UTF-8",
                    },
                )
                pdf_doc = save_file(
                    prefix + ".pdf",
                    pdf_content,
                    REPORT_DOCTYPE,
                    doc.name,
                    is_private=1,
                )
                updates[language + "_pdf_file"] = pdf_doc.file_url
            except Exception:
                warnings.append(
                    "{0} PDF generation failed: {1}".format(
                        language.title(),
                        frappe.get_traceback(),
                    )
                )

    return updates


def build_pdf_html(markdown_content, language, period_type="Monthly"):
    semester = period_type == "Semester"
    if language == "french":
        title = (
            "Rapport semestriel de performance opérationnelle"
            if semester
            else "Rapport mensuel de performance opérationnelle"
        )
    else:
        title = (
            "Semester Operations Performance Report"
            if semester
            else "Monthly Operations Performance Report"
        )
    return """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <style>
            body {{ font-family: Arial, sans-serif; color: #202124; font-size: 10pt; line-height: 1.42; }}
            h1 {{ font-size: 22pt; color: #17365d; margin-bottom: 8px; }}
            h2 {{ font-size: 15pt; color: #244a73; margin-top: 24px; border-bottom: 1px solid #b8c6d6; padding-bottom: 4px; }}
            h3 {{ font-size: 12pt; color: #315d85; margin-top: 18px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 10px 0 16px; page-break-inside: auto; }}
            th, td {{ border: 1px solid #c7cdd4; padding: 5px 7px; vertical-align: top; }}
            th {{ background: #e9eef3; font-weight: bold; }}
            tr {{ page-break-inside: avoid; }}
            code {{ background: #f2f4f6; padding: 1px 3px; }}
            ul, ol {{ margin-top: 4px; }}
        </style>
    </head>
    <body>{body}</body>
    </html>
    """.format(title=title, body=md_to_html(markdown_content))


def remove_generated_files(doc):
    file_urls = [
        doc.english_markdown_file,
        doc.english_pdf_file,
        doc.french_markdown_file,
        doc.french_pdf_file,
    ]
    for file_url in [url for url in file_urls if url]:
        file_name = frappe.db.get_value(
            "File",
            {
                "file_url": file_url,
                "attached_to_doctype": REPORT_DOCTYPE,
                "attached_to_name": doc.name,
            },
            "name",
        )
        if file_name:
            frappe.delete_doc("File", file_name, ignore_permissions=True)


def email_report(report_name, force=False):
    doc = frappe.get_doc(REPORT_DOCTYPE, report_name)
    if doc.ai_status == "Approval Required":
        frappe.throw(
            _(
                "AI insights require approval before this report can be distributed."
            )
        )
    if doc.email_sent_on and not force:
        return {"name": doc.name, "skipped": True, "reason": "Already sent."}
    recipients = parse_recipients(doc.email_recipients)
    if not recipients:
        frappe.throw(_("No valid email recipient is configured."))

    settings = get_settings()
    attachments = []
    for file_url in (
        doc.english_pdf_file,
        doc.french_pdf_file,
        doc.english_markdown_file,
        doc.french_markdown_file,
    ):
        if not file_url:
            continue
        file_id = frappe.db.get_value(
            "File",
            {
                "file_url": file_url,
                "attached_to_doctype": REPORT_DOCTYPE,
                "attached_to_name": doc.name,
            },
            "name",
        )
        if file_id:
            attachments.append({"fid": file_id})

    prefix = settings.email_subject_prefix or "[AMF Operations]"
    period_kind = "Semester" if doc.period_type == "Semester" else "Monthly"
    period_label = get_report_period_label(doc)
    subject = "{0} {1} KPI Report - {2}".format(
        prefix,
        period_kind,
        period_label,
    )
    message = """
        <p>The {period_kind_lower} operations KPI report for <strong>{period}</strong> is complete.</p>
        <p>
            OTIF: <strong>{otif:.1f}%</strong><br>
            Strict OTIF: <strong>{strict:.1f}%</strong><br>
            Machining scrap: <strong>{scrap:.1f}%</strong><br>
            Purchase price ratio: <strong>{price:.1f}%</strong>
        </p>
        <p>The English and French reports are attached according to the configured formats.</p>
    """.format(
        period_kind_lower=period_kind.lower(),
        period=period_label,
        otif=flt(doc.otif_rate),
        strict=flt(doc.strict_otif_rate),
        scrap=flt(doc.machining_scrap_rate),
        price=flt(doc.purchase_price_ratio),
    )
    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        attachments=attachments,
        reference_doctype=REPORT_DOCTYPE,
        reference_name=doc.name,
    )
    doc.db_set("email_sent_on", now_datetime(), update_modified=True)
    return {"name": doc.name, "recipients": recipients, "queued": True}


def get_report_period_label(doc):
    if doc.period_type == "Semester":
        return "{0}-{1}".format(doc.reporting_year, doc.reporting_semester)
    return getdate(doc.reporting_month).strftime("%Y-%m")


def parse_recipients(value):
    return [
        recipient.strip()
        for recipient in re.split(r"[,;\n]+", value or "")
        if recipient.strip()
    ]


def kpi_assessment(value, target, higher_is_better=True):
    if higher_is_better:
        if value >= target:
            return "Green"
        if value >= target - 5:
            return "Amber"
        return "Red"
    if value <= target:
        return "Green"
    if value <= target + 3:
        return "Amber"
    return "Red"


def kpi_assessment_fr(value, target, higher_is_better=True):
    return {
        "Green": "Vert",
        "Amber": "Orange",
        "Red": "Rouge",
    }[kpi_assessment(value, target, higher_is_better)]


def percent(numerator, denominator, digits=1):
    return (
        round(100.0 * flt(numerator) / flt(denominator), digits)
        if denominator
        else 0.0
    )


def rounded(value, digits=2):
    return round(flt(value), digits)


def clean_text(value):
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", text).strip()


def md(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return str(value)
