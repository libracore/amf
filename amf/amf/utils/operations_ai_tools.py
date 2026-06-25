# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

import frappe
from frappe import _
from frappe.utils import cint


REPORT_DOCTYPE = "Operations KPI Report"
MAX_TOOL_ROWS = 20


@frappe.whitelist()
def get_report_snapshot(report_name):
    data = _get_snapshot(report_name)
    return {
        "scope": data.get("scope", {}),
        "otif": _without_detail_lists(data.get("otif", {})),
        "machining": data.get("machining", {}),
        "shipping": _without_detail_lists(data.get("shipping", {})),
        "procurement": _without_detail_lists(data.get("procurement", {})),
    }


@frappe.whitelist()
def get_otif_customer_breakdown(report_name, limit=10):
    data = _get_snapshot(report_name)
    return {
        "top_customers": data.get("otif", {}).get("top_customers", [])[
            :_bounded_limit(limit)
        ],
        "top_item_groups": data.get("otif", {}).get("top_item_groups", [])[
            :_bounded_limit(limit)
        ],
    }


@frappe.whitelist()
def get_open_shortfalls(report_name, limit=20):
    data = _get_snapshot(report_name)
    return data.get("otif", {}).get("strict", {}).get("open_shortfalls", [])[
        :_bounded_limit(limit)
    ]


@frappe.whitelist()
def get_machining_scrap_details(report_name, limit=20):
    data = _get_snapshot(report_name)
    return data.get("machining", {}).get("current", {}).get(
        "top_scrap_items", []
    )[:_bounded_limit(limit)]


@frappe.whitelist()
def get_shipping_issue_details(report_name, limit=20):
    data = _get_snapshot(report_name)
    return data.get("shipping", {}).get("issues", [])[:_bounded_limit(limit)]


@frappe.whitelist()
def get_procurement_exceptions(report_name, exception_type="review", limit=20):
    data = _get_snapshot(report_name)
    key = "anomalies" if exception_type == "anomaly" else "review_items"
    return data.get("procurement", {}).get(key, [])[:_bounded_limit(limit)]


def _get_snapshot(report_name):
    doc = frappe.get_doc(REPORT_DOCTYPE, report_name)
    doc.check_permission("read")
    if not doc.kpi_data_json:
        frappe.throw(_("The report has no KPI snapshot."))
    return json.loads(doc.kpi_data_json)


def _without_detail_lists(values):
    return {
        key: value
        for key, value in values.items()
        if key
        not in (
            "issues",
            "review_items",
            "anomalies",
            "worst_deliveries",
            "open_shortfalls",
            "top_customers",
            "top_item_groups",
        )
    }


def _bounded_limit(limit):
    return min(max(cint(limit) or 10, 1), MAX_TOOL_ROWS)
