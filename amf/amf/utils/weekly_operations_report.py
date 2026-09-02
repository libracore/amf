# -*- coding: utf-8 -*-
"""Weekly 16:9 production and supply slide for AMF.

The scheduled report deliberately uses the same operational definitions as the
existing ERP reports.  In particular, delivered-line OTIF comes from the AMF
On Time Delivery KPI report, while all other sections are point-in-time views
of submitted ERP transactions as at the report date.
"""
from __future__ import unicode_literals

import calendar
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_months,
    cint,
    date_diff,
    flt,
    get_first_day,
    get_last_day,
    getdate,
    now_datetime,
    today,
)
from frappe.utils.file_manager import save_file

from amf.amf.report.on_time_delivery_kpis.on_time_delivery_kpis import (
    get_data as get_otif_rows,
)
from amf.amf.utils.sales_order_otif import get_skip_otif_kpi_condition


REPORT_DOCTYPE = "Weekly Operations Report"
SETTINGS_DOCTYPE = "Operations KPI Report Settings"
MACHINING_ITEM_PATTERN = r"^(10|20)[0-9]{4}$"
DEFAULT_QC_WAREHOUSE = "Quality Control - AMF21"
DEFAULT_OWNER = "ATR"
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_LOOKAHEAD_DAYS = 14
DEFAULT_QC_BACKLOG_DAYS = 7
DEFAULT_MAX_ITEMS = 6

FRENCH_MONTH_NAMES = (
    "",
    "Janv.",
    "Févr.",
    "Mars",
    "Avr.",
    "Mai",
    "Juin",
    "Juil.",
    "Août",
    "Sept.",
    "Oct.",
    "Nov.",
    "Déc.",
)


def sync_weekly_operations_report_settings():
    """Backfill only missing Single values; never overwrite administrator choices."""
    defaults = {
        "enable_weekly_operations_slide": 1,
        "weekly_report_owner": DEFAULT_OWNER,
        "weekly_qc_warehouse": DEFAULT_QC_WAREHOUSE,
        "weekly_lookback_days": DEFAULT_LOOKBACK_DAYS,
        "weekly_lookahead_days": DEFAULT_LOOKAHEAD_DAYS,
        "weekly_qc_backlog_days": DEFAULT_QC_BACKLOG_DAYS,
        "weekly_max_items": DEFAULT_MAX_ITEMS,
        "weekly_email_subject_prefix": "[AMF Operations]",
    }
    existing_fields = {
        row[0]
        for row in frappe.db.sql(
            "SELECT field FROM `tabSingles` WHERE doctype = %s",
            SETTINGS_DOCTYPE,
        )
    }
    missing = {
        fieldname: value
        for fieldname, value in defaults.items()
        if fieldname not in existing_fields
    }
    if missing:
        frappe.db.set_value(
            SETTINGS_DOCTYPE,
            SETTINGS_DOCTYPE,
            missing,
            update_modified=False,
        )
    return missing


def generate_current_weekly_report(force=False, source="Scheduled", report_date=None):
    """Create or refresh the report for the ISO week containing ``report_date``."""
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    if source == "Scheduled" and not cint(
        _setting(settings, "enable_weekly_operations_slide", 1)
    ):
        return {"skipped": True, "reason": "Weekly slide generation is disabled."}

    report_date = getdate(report_date or today())
    company = settings.company or frappe.defaults.get_global_default("company")
    if not company:
        frappe.throw(_("Configure a Company in Operations KPI Report Settings."))

    report = get_or_create_weekly_report(
        company=company,
        report_date=report_date,
        source=source,
        owner_initials=_setting(settings, "weekly_report_owner", DEFAULT_OWNER),
    )
    has_both_outputs = bool(report.output_file and report.get("output_png"))
    refresh_completed = (
        cint(force) or source == "Scheduled" or not has_both_outputs
    )
    if (
        report.status == "Completed"
        and not refresh_completed
    ):
        return {
            "name": report.name,
            "status": report.status,
            "file_url": report.output_file,
            "png_url": report.get("output_png"),
            "skipped": True,
        }

    return generate_weekly_report(
        report.name,
        force=refresh_completed,
    )


def get_or_create_weekly_report(company, report_date, source="Manual", owner_initials=None):
    report_date = getdate(report_date)
    iso_year, iso_week, _ = report_date.isocalendar()
    company_abbr = frappe.db.get_value("Company", company, "abbr") or "COMPANY"
    report_key = "OPS-WEEKLY-{0}-W{1:02d}-{2}".format(
        iso_year, iso_week, company_abbr
    )
    existing = frappe.db.get_value(REPORT_DOCTYPE, {"report_key": report_key}, "name")
    if existing:
        report = frappe.get_doc(REPORT_DOCTYPE, existing)
        updates = {}
        if getdate(report.report_date) != report_date:
            updates["report_date"] = report_date
        if report.source != source:
            updates["source"] = source
        if owner_initials and report.owner_initials != owner_initials:
            updates["owner_initials"] = owner_initials
        if updates:
            frappe.db.set_value(REPORT_DOCTYPE, report.name, updates, update_modified=False)
            report.reload()
        return report

    return frappe.get_doc(
        {
            "doctype": REPORT_DOCTYPE,
            "report_key": report_key,
            "report_date": report_date,
            "company": company,
            "owner_initials": owner_initials or DEFAULT_OWNER,
            "source": source,
            "status": "Draft",
        }
    ).insert(ignore_permissions=True)


def generate_weekly_report(report_name, force=False):
    """Collect live ERP data, render one slide as PDF and PNG, and optionally email it."""
    report = frappe.get_doc(REPORT_DOCTYPE, report_name)
    if report.status == "Completed" and not cint(force):
        return {
            "name": report.name,
            "status": report.status,
            "file_url": report.output_file,
            "png_url": report.get("output_png"),
            "skipped": True,
        }

    report.db_set("status", "Generating", update_modified=True)
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    try:
        data = collect_weekly_operations_data(
            report_date=report.report_date,
            company=report.company,
            owner_initials=report.owner_initials,
            settings=settings,
        )
        html = build_slide_html(data)
        pdf_content = render_slide_pdf(html)
        png_content = render_slide_png(pdf_content)
        filename_stem = "amf_ops_weekly_{0}_W{1:02d}".format(
            data["scope"]["iso_year"], data["scope"]["iso_week"]
        )

        _remove_previous_outputs(report)
        pdf_file = save_file(
            filename_stem + ".pdf",
            pdf_content,
            REPORT_DOCTYPE,
            report.name,
            is_private=1,
        )
        png_file = save_file(
            filename_stem + ".png",
            png_content,
            REPORT_DOCTYPE,
            report.name,
            is_private=1,
        )
        frappe.db.set_value(
            REPORT_DOCTYPE,
            report.name,
            {
                "status": "Completed",
                "generated_on": now_datetime(),
                "generated_by": frappe.session.user or "Administrator",
                "output_file": pdf_file.file_url,
                "output_png": png_file.file_url,
                "report_data_json": json.dumps(
                    data, default=str, indent=2, sort_keys=True, ensure_ascii=False
                ),
                "generation_log": "",
            },
            update_modified=True,
        )
        report.reload()

        return {
            "name": report.name,
            "status": report.status,
            "file_url": report.output_file,
            "png_url": report.output_png,
        }
    except Exception:
        error = frappe.get_traceback()
        frappe.db.set_value(
            REPORT_DOCTYPE,
            report.name,
            {"status": "Failed", "generation_log": error},
            update_modified=True,
        )
        frappe.log_error(error, "Weekly Operations Report {0}".format(report.name))
        raise


def collect_weekly_operations_data(
    report_date, company, owner_initials=None, settings=None
):
    """Return the deterministic snapshot used by both the PDF and tests."""
    report_date = getdate(report_date)
    settings = settings or frappe.get_single(SETTINGS_DOCTYPE)
    lookback_days = max(
        1, cint(_setting(settings, "weekly_lookback_days", DEFAULT_LOOKBACK_DAYS))
    )
    lookahead_days = max(
        1, cint(_setting(settings, "weekly_lookahead_days", DEFAULT_LOOKAHEAD_DAYS))
    )
    qc_backlog_days = max(
        1,
        cint(_setting(settings, "weekly_qc_backlog_days", DEFAULT_QC_BACKLOG_DAYS)),
    )
    max_items = max(
        3,
        min(8, cint(_setting(settings, "weekly_max_items", DEFAULT_MAX_ITEMS))),
    )
    qc_warehouse = _setting(
        settings, "weekly_qc_warehouse", DEFAULT_QC_WAREHOUSE
    )
    iso_year, iso_week, _ = report_date.isocalendar()

    delivery_performance = collect_delivery_performance(report_date)
    overdue_deliveries = collect_overdue_deliveries(report_date)
    machining = collect_machining_queue(
        report_date, lookahead_days, max_items=max_items
    )
    current_work_orders = collect_current_work_orders(
        report_date, lookahead_days, max_items=max_items
    )
    quality = collect_quality_control(
        report_date,
        qc_warehouse,
        qc_backlog_days=qc_backlog_days,
        max_items=max_items,
    )
    shipping = collect_delivery_notes(
        report_date,
        lookback_days=lookback_days,
        lookahead_days=lookahead_days,
        max_items=max_items,
    )
    signals = build_management_signals(
        report_date=report_date,
        overdue_deliveries=overdue_deliveries,
        machining=machining,
        current_work_orders=current_work_orders,
        quality=quality,
        shipping=shipping,
    )

    return {
        "scope": {
            "company": company,
            "report_date": report_date,
            "date_label": report_date.strftime("%d.%m.%y"),
            "departure_date_label": report_date.strftime("%d.%m"),
            "iso_year": iso_year,
            "iso_week": iso_week,
            "owner": owner_initials or DEFAULT_OWNER,
            "lookback_days": lookback_days,
            "lookahead_days": lookahead_days,
            "qc_warehouse": qc_warehouse,
            "generated_on": now_datetime(),
        },
        "delivery_performance": delivery_performance,
        "overdue_deliveries": overdue_deliveries,
        "machining": machining,
        "current_work_orders": current_work_orders,
        "quality": quality,
        "shipping": shipping,
        "signals": signals,
    }


def collect_delivery_performance(report_date):
    periods = get_reporting_months(report_date, count=3)
    output_rows = []
    otif_rows = []
    for period_start, period_end in periods:
        output = get_output_vs_plan(period_start, period_end)
        output_rows.append(
            {
                "month": FRENCH_MONTH_NAMES[period_start.month],
                "actual": output["actual"],
                "planned": output["planned"],
                "rate": output["rate"],
                "tone": _rate_tone(output["rate"], green=95, amber=80),
            }
        )
        rows = get_otif_rows(
            frappe._dict(
                {
                    "from_date": period_start,
                    "to_date": period_end,
                    "item_group": None,
                    "include_rd": 0,
                }
            )
        )
        on_time = sum(cint(row["0d"]) for row in rows)
        rate = round(on_time * 100.0 / len(rows), 1) if rows else 0.0
        otif_rows.append(
            {
                "month": "{0}. {1:02d}".format(
                    calendar.month_abbr[period_start.month], period_start.year % 100
                ),
                "on_time": on_time,
                "total": len(rows),
                "rate": rate,
                "tone": _rate_tone(rate, green=90, amber=60),
            }
        )

    return {
        "output_vs_plan": output_rows[-2:],
        "otif": otif_rows,
    }


def get_reporting_months(report_date, count=3):
    report_date = getdate(report_date)
    current_month = get_first_day(report_date)
    periods = []
    for offset in reversed(range(count)):
        period_start = get_first_day(add_months(current_month, -offset))
        period_end = min(getdate(get_last_day(period_start)), report_date)
        periods.append((getdate(period_start), getdate(period_end)))
    return periods


def get_output_vs_plan(period_start, cutoff_date):
    """Count due Sales Orders whose due lines were fully delivered by cutoff."""
    skip_condition = get_skip_otif_kpi_condition("so")
    if skip_condition:
        skip_condition = "AND {0}".format(skip_condition)

    result = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS planned,
            SUM(CASE WHEN due_lines = delivered_lines THEN 1 ELSE 0 END) AS actual
        FROM (
            SELECT
                so.name,
                COUNT(soi.name) AS due_lines,
                SUM(
                    CASE WHEN IFNULL(delivered.delivered_qty, 0) + 0.000001 >=
                        COALESCE(
                            NULLIF(soi.stock_qty, 0),
                            soi.qty * IFNULL(soi.conversion_factor, 1)
                        )
                    THEN 1 ELSE 0 END
                ) AS delivered_lines
            FROM `tabSales Order Item` soi
            INNER JOIN `tabSales Order` so ON so.name = soi.parent
            LEFT JOIN (
                SELECT
                    dni.so_detail,
                    SUM(
                        COALESCE(
                            NULLIF(dni.stock_qty, 0),
                            dni.qty * IFNULL(dni.conversion_factor, 1)
                        )
                    ) AS delivered_qty
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
                WHERE dn.docstatus = 1
                    AND IFNULL(dn.is_return, 0) = 0
                    AND dn.posting_date <= %(cutoff_date)s
                GROUP BY dni.so_detail
            ) delivered ON delivered.so_detail = soi.name
            WHERE so.docstatus = 1
                AND so.sales_order_type = 'Production'
                AND soi.delivery_date BETWEEN %(period_start)s AND %(cutoff_date)s
                AND soi.item_code NOT RLIKE '^Di-'
                AND soi.item_code NOT RLIKE '^ENC-'
                AND COALESCE(
                    NULLIF(soi.stock_qty, 0),
                    soi.qty * IFNULL(soi.conversion_factor, 1)
                ) > 0
                {skip_condition}
            GROUP BY so.name
        ) due_orders
        """.format(skip_condition=skip_condition),
        {"period_start": period_start, "cutoff_date": cutoff_date},
        as_dict=True,
    )[0]
    planned = cint(result.planned)
    actual = cint(result.actual)
    return {
        "planned": planned,
        "actual": actual,
        "rate": round(actual * 100.0 / planned, 1) if planned else 0.0,
    }


def collect_overdue_deliveries(report_date):
    skip_condition = get_skip_otif_kpi_condition("so")
    if skip_condition:
        skip_condition = "AND {0}".format(skip_condition)
    rows = frappe.db.sql(
        """
        SELECT
            detail.sales_order,
            detail.customer,
            MIN(detail.delivery_date) AS earliest_due_date,
            MAX(DATEDIFF(%(report_date)s, detail.delivery_date)) AS delay_days,
            COUNT(*) AS overdue_lines,
            SUM(detail.remaining_qty) AS remaining_qty
        FROM (
            SELECT
                so.name AS sales_order,
                so.customer_name AS customer,
                soi.delivery_date,
                GREATEST(
                    COALESCE(
                        NULLIF(soi.stock_qty, 0),
                        soi.qty * IFNULL(soi.conversion_factor, 1)
                    ) - IFNULL(delivered.delivered_qty, 0),
                    0
                ) AS remaining_qty
            FROM `tabSales Order Item` soi
            INNER JOIN `tabSales Order` so ON so.name = soi.parent
            LEFT JOIN (
                SELECT
                    dni.so_detail,
                    SUM(
                        COALESCE(
                            NULLIF(dni.stock_qty, 0),
                            dni.qty * IFNULL(dni.conversion_factor, 1)
                        )
                    ) AS delivered_qty
                FROM `tabDelivery Note Item` dni
                INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
                WHERE dn.docstatus = 1
                    AND IFNULL(dn.is_return, 0) = 0
                    AND dn.posting_date <= %(report_date)s
                GROUP BY dni.so_detail
            ) delivered ON delivered.so_detail = soi.name
            WHERE so.docstatus = 1
                AND so.status NOT IN ('Closed', 'Completed')
                AND soi.delivery_date < %(report_date)s
                AND soi.item_code NOT RLIKE '^Di-'
                AND soi.item_code NOT RLIKE '^ENC-'
                AND (
                    so.sales_order_type IS NULL
                    OR so.sales_order_type NOT IN ('R&D', 'Hybrid')
                )
                {skip_condition}
        ) detail
        WHERE detail.remaining_qty > 0.000001
        GROUP BY detail.sales_order, detail.customer
        ORDER BY delay_days DESC, remaining_qty DESC
        LIMIT 25
        """.format(skip_condition=skip_condition),
        {"report_date": report_date},
        as_dict=True,
    )
    return [
        {
            "sales_order": row.sales_order,
            "customer": _shorten(row.customer or row.sales_order, 36),
            "due_date": row.earliest_due_date,
            "delay_days": cint(row.delay_days),
            "overdue_lines": cint(row.overdue_lines),
            "remaining_qty": _rounded_qty(row.remaining_qty),
        }
        for row in rows
    ]


def collect_machining_queue(report_date, lookahead_days, max_items=DEFAULT_MAX_ITEMS):
    horizon = add_days(report_date, lookahead_days)
    planning_rows = frappe.db.sql(
        """
        SELECT
            p.name,
            p.item_code,
            COALESCE(NULLIF(p.item_name, ''), item.item_name) AS item_name,
            p.work_order,
            IFNULL(linked_wo.priority, 0) AS priority,
            p.machine,
            p.date_de_fin AS due_date,
            IFNULL(p.quantite_validee, 0) AS valid_qty,
            IFNULL(p.quantite_scrap, 0) AS scrap_qty
        FROM `tabPlanning` p
        LEFT JOIN `tabItem` item ON item.name = p.item_code
        LEFT JOIN `tabWork Order` linked_wo ON linked_wo.name = p.work_order
        WHERE p.docstatus = 0
            AND p.item_code REGEXP %(item_pattern)s
            AND DATE(COALESCE(p.date_de_fin, p.date_de_debut)) <= %(horizon)s
        ORDER BY
            CASE
                WHEN IFNULL(linked_wo.priority, 0) > 0
                THEN linked_wo.priority
                ELSE 999
            END,
            COALESCE(p.date_de_fin, p.date_de_debut),
            p.name
        LIMIT %(row_limit)s
        """,
        {
            "item_pattern": MACHINING_ITEM_PATTERN,
            "horizon": horizon,
            "row_limit": max_items * 2,
        },
        as_dict=True,
    )
    work_order_rows = _get_open_work_orders(
        report_date=report_date,
        horizon=horizon,
        machining=True,
        row_limit=max_items * 3,
    )

    items = []
    for row in planning_rows:
        due_date = getdate(row.due_date) if row.due_date else None
        items.append(
            {
                "kind": "Planning",
                "name": row.name,
                "item_code": row.item_code,
                "priority": cint(row.priority),
                "due_date": due_date,
                "overdue": bool(due_date and due_date < report_date),
                "primary": _shorten(
                    row.item_name or row.item_code or row.name, 34
                ),
                "secondary": "Planning {0}{1}{2}".format(
                    row.name,
                    " · {0}".format(row.machine) if row.machine else "",
                    " · P{0}".format(cint(row.priority))
                    if cint(row.priority) > 0
                    else "",
                ),
            }
        )
    items.extend(_format_work_order_rows(work_order_rows, report_date))
    for row in items:
        if row["kind"] == "Work Order" and cint(row.get("priority")) > 0:
            row["secondary"] += " · P{0}".format(cint(row["priority"]))
    items.sort(key=_priority_date_sort_key)
    overdue_count = sum(1 for row in items if row["overdue"])
    return {
        "items": items[:max_items],
        "total": len(items),
        "overdue_count": overdue_count,
    }


def collect_current_work_orders(
    report_date, lookahead_days, max_items=DEFAULT_MAX_ITEMS
):
    rows = _get_open_work_orders(
        report_date=report_date,
        horizon=add_days(report_date, lookahead_days),
        machining=False,
        sales_order_linked=True,
        row_limit=max_items * 4,
    )
    items = _format_work_order_rows(
        rows, report_date, include_sales_order=True
    )
    items.sort(key=_date_sort_key)
    return {
        "items": items[:max_items],
        "total": len(items),
        "overdue_count": sum(1 for row in items if row["overdue"]),
    }


def _get_open_work_orders(
    report_date,
    horizon,
    machining,
    row_limit,
    sales_order_linked=False,
):
    item_condition = (
        "wo.production_item REGEXP %(item_pattern)s"
        if machining
        else "wo.production_item NOT REGEXP %(item_pattern)s"
    )
    document_condition = (
        "(wo.docstatus = 0 OR (wo.docstatus = 1 AND wo.status IN ('Not Started', 'In Process')))"
        if machining
        else "wo.docstatus = 1 AND wo.status IN ('Not Started', 'In Process')"
    )
    sales_order_condition = (
        "AND IFNULL(wo.sales_order, '') != ''" if sales_order_linked else ""
    )
    order_by = (
        "CASE WHEN IFNULL(wo.priority, 0) > 0 THEN wo.priority ELSE 999 END, due_date, wo.name"
        if machining
        else "due_date, wo.name"
    )
    return frappe.db.sql(
        """
        SELECT
            wo.name,
            wo.production_item,
            COALESCE(NULLIF(wo.item_name, ''), item.item_name) AS item_name,
            wo.status,
            wo.docstatus,
            wo.qty,
            wo.produced_qty,
            wo.sales_order,
            wo.priority,
            COALESCE(
                wo.expected_delivery_date_,
                wo.expected_delivery_date,
                wo.p_e_d,
                DATE(wo.planned_start_date)
            ) AS due_date
        FROM `tabWork Order` wo
        LEFT JOIN `tabItem` item ON item.name = wo.production_item
        WHERE {document_condition}
            AND {item_condition}
            {sales_order_condition}
            AND COALESCE(
                wo.expected_delivery_date_,
                wo.expected_delivery_date,
                wo.p_e_d,
                DATE(wo.planned_start_date)
            ) <= %(horizon)s
        ORDER BY {order_by}
        LIMIT %(row_limit)s
        """.format(
            document_condition=document_condition,
            item_condition=item_condition,
            sales_order_condition=sales_order_condition,
            order_by=order_by,
        ),
        {
            "report_date": report_date,
            "horizon": horizon,
            "item_pattern": MACHINING_ITEM_PATTERN,
            "row_limit": row_limit,
        },
        as_dict=True,
    )


def _format_work_order_rows(rows, report_date, include_sales_order=False):
    items = []
    for row in rows:
        due_date = getdate(row.due_date) if row.due_date else None
        remaining = max(flt(row.qty) - flt(row.produced_qty), 0)
        state = "Draft" if cint(row.docstatus) == 0 else row.status
        items.append(
            {
                "kind": "Work Order",
                "name": row.name,
                "status": state,
                "item_code": row.production_item,
                "priority": cint(row.priority),
                "sales_order": row.sales_order,
                "due_date": due_date,
                "overdue": bool(due_date and due_date < report_date),
                "primary": _shorten(
                    row.item_name or row.production_item or row.name, 34
                ),
                "secondary": " · ".join(
                    [row.name]
                    + ([row.sales_order] if include_sales_order and row.sales_order else [])
                    + [state, _format_qty(remaining)]
                ),
            }
        )
    items.sort(key=_operational_item_sort_key)
    return items


def collect_quality_control(
    report_date,
    warehouse,
    qc_backlog_days=DEFAULT_QC_BACKLOG_DAYS,
    max_items=DEFAULT_MAX_ITEMS,
):
    balances = frappe.db.sql(
        """
        SELECT
            sle.item_code,
            COALESCE(NULLIF(item.item_name, ''), sle.item_code) AS item_name,
            SUM(sle.actual_qty) AS actual_qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabItem` item ON item.name = sle.item_code
        WHERE sle.warehouse = %(warehouse)s
            AND sle.posting_date <= %(report_date)s
            AND sle.item_code NOT LIKE 'GX%%'
        GROUP BY sle.item_code, item.item_name
        HAVING SUM(sle.actual_qty) > 0.000001
        """,
        {"warehouse": warehouse, "report_date": report_date},
        as_dict=True,
    )
    items = []
    for balance in balances:
        receipt_rows = frappe.db.sql(
            """
            SELECT
                posting_date,
                voucher_type,
                voucher_no,
                batch_no
            FROM `tabStock Ledger Entry`
            WHERE warehouse = %(warehouse)s
                AND item_code = %(item_code)s
                AND posting_date <= %(report_date)s
                AND actual_qty > 0
                AND voucher_type = 'Purchase Receipt'
            ORDER BY posting_date DESC, posting_time DESC, creation DESC
            LIMIT 1
            """,
            {
                "warehouse": warehouse,
                "item_code": balance.item_code,
                "report_date": report_date,
            },
            as_dict=True,
        )
        if not receipt_rows:
            continue
        receipt = receipt_rows[0]
        source_label = "PREC"
        origin = _get_receipt_origin(receipt.voucher_type, receipt.voucher_no)
        inspection = _get_receipt_inspection(receipt.voucher_no, balance.item_code)
        source_date = getdate(receipt.posting_date)
        age_days = max(date_diff(report_date, source_date), 0)
        status = inspection.get("status") if inspection else ""
        if not status:
            status = "Awaiting QC"
        secondary_parts = [
            "{0} {1}".format(source_label, receipt.voucher_no),
            source_date.strftime("%d.%m"),
            "{0} pcs".format(_format_qty(balance.actual_qty)),
        ]
        if origin:
            secondary_parts.append(_shorten(origin, 22))
        items.append(
            {
                "item_code": balance.item_code,
                "primary": _shorten(balance.item_name or balance.item_code, 34),
                "secondary": " · ".join(secondary_parts),
                "actual_qty": _rounded_qty(balance.actual_qty),
                "source_type": receipt.voucher_type,
                "source_name": receipt.voucher_no,
                "source_date": source_date,
                "age_days": age_days,
                "inspection_status": status,
                "inspection_name": inspection.get("name") if inspection else None,
                "rejected": status == "Rejected",
                "backlog": age_days >= qc_backlog_days,
            }
        )

    items.sort(
        key=lambda row: (
            -(row["source_date"].toordinal() if row["source_date"] else 0),
            row["source_name"],
            row["item_code"],
        )
    )
    backlog_items = sorted(
        [row for row in items if row["backlog"]],
        key=lambda row: (
            -(row["source_date"].toordinal() if row["source_date"] else 0),
            -flt(row["actual_qty"]),
        ),
    )
    return {
        # QC descriptions often wrap onto a supplier/source line. Five entries
        # retain the source slide's readable type size without clipping.
        "items": items[: min(max_items, 5)],
        "total": len(items),
        "backlog_count": len(backlog_items),
        "backlog_items": backlog_items[:2],
        "rejected_count": sum(1 for row in items if row["rejected"]),
        "warehouse": warehouse,
    }


def _get_receipt_origin(voucher_type, voucher_no):
    if voucher_type == "Purchase Receipt":
        return frappe.db.get_value("Purchase Receipt", voucher_no, "supplier") or ""
    if voucher_type == "Stock Entry":
        values = frappe.db.get_value(
            "Stock Entry", voucher_no, ["work_order", "purpose"], as_dict=True
        )
        if not values:
            return ""
        return values.work_order or values.purpose or ""
    return ""


def _get_receipt_inspection(reference_name, item_code):
    rows = frappe.db.sql(
        """
        SELECT name, status, verified_by
        FROM `tabGlobal Quality Inspection`
        WHERE reference_name = %(reference_name)s
            AND (item_code = %(item_code)s OR IFNULL(item_code, '') = '')
        ORDER BY (item_code = %(item_code)s) DESC, report_date DESC, creation DESC
        LIMIT 1
        """,
        {"reference_name": reference_name, "item_code": item_code},
        as_dict=True,
    )
    return rows[0] if rows else frappe._dict()


def collect_delivery_notes(
    report_date,
    lookback_days=DEFAULT_LOOKBACK_DAYS,
    lookahead_days=DEFAULT_LOOKAHEAD_DAYS,
    max_items=DEFAULT_MAX_ITEMS,
):
    ready_rows = frappe.db.sql(
        """
        SELECT name, customer_name, posting_date, carrier
        FROM `tabDelivery Note`
        WHERE docstatus = 0
            AND IFNULL(is_return, 0) = 0
            AND name NOT LIKE 'DN-RET%%'
            AND posting_date BETWEEN %(oldest)s AND %(horizon)s
        ORDER BY posting_date, name
        LIMIT %(row_limit)s
        """,
        {
            "oldest": add_days(report_date, -30),
            "horizon": add_days(report_date, lookahead_days),
            "row_limit": max_items * 3,
        },
        as_dict=True,
    )
    shipped_rows = frappe.db.sql(
        """
        SELECT name, customer_name, posting_date, carrier, tracking_no
        FROM `tabDelivery Note`
        WHERE docstatus = 1
            AND IFNULL(is_return, 0) = 0
            AND IFNULL(TRIM(tracking_no), '') != ''
            AND posting_date BETWEEN %(period_start)s AND %(report_date)s
        ORDER BY posting_date DESC, name DESC
        LIMIT %(row_limit)s
        """,
        {
            "period_start": add_days(report_date, -lookback_days),
            "report_date": report_date,
            "row_limit": max_items,
        },
        as_dict=True,
    )

    ready = [
        {
            "name": row.name,
            "posting_date": getdate(row.posting_date),
            "overdue": getdate(row.posting_date) < report_date,
            "primary": _shorten(row.customer_name or row.name, 31),
            "secondary": "{0} · {1}{2}".format(
                row.name,
                getdate(row.posting_date).strftime("%d.%m"),
                " · {0}".format(row.carrier) if row.carrier else "",
            ),
        }
        for row in ready_rows
    ]
    shipped = [
        {
            "name": row.name,
            "posting_date": getdate(row.posting_date),
            "tracking_no": row.tracking_no,
            "primary": _shorten(row.customer_name or row.name, 31),
            "secondary": "{0} · {1} · {2}".format(
                row.name,
                _shorten(row.tracking_no, 21),
                row.carrier or "Carrier n/a",
            ),
        }
        for row in shipped_rows
    ]
    return {
        "ready": ready[:max_items],
        "ready_total": len(ready),
        "ready_overdue_count": sum(1 for row in ready if row["overdue"]),
        "shipped": shipped,
        "shipped_total": len(shipped),
    }


def build_management_signals(
    report_date,
    overdue_deliveries,
    machining,
    current_work_orders,
    quality,
    shipping,
):
    critical = []
    alerts = []
    decisions = []

    if overdue_deliveries:
        worst = overdue_deliveries[0]
        critical.append(
            "{0}: {1}d delivery delay".format(
                _shorten(worst["customer"], 27), worst["delay_days"]
            )
        )
        alerts.append(
            "{0} overdue SO{1} · {2} units open".format(
                len(overdue_deliveries),
                "" if len(overdue_deliveries) == 1 else "s",
                _format_qty(sum(flt(row["remaining_qty"]) for row in overdue_deliveries)),
            )
        )
        decisions.append(
            "Prioritise {0} ({1})".format(
                _shorten(worst["customer"], 29), worst["sales_order"]
            )
        )

    if quality["rejected_count"]:
        critical.append(
            "{0} rejected incoming QC lot{1}".format(
                quality["rejected_count"],
                "" if quality["rejected_count"] == 1 else "s",
            )
        )
    if quality["backlog_count"]:
        alerts.append(
            "{0} QC item{1} older than backlog threshold".format(
                quality["backlog_count"],
                "" if quality["backlog_count"] == 1 else "s",
            )
        )

    overdue_work_orders = (
        machining["overdue_count"] + current_work_orders["overdue_count"]
    )
    if overdue_work_orders:
        if len(critical) < 2:
            critical.append(
                "{0} overdue work order{1}".format(
                    overdue_work_orders, "" if overdue_work_orders == 1 else "s"
                )
            )
        alerts.append(
            "Release/replan {0} overdue WO{1}".format(
                overdue_work_orders, "" if overdue_work_orders == 1 else "s"
            )
        )

    if shipping["ready_total"]:
        decisions.append(
            "Release {0} draft DN{1} for shipment".format(
                shipping["ready_total"],
                "" if shipping["ready_total"] == 1 else "s",
            )
        )

    if not critical:
        critical.append("No critical risk detected")
    if not alerts:
        alerts.append("No operational blocker detected")
    if not decisions:
        decisions.append("No escalation required")
    return {
        "critical_risks": critical[:2],
        "alerts": alerts[:3],
        "decisions": decisions[:2],
    }


def build_slide_html(data):
    return frappe.render_template(
        "amf/templates/reports/weekly_operations_slide.html",
        {"report": data},
    )


def render_slide_pdf(html):
    """Render exactly one 16:9 page matching the 960 × 540 pt source slide."""
    import pdfkit

    wkhtmltopdf = shutil.which("wkhtmltopdf")
    if not wkhtmltopdf:
        wkhtmltopdf = next(
            (
                path
                for path in ("/usr/local/bin/wkhtmltopdf", "/usr/bin/wkhtmltopdf")
                if os.path.isfile(path) and os.access(path, os.X_OK)
            ),
            None,
        )
    if not wkhtmltopdf:
        frappe.throw(_("wkhtmltopdf is required to generate the weekly report."))

    options = {
        "page-width": "338.667mm",
        "page-height": "190.5mm",
        "margin-top": "0mm",
        "margin-bottom": "0mm",
        "margin-left": "0mm",
        "margin-right": "0mm",
        "disable-smart-shrinking": "",
        "print-media-type": None,
        "background": None,
        "images": None,
        "encoding": "UTF-8",
        "quiet": None,
    }
    configuration = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf)
    return pdfkit.from_string(
        html, False, options=options, configuration=configuration
    )


def render_slide_png(pdf_content):
    """Convert the first (and only) PDF page to a 1920 × 1080 PNG."""
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        pdftoppm = next(
            (
                path
                for path in ("/usr/local/bin/pdftoppm", "/usr/bin/pdftoppm")
                if os.path.isfile(path) and os.access(path, os.X_OK)
            ),
            None,
        )
    if not pdftoppm:
        frappe.throw(_("pdftoppm is required to generate the weekly report PNG."))

    with tempfile.TemporaryDirectory(prefix="amf-weekly-report-") as temp_dir:
        pdf_path = os.path.join(temp_dir, "slide.pdf")
        png_prefix = os.path.join(temp_dir, "slide")
        png_path = png_prefix + ".png"
        with open(pdf_path, "wb") as pdf_file:
            pdf_file.write(pdf_content)

        result = subprocess.run(
            [
                pdftoppm,
                "-f",
                "1",
                "-l",
                "1",
                "-singlefile",
                "-png",
                "-r",
                "144",
                pdf_path,
                png_prefix,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode:
            error = result.stderr.decode("utf-8", "replace").strip()
            frappe.throw(
                _("Could not generate the weekly report PNG: {0}").format(error)
            )
        with open(png_path, "rb") as png_file:
            return png_file.read()


def email_weekly_report(report_name, force=False):
    report = frappe.get_doc(REPORT_DOCTYPE, report_name)
    if report.email_sent_on and not cint(force):
        return {"name": report.name, "skipped": True, "reason": "Already sent."}
    if not report.output_file:
        frappe.throw(_("Generate the weekly report before sending it."))

    settings = frappe.get_single(SETTINGS_DOCTYPE)
    recipients = parse_recipients(
        _setting(settings, "weekly_email_recipients", "")
    )
    if not recipients:
        frappe.throw(_("No weekly report email recipient is configured."))
    file_id = frappe.db.get_value(
        "File",
        {
            "file_url": report.output_file,
            "attached_to_doctype": REPORT_DOCTYPE,
            "attached_to_name": report.name,
        },
        "name",
    )
    if not file_id:
        frappe.throw(_("The generated weekly report PDF could not be found."))

    prefix = _setting(settings, "weekly_email_subject_prefix", "[AMF Operations]")
    subject = "{0} Week {1:02d} — Production & Supply".format(
        prefix, cint(report.week_number)
    )
    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=(
            "<p>The AMF weekly Production &amp; Supply slide for "
            "<strong>week {0:02d}</strong> is attached.</p>"
            "<p>Report date: {1}</p>"
        ).format(cint(report.week_number), getdate(report.report_date).strftime("%d.%m.%Y")),
        attachments=[{"fid": file_id}],
        reference_doctype=REPORT_DOCTYPE,
        reference_name=report.name,
    )
    report.db_set("email_sent_on", now_datetime(), update_modified=True)
    return {"name": report.name, "recipients": recipients, "queued": True}


def parse_recipients(value):
    return [
        recipient.strip()
        for recipient in re.split(r"[,;\n]+", value or "")
        if recipient.strip()
    ]


def _remove_previous_outputs(report):
    for file_url in (report.output_file, report.get("output_png")):
        if not file_url:
            continue
        file_name = frappe.db.get_value(
            "File",
            {
                "file_url": file_url,
                "attached_to_doctype": REPORT_DOCTYPE,
                "attached_to_name": report.name,
            },
            "name",
        )
        if file_name:
            frappe.delete_doc("File", file_name, ignore_permissions=True)


def _setting(settings, fieldname, default=None):
    value = settings.get(fieldname) if settings else None
    return default if value in (None, "") else value


def _rate_tone(rate, green, amber):
    if rate >= green:
        return "green"
    if rate >= amber:
        return "amber"
    return "red"


def _shorten(value, limit):
    value = " ".join(str(value or "").split())
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 1)].rstrip() + "…"


def _rounded_qty(value):
    value = flt(value)
    if abs(value - round(value)) < 0.000001:
        return int(round(value))
    return round(value, 2)


def _format_qty(value):
    value = flt(value)
    if abs(value - round(value)) < 0.000001:
        return "{0:,}".format(int(round(value)))
    return "{0:,.2f}".format(value).rstrip("0").rstrip(".")


def _operational_item_sort_key(row):
    due_date = row.get("due_date") or date.max
    return (not row.get("overdue"), due_date, row.get("name") or "")


def _priority_date_sort_key(row):
    priority = cint(row.get("priority"))
    return (
        priority if priority > 0 else 999,
        row.get("due_date") or date.max,
        row.get("name") or "",
    )


def _date_sort_key(row):
    return (row.get("due_date") or date.max, row.get("name") or "")
