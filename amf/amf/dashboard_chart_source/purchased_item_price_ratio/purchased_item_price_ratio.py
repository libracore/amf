from __future__ import unicode_literals

import math
from collections import OrderedDict

import frappe
from frappe import _
from frappe.core.page.dashboard.dashboard import cache_source
from frappe.utils import cint, flt, getdate, today

from amf.amf.dashboard_chart_source.otif_by_semester.otif_by_semester import (
    add_semesters,
    get_semester,
    get_semester_end,
    get_semester_label_from_parts,
    get_semester_start,
)


DEFAULT_SEMESTER_COUNT = 8
EXCLUDED_SUPPLIER = "AMF Medical"
EXCLUDED_COMPANY = "Advanced Microfluidics SA (OLD)"
EXCLUDED_ITEM_CODE_REGEX = "GX"
ANOMALY_SCORE_THRESHOLD = 3.5
IQR_ANOMALY_MULTIPLIER = 1.5
MIN_ANOMALY_SAMPLE_SIZE = 7
CHART_COLORS = ["orange"]


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None):
    chart = _get_chart(chart_name, chart)
    filters = normalize_filters(frappe.parse_json(chart.filters_json or "{}"))
    rows = get_purchased_item_price_ratio_by_semester(filters)

    return {
        "labels": [row["label"] for row in rows],
        "datasets": [
            {
                "name": _("Latest / Previous Purchase Price %"),
                "values": [row["ratio_percent"] for row in rows],
            }
        ],
        "colors": CHART_COLORS,
    }


def _get_chart(chart_name=None, chart=None):
    if chart_name:
        return frappe.get_doc("Dashboard Chart", chart_name)

    if hasattr(chart, "doctype"):
        return chart

    if isinstance(chart, dict):
        return frappe._dict(chart)

    return frappe._dict(frappe.parse_json(chart))


def normalize_filters(filters=None):
    filters = frappe._dict(filters or {})
    filters.semester_count = max(1, cint(filters.get("semester_count") or DEFAULT_SEMESTER_COUNT))
    filters.to_date = getdate(filters.get("to_date") or today())

    if filters.get("from_date"):
        filters.from_date = getdate(filters.from_date)
    else:
        year, semester = get_semester(filters.to_date)
        start_year, start_semester = add_semesters(year, semester, -(filters.semester_count - 1))
        filters.from_date = get_semester_start(start_year, start_semester)

    if filters.from_date > filters.to_date:
        frappe.throw(_("From Date cannot be after To Date"))

    return filters


def get_purchased_item_price_ratio_by_semester(filters=None):
    filters = normalize_filters(filters)
    buckets = get_empty_semester_buckets(filters.from_date, filters.to_date)
    previous_rate_by_item = {}

    for row in get_purchase_rows(filters):
        item_code = row.item_code
        purchase_date = getdate(row.posting_date)
        current_rate = flt(row.normalized_rate)
        previous_rate = previous_rate_by_item.get(item_code)

        if filters.from_date <= purchase_date <= filters.to_date and previous_rate and current_rate:
            label = get_semester_label_from_parts(*get_semester(purchase_date))
            if label in buckets:
                buckets[label]["item_ratios"][item_code] = current_rate / previous_rate

        previous_rate_by_item[item_code] = current_rate

    for bucket in buckets.values():
        ratio_values = list(bucket["item_ratios"].values())
        anomaly_decisions = get_anomaly_decisions(ratio_values)
        included_ratios = [
            decision["value"]
            for decision in anomaly_decisions
            if not decision["is_anomaly"]
        ]
        bucket["item_count"] = len(ratio_values)
        bucket["anomaly_count"] = len(ratio_values) - len(included_ratios)
        bucket["included_item_count"] = len(included_ratios)
        bucket["ratio"] = average(included_ratios)
        bucket["ratio_percent"] = round(bucket["ratio"] * 100.0, 1) if bucket["ratio"] else 0

    return list(buckets.values())


def get_empty_semester_buckets(from_date, to_date):
    buckets = OrderedDict()
    year, semester = get_semester(from_date)
    end_year, end_semester = get_semester(to_date)
    end_index = get_semester_index(end_year, end_semester)

    while get_semester_index(year, semester) <= end_index:
        label = get_semester_label_from_parts(year, semester)
        buckets[label] = {
            "label": label,
            "year": year,
            "semester": semester,
            "from_date": get_semester_start(year, semester),
            "to_date": get_semester_end(year, semester),
            "item_ratios": {},
            "item_count": 0,
            "anomaly_count": 0,
            "included_item_count": 0,
            "ratio": 0.0,
            "ratio_percent": 0.0,
        }
        year, semester = add_semesters(year, semester, 1)

    return buckets


def get_semester_index(year, semester):
    return (cint(year) * 2) + (cint(semester) - 1)


def get_purchase_rows(filters):
    conditions = [
        "pr.docstatus = 1",
        "IFNULL(pr.is_return, 0) = 0",
        "pr.posting_date <= %(to_date)s",
        "IFNULL(pri.item_code, '') != ''",
        "IFNULL(pri.qty, 0) > 0",
        "IFNULL(pri.conversion_factor, 0) > 0",
        "IFNULL(pr.supplier, '') != %(excluded_supplier)s",
        "IFNULL(pr.company, '') != %(excluded_company)s",
        "pri.item_code NOT RLIKE %(excluded_item_code_regex)s",
        """
        COALESCE(
            NULLIF(pri.base_net_rate, 0),
            NULLIF(pri.base_rate, 0),
            NULLIF(pri.net_rate, 0),
            NULLIF(pri.rate, 0),
            0
        ) > 0
        """,
    ]
    values = {
        "to_date": filters.to_date,
        "excluded_supplier": EXCLUDED_SUPPLIER,
        "excluded_company": EXCLUDED_COMPANY,
        "excluded_item_code_regex": EXCLUDED_ITEM_CODE_REGEX,
    }

    if filters.get("item_group"):
        conditions.append("item.item_group = %(item_group)s")
        values["item_group"] = filters.item_group

    if filters.get("item_code"):
        conditions.append("pri.item_code = %(item_code)s")
        values["item_code"] = filters.item_code

    if filters.get("supplier"):
        conditions.append("pr.supplier = %(supplier)s")
        values["supplier"] = filters.supplier

    return frappe.db.sql(
        """
        SELECT
            pri.item_code,
            pr.posting_date,
            pr.posting_time,
            pr.name AS purchase_receipt,
            pri.idx,
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
        WHERE {conditions}
        ORDER BY
            pri.item_code,
            pr.posting_date,
            pr.posting_time,
            pr.creation,
            pr.name,
            pri.idx
        """.format(conditions=" AND ".join(conditions)),
        values,
        as_dict=True,
    )


def get_anomaly_decisions(values):
    values = [flt(value) for value in values if flt(value) > 0]
    if len(values) < MIN_ANOMALY_SAMPLE_SIZE:
        return [
            {"value": value, "is_anomaly": False, "anomaly_score": 0.0}
            for value in values
        ]

    log_values = [math.log(value) for value in values]
    median_log_value = get_median(log_values)
    absolute_deviations = [
        abs(log_value - median_log_value)
        for log_value in log_values
    ]
    median_absolute_deviation = get_median(absolute_deviations)

    if median_absolute_deviation:
        return get_mad_anomaly_decisions(
            values,
            log_values,
            median_log_value,
            median_absolute_deviation,
        )

    return get_iqr_anomaly_decisions(values, log_values)


def get_mad_anomaly_decisions(values, log_values, median_log_value, median_absolute_deviation):
    decisions = []

    for value, log_value in zip(values, log_values):
        anomaly_score = 0.6745 * abs(log_value - median_log_value) / median_absolute_deviation
        decisions.append({
            "value": value,
            "is_anomaly": anomaly_score > ANOMALY_SCORE_THRESHOLD,
            "anomaly_score": anomaly_score,
        })

    return decisions


def get_iqr_anomaly_decisions(values, log_values):
    q1 = get_percentile(log_values, 0.25)
    q3 = get_percentile(log_values, 0.75)
    iqr = q3 - q1

    if not iqr:
        return [
            {"value": value, "is_anomaly": False, "anomaly_score": 0.0}
            for value in values
        ]

    lower_fence = q1 - (IQR_ANOMALY_MULTIPLIER * iqr)
    upper_fence = q3 + (IQR_ANOMALY_MULTIPLIER * iqr)
    decisions = []

    for value, log_value in zip(values, log_values):
        is_anomaly = log_value < lower_fence or log_value > upper_fence
        anomaly_score = 0.0
        if is_anomaly:
            anomaly_score = abs(log_value - get_median(log_values)) / iqr

        decisions.append({
            "value": value,
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score,
        })

    return decisions


def get_median(values):
    values = sorted(values)
    if not values:
        return 0.0

    middle_index = len(values) // 2
    if len(values) % 2:
        return values[middle_index]

    return (values[middle_index - 1] + values[middle_index]) / 2.0


def get_percentile(values, percentile):
    values = sorted(values)
    if not values:
        return 0.0

    position = (len(values) - 1) * percentile
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))

    if lower_index == upper_index:
        return values[lower_index]

    lower_weight = upper_index - position
    upper_weight = position - lower_index
    return (values[lower_index] * lower_weight) + (values[upper_index] * upper_weight)


def average(values):
    return sum(values) / len(values) if values else 0.0
