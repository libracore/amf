from __future__ import unicode_literals

import json

import frappe
from frappe.modules.import_file import import_file_by_path


DASHBOARD_NAME = "Supply Chain and Manufacturing"
OTIF_SOURCE_NAME = "OTIF by Semester"
MACHINING_SOURCE_NAME = "External vs Internal Machining"
VALVE_HEAD_SOURCE_NAME = "Valve Heads Manufactured vs Delivered"
PACKAGING_SHIPPING_ISSUES_SOURCE_NAME = "Packaging and Shipping Issues"
PURCHASE_PRICE_RATIO_SOURCE_NAME = "Purchased Item Price Ratio"
PURCHASING_AMOUNT_BY_CURRENCY_SOURCE_NAME = "Purchasing Amount by Currency"
STOCK_BALANCE_SOURCE_NAME = "Stock Balance by Semester"
LONGEST_MANUFACTURED_ITEMS_SOURCE_NAME = "Longest Manufactured Items"
PLANNING_SCRAP_RATE_SOURCE_NAME = "Planning Scrap Rate"
INVENTORY_TURNOVER_SOURCE_NAME = "Inventory Turnover Ratio"
CURRENT_OTIF_CHART = "OTIF Current Semester"
OTIF_EVOLUTION_CHART = "OTIF by Semester"
CURRENT_MACHINING_CHART = "External vs Internal Machining Current Semester"
MACHINING_EVOLUTION_CHART = "External vs Internal Machining by Semester"
CURRENT_VALVE_HEAD_CHART = "Valve Heads Manufactured vs Delivered Current Semester"
VALVE_HEAD_EVOLUTION_CHART = "Valve Heads Manufactured vs Delivered by Semester"
CURRENT_PACKAGING_SHIPPING_ISSUES_CHART = "Packaging and Shipping Issues Current Semester"
PACKAGING_SHIPPING_ISSUES_EVOLUTION_CHART = "Packaging and Shipping Issues by Semester"
CURRENT_PURCHASE_PRICE_RATIO_CHART = "Purchased Item Price Ratio Current Semester"
PURCHASE_PRICE_RATIO_EVOLUTION_CHART = "Purchased Item Price Ratio by Semester"
CURRENT_PURCHASING_AMOUNT_BY_CURRENCY_CHART = (
    "Stock Item Purchase Invoice Amount by Currency Current Semester"
)
PURCHASING_AMOUNT_BY_CURRENCY_EVOLUTION_CHART = (
    "Stock Item Purchase Invoice Amount by Currency by Semester"
)
CURRENT_NON_STOCK_PURCHASING_AMOUNT_BY_CURRENCY_CHART = (
    "Non-Stock Item Purchase Invoice Amount by Currency Current Semester"
)
NON_STOCK_PURCHASING_AMOUNT_BY_CURRENCY_EVOLUTION_CHART = (
    "Non-Stock Item Purchase Invoice Amount by Currency by Semester"
)
CURRENT_STOCK_BALANCE_CHART = "Stock Balance Amount and Quantity Current Semester"
STOCK_BALANCE_EVOLUTION_CHART = "Stock Balance Amount and Quantity by Semester"
LONGEST_MANUFACTURED_ITEMS_CHART = "Longest Manufactured Items Current Semester"
CURRENT_PLANNING_SCRAP_RATE_CHART = "Planning Scrap Rate Current Semester"
PLANNING_SCRAP_RATE_EVOLUTION_CHART = "Planning Scrap Rate by Semester"
CURRENT_INVENTORY_TURNOVER_CHART = "Inventory Turnover by Product Range Current Semester"
INVENTORY_TURNOVER_EVOLUTION_CHART = "Inventory Turnover by Product Range by Semester"
LEGACY_PACKAGING_SHIPPING_ISSUES_SOURCE_NAME = "Packaging & Shipping Issues"
LEGACY_PACKAGING_SHIPPING_ISSUES_CHARTS = (
    "Packaging & Shipping Issues Current Semester",
    "Packaging & Shipping Issues by Semester",
)
LEGACY_PURCHASING_AMOUNT_BY_CURRENCY_CHARTS = (
    "Purchasing Amount by Currency Current Semester",
    "Purchasing Amount by Currency by Semester",
)
LEGACY_STOCK_BALANCE_CHARTS = (
    "Stock Balance Amount Current Semester",
    "Stock Balance Amount by Semester",
    "Stock Balance Quantity Current Semester",
    "Stock Balance Quantity by Semester",
)
LEGACY_INVENTORY_TURNOVER_CHARTS = (
    "Inventory Turnover Current Semester",
    "Inventory Turnover by Semester",
)


def sync_supply_chain_manufacturing_dashboard():
    ensure_dashboard_chart_source(OTIF_SOURCE_NAME, "otif_by_semester")
    ensure_dashboard_chart_source(MACHINING_SOURCE_NAME, "external_vs_internal_machining")
    ensure_dashboard_chart_source(
        VALVE_HEAD_SOURCE_NAME,
        "valve_heads_manufactured_vs_delivered",
    )
    ensure_dashboard_chart_source(
        PACKAGING_SHIPPING_ISSUES_SOURCE_NAME,
        "packaging_and_shipping_issues",
    )
    ensure_dashboard_chart_source(
        PURCHASE_PRICE_RATIO_SOURCE_NAME,
        "purchased_item_price_ratio",
    )
    ensure_dashboard_chart_source(
        PURCHASING_AMOUNT_BY_CURRENCY_SOURCE_NAME,
        "purchasing_amount_by_currency",
    )
    ensure_dashboard_chart_source(
        STOCK_BALANCE_SOURCE_NAME,
        "stock_balance_by_semester",
    )
    ensure_dashboard_chart_source(
        LONGEST_MANUFACTURED_ITEMS_SOURCE_NAME,
        "longest_manufactured_items",
    )
    ensure_dashboard_chart_source(
        PLANNING_SCRAP_RATE_SOURCE_NAME,
        "planning_scrap_rate",
    )
    ensure_dashboard_chart_source(
        INVENTORY_TURNOVER_SOURCE_NAME,
        "inventory_turnover_ratio",
    )
    ensure_dashboard_chart(
        CURRENT_OTIF_CHART,
        OTIF_SOURCE_NAME,
        {"semester_count": 1, "include_rd": 0},
        width="Half",
    )
    ensure_dashboard_chart(
        OTIF_EVOLUTION_CHART,
        OTIF_SOURCE_NAME,
        {"semester_count": 8, "include_rd": 0},
        width="Half",
    )
    ensure_dashboard_chart(
        CURRENT_MACHINING_CHART,
        MACHINING_SOURCE_NAME,
        {"semester_count": 1},
        width="Half",
    )
    ensure_dashboard_chart(
        MACHINING_EVOLUTION_CHART,
        MACHINING_SOURCE_NAME,
        {"semester_count": 8},
        width="Half",
    )
    ensure_dashboard_chart(
        CURRENT_VALVE_HEAD_CHART,
        VALVE_HEAD_SOURCE_NAME,
        {"semester_count": 1},
        width="Half",
    )
    ensure_dashboard_chart(
        VALVE_HEAD_EVOLUTION_CHART,
        VALVE_HEAD_SOURCE_NAME,
        {"semester_count": 8},
        width="Half",
    )
    ensure_dashboard_chart(
        CURRENT_PACKAGING_SHIPPING_ISSUES_CHART,
        PACKAGING_SHIPPING_ISSUES_SOURCE_NAME,
        {"semester_count": 1},
        width="Half",
    )
    ensure_dashboard_chart(
        PACKAGING_SHIPPING_ISSUES_EVOLUTION_CHART,
        PACKAGING_SHIPPING_ISSUES_SOURCE_NAME,
        {"semester_count": 8},
        width="Half",
    )
    ensure_dashboard_chart(
        CURRENT_PURCHASE_PRICE_RATIO_CHART,
        PURCHASE_PRICE_RATIO_SOURCE_NAME,
        {"semester_count": 1},
        width="Half",
    )
    ensure_dashboard_chart(
        PURCHASE_PRICE_RATIO_EVOLUTION_CHART,
        PURCHASE_PRICE_RATIO_SOURCE_NAME,
        {"semester_count": 8},
        width="Half",
    )
    ensure_dashboard_chart(
        CURRENT_PURCHASING_AMOUNT_BY_CURRENCY_CHART,
        PURCHASING_AMOUNT_BY_CURRENCY_SOURCE_NAME,
        {"semester_count": 1, "company": "Advanced Microfluidics SA", "item_scope": "stock"},
        width="Half",
        chart_display_type="Bar",
        filter_overrides={"item_scope": "stock"},
    )
    ensure_dashboard_chart(
        PURCHASING_AMOUNT_BY_CURRENCY_EVOLUTION_CHART,
        PURCHASING_AMOUNT_BY_CURRENCY_SOURCE_NAME,
        {"semester_count": 8, "company": "Advanced Microfluidics SA", "item_scope": "stock"},
        width="Half",
        filter_overrides={"item_scope": "stock"},
    )
    ensure_dashboard_chart(
        CURRENT_NON_STOCK_PURCHASING_AMOUNT_BY_CURRENCY_CHART,
        PURCHASING_AMOUNT_BY_CURRENCY_SOURCE_NAME,
        {"semester_count": 1, "company": "Advanced Microfluidics SA", "item_scope": "non_stock"},
        width="Half",
        chart_display_type="Bar",
    )
    ensure_dashboard_chart(
        NON_STOCK_PURCHASING_AMOUNT_BY_CURRENCY_EVOLUTION_CHART,
        PURCHASING_AMOUNT_BY_CURRENCY_SOURCE_NAME,
        {"semester_count": 8, "company": "Advanced Microfluidics SA", "item_scope": "non_stock"},
        width="Half",
    )
    ensure_dashboard_chart(
        CURRENT_STOCK_BALANCE_CHART,
        STOCK_BALANCE_SOURCE_NAME,
        {"semester_count": 1, "mode": "combined", "company": "Advanced Microfluidics SA"},
        width="Half",
        chart_display_type="Bar",
    )
    ensure_dashboard_chart(
        STOCK_BALANCE_EVOLUTION_CHART,
        STOCK_BALANCE_SOURCE_NAME,
        {"semester_count": 8, "mode": "combined", "company": "Advanced Microfluidics SA"},
        width="Half",
    )
    ensure_dashboard_chart(
        LONGEST_MANUFACTURED_ITEMS_CHART,
        LONGEST_MANUFACTURED_ITEMS_SOURCE_NAME,
        {"semester_count": 1, "limit": 20},
        width="Full",
        chart_display_type="Bar",
        filter_overrides={"limit": 20},
    )
    ensure_dashboard_chart(
        CURRENT_PLANNING_SCRAP_RATE_CHART,
        PLANNING_SCRAP_RATE_SOURCE_NAME,
        {"semester_count": 1, "mode": "references", "limit": 20},
        width="Half",
        chart_display_type="Bar",
        filter_overrides={"limit": 20},
    )
    ensure_dashboard_chart(
        PLANNING_SCRAP_RATE_EVOLUTION_CHART,
        PLANNING_SCRAP_RATE_SOURCE_NAME,
        {"semester_count": 8, "mode": "semester"},
        width="Half",
    )
    ensure_dashboard_chart(
        CURRENT_INVENTORY_TURNOVER_CHART,
        INVENTORY_TURNOVER_SOURCE_NAME,
        {"semester_count": 1, "company": "Advanced Microfluidics SA"},
        width="Half",
        chart_display_type="Bar",
    )
    ensure_dashboard_chart(
        INVENTORY_TURNOVER_EVOLUTION_CHART,
        INVENTORY_TURNOVER_SOURCE_NAME,
        {"semester_count": 8, "company": "Advanced Microfluidics SA"},
        width="Half",
    )
    ensure_dashboard()
    remove_legacy_inventory_turnover_charts()
    remove_legacy_stock_balance_charts()
    remove_legacy_purchasing_amount_by_currency()
    remove_legacy_packaging_shipping_issues()


def ensure_dashboard_chart_source(source_name, source_folder):
    if frappe.db.exists("Dashboard Chart Source", source_name):
        return

    import_file_by_path(
        frappe.get_app_path(
            "amf",
            "amf",
            "dashboard_chart_source",
            source_folder,
            source_folder + ".json",
        ),
        force=True,
        for_sync=True,
    )


def ensure_dashboard_chart(
    chart_name,
    source_name,
    default_filters,
    width="Half",
    chart_display_type="Line",
    filter_overrides=None,
):
    required_values = {
        "doctype": "Dashboard Chart",
        "chart_name": chart_name,
        "chart_type": "Custom",
        "source": source_name,
        "width": width,
        "timeseries": 0,
    }

    if frappe.db.exists("Dashboard Chart", chart_name):
        chart = frappe.get_doc("Dashboard Chart", chart_name)
        changed = update_doc_values(chart, required_values, skip_fields={"doctype", "chart_name"})
        if not chart.get("filters_json"):
            chart.filters_json = json.dumps(default_filters)
            changed = True
        elif filter_overrides:
            filters = frappe.parse_json(chart.filters_json or "{}")
            filters_changed = update_filter_values(filters, filter_overrides)
            if filters_changed:
                chart.filters_json = json.dumps(filters)
                changed = True
        if not chart.get("type"):
            chart.type = chart_display_type
            changed = True
        if changed:
            chart.save(ignore_permissions=True)
    else:
        values = required_values.copy()
        values.update({
            "type": chart_display_type,
            "filters_json": json.dumps(default_filters),
        })
        frappe.get_doc(values).insert(ignore_permissions=True)

    frappe.cache().delete_key("chart-data:{0}".format(chart_name))


def ensure_dashboard():
    required_charts = [
        CURRENT_OTIF_CHART,
        OTIF_EVOLUTION_CHART,
        CURRENT_MACHINING_CHART,
        MACHINING_EVOLUTION_CHART,
        CURRENT_VALVE_HEAD_CHART,
        VALVE_HEAD_EVOLUTION_CHART,
        CURRENT_PACKAGING_SHIPPING_ISSUES_CHART,
        PACKAGING_SHIPPING_ISSUES_EVOLUTION_CHART,
        CURRENT_PURCHASE_PRICE_RATIO_CHART,
        PURCHASE_PRICE_RATIO_EVOLUTION_CHART,
        CURRENT_PURCHASING_AMOUNT_BY_CURRENCY_CHART,
        PURCHASING_AMOUNT_BY_CURRENCY_EVOLUTION_CHART,
        CURRENT_NON_STOCK_PURCHASING_AMOUNT_BY_CURRENCY_CHART,
        NON_STOCK_PURCHASING_AMOUNT_BY_CURRENCY_EVOLUTION_CHART,
        CURRENT_STOCK_BALANCE_CHART,
        STOCK_BALANCE_EVOLUTION_CHART,
        LONGEST_MANUFACTURED_ITEMS_CHART,
        CURRENT_PLANNING_SCRAP_RATE_CHART,
        PLANNING_SCRAP_RATE_EVOLUTION_CHART,
        CURRENT_INVENTORY_TURNOVER_CHART,
        INVENTORY_TURNOVER_EVOLUTION_CHART,
    ]

    if frappe.db.exists("Dashboard", DASHBOARD_NAME):
        dashboard = frappe.get_doc("Dashboard", DASHBOARD_NAME)
    else:
        dashboard = frappe.get_doc({
            "doctype": "Dashboard",
            "dashboard_name": DASHBOARD_NAME,
            "is_default": 0,
            "charts": [],
        })

    existing_charts = [row.chart for row in dashboard.get("charts") if row.chart]
    extra_charts = [chart for chart in existing_charts if chart not in required_charts]
    extra_charts = [chart for chart in extra_charts if chart not in LEGACY_PACKAGING_SHIPPING_ISSUES_CHARTS]
    extra_charts = [chart for chart in extra_charts if chart not in LEGACY_PURCHASING_AMOUNT_BY_CURRENCY_CHARTS]
    extra_charts = [chart for chart in extra_charts if chart not in LEGACY_STOCK_BALANCE_CHARTS]
    extra_charts = [chart for chart in extra_charts if chart not in LEGACY_INVENTORY_TURNOVER_CHARTS]
    dashboard.set("charts", [])
    for chart_name in required_charts + extra_charts:
        dashboard.append("charts", {"chart": chart_name})

    if dashboard.is_new():
        dashboard.insert(ignore_permissions=True)
    else:
        dashboard.save(ignore_permissions=True)


def update_doc_values(doc, values, skip_fields=None):
    skip_fields = skip_fields or set()
    changed = False

    for fieldname, value in values.items():
        if fieldname in skip_fields:
            continue
        if doc.get(fieldname) != value:
            doc.set(fieldname, value)
            changed = True

    return changed


def update_filter_values(filters, values):
    changed = False

    for fieldname, value in values.items():
        if filters.get(fieldname) != value:
            filters[fieldname] = value
            changed = True

    return changed


def remove_legacy_packaging_shipping_issues():
    for chart_name in LEGACY_PACKAGING_SHIPPING_ISSUES_CHARTS:
        if frappe.db.exists("Dashboard Chart", chart_name):
            frappe.delete_doc("Dashboard Chart", chart_name, ignore_permissions=True, force=True)
            frappe.cache().delete_key("chart-data:{0}".format(chart_name))

    if frappe.db.exists("Dashboard Chart Source", LEGACY_PACKAGING_SHIPPING_ISSUES_SOURCE_NAME):
        frappe.delete_doc(
            "Dashboard Chart Source",
            LEGACY_PACKAGING_SHIPPING_ISSUES_SOURCE_NAME,
            ignore_permissions=True,
            force=True,
        )


def remove_legacy_purchasing_amount_by_currency():
    for chart_name in LEGACY_PURCHASING_AMOUNT_BY_CURRENCY_CHARTS:
        if frappe.db.exists("Dashboard Chart", chart_name):
            frappe.delete_doc("Dashboard Chart", chart_name, ignore_permissions=True, force=True)
            frappe.cache().delete_key("chart-data:{0}".format(chart_name))


def remove_legacy_stock_balance_charts():
    for chart_name in LEGACY_STOCK_BALANCE_CHARTS:
        if frappe.db.exists("Dashboard Chart", chart_name):
            frappe.delete_doc("Dashboard Chart", chart_name, ignore_permissions=True, force=True)
            frappe.cache().delete_key("chart-data:{0}".format(chart_name))


def remove_legacy_inventory_turnover_charts():
    for chart_name in LEGACY_INVENTORY_TURNOVER_CHARTS:
        if frappe.db.exists("Dashboard Chart", chart_name):
            frappe.delete_doc("Dashboard Chart", chart_name, ignore_permissions=True, force=True)
            frappe.cache().delete_key("chart-data:{0}".format(chart_name))
