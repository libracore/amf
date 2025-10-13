# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
from collections import defaultdict, OrderedDict
from datetime import datetime, date
import frappe

def execute(filters=None):
    filters = filters or {}
    from_date, to_date = _get_date_range(filters)
    company = (filters.get("company") or "").strip()
    customer = (filters.get("customer") or "").strip()
    only_with_dn = int(filters.get("only_with_dn") or 0)

    # 1) Get submitted SOs within the window (using transaction_date to prefilter fast)
    sales_orders = _get_sales_orders(from_date, to_date, company, customer)

    if not sales_orders:
        return _empty_result()

    so_names = [x["name"] for x in sales_orders]

    # 2) Map: Sales Order -> real submit timestamp (from tabVersion docstatus transition)
    so_submit_ts_map = _get_submit_timestamps(so_names)

    # 3) Per-SO Delivery Note aggregates (first/last DN creation, DN count)
    dn_agg = _get_dn_aggregates(so_names)

    # 4) Build rows: compute lead times (days) from submit_ts -> first_dn_creation
    rows = []
    monthly_buckets = defaultdict(list)  # "YYYY-MM" -> [lead_time_days,...]

    for so in sales_orders:
        so_name = so["name"]
        submit_ts = so_submit_ts_map.get(so_name)

        # Fallback: if submit_ts is not found, approximate with transaction_date at 00:00
        # (Version rows might be missing after imports or heavy data cleaning)
        if not submit_ts:
            if so.get("transaction_date"):
                submit_ts = datetime.combine(so["transaction_date"], datetime.min.time())
            else:
                submit_ts = so.get("creation")  # worst-case fallback

        dn_info = dn_agg.get(so_name, {})
        first_dn_creation = dn_info.get("first_dn_creation")
        last_dn_creation = dn_info.get("last_dn_creation")
        dn_count = dn_info.get("dn_count", 0)

        lead_days_first = None
        lead_days_last = None

        if first_dn_creation:
            lead_days_first = (first_dn_creation - submit_ts).total_seconds() / 86400.0
        if last_dn_creation:
            lead_days_last = (last_dn_creation - submit_ts).total_seconds() / 86400.0

        # Respect "Only with DN" filter
        if only_with_dn and dn_count == 0:
            continue

        # Bucket for trend based on submission month
        month_key = (submit_ts.strftime("%Y-%m") if isinstance(submit_ts, datetime)
                     else str(so.get("transaction_date") or ""))[:7]
        if month_key and (lead_days_first is not None):
            monthly_buckets[month_key].append(lead_days_first)

        rows.append({
            "sales_order": so_name,
            "company": so.get("company"),
            "customer": so.get("customer"),
            "transaction_date": so.get("transaction_date"),
            "submitted_at": submit_ts,
            "first_dn_created_at": first_dn_creation,
            "last_dn_created_at": last_dn_creation,
            "dn_count": dn_count,
            "days_to_first_dn": _round_or_none(lead_days_first),
            "days_to_last_dn": _round_or_none(lead_days_last)
        })

    # 5) Columns
    columns = _get_columns()

    # 6) Chart: monthly average of days_to_first_dn (last 12 months)
    chart = _build_monthly_chart(monthly_buckets, from_date, to_date)

    # 7) Report summary (overall avg, p90, trend last 3 months vs prior 3)
    report_summary = _build_report_summary(rows, chart)

    # Sort rows by submission time asc by default
    rows.sort(key=lambda r: (r["submitted_at"] or datetime.min))

    return columns, rows, None, chart, report_summary


# ------------------------
# Helpers
# ------------------------

def _get_date_range(filters):
    """Return (from_date, to_date) as date objects with defaults: last 365 days."""
    to_date = filters.get("to_date")
    from_date = filters.get("from_date")

    today = frappe.utils.getdate()  # system tz date
    if not to_date:
        to_date = today
    else:
        to_date = frappe.utils.getdate(to_date)

    if not from_date:
        from_date = frappe.utils.add_days(to_date, -365)
    else:
        from_date = frappe.utils.getdate(from_date)

    return from_date, to_date


def _get_sales_orders(from_date, to_date, company, customer):
    """
    Pre-filter Sales Orders by:
      - docstatus = 1 (submitted)
      - transaction_date within [from_date, to_date]
      - optional Company/Customer
    Returns minimal fields for downstream joins.
    """
    conditions = [
        "so.docstatus = 1",
        "so.transaction_date >= %s",
        "so.transaction_date <= %s"
    ]
    params = [from_date, to_date]

    if company:
        conditions.append("so.company = %s")
        params.append(company)

    if customer:
        conditions.append("so.customer = %s")
        params.append(customer)

    sql = f"""
        SELECT
            so.name,
            so.company,
            so.customer,
            so.transaction_date,
            so.creation
        FROM `tabSales Order` so
        WHERE {" AND ".join(conditions)}
    """
    return frappe.db.sql(sql, params, as_dict=True)


def _get_submit_timestamps(so_names):
    """
    Find the exact submit timestamp per SO by parsing Version rows
    where docstatus transitioned to 1.
    Version.data JSON in v12 contains a "changed" array like:
      [["docstatus", 0, 1], ["status", "Draft", "To Deliver"] ...]
    Returns: dict {so_name: datetime_of_submit}
    """
    if not so_names:
        return {}

    # break into chunks for large IN clauses
    chunk_size = 500
    out = {}
    for i in range(0, len(so_names), chunk_size):
        chunk = so_names[i:i+chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        version_rows = frappe.db.sql(f"""
            SELECT docname, creation, data
            FROM `tabVersion`
            WHERE ref_doctype = 'Sales Order'
              AND docname IN ({placeholders})
            ORDER BY creation ASC
        """, chunk, as_dict=True)

        for v in version_rows:
            try:
                payload = json.loads(v.get("data") or "{}")
            except Exception:
                payload = {}

            changed = payload.get("changed") or []
            # Detect a transition to docstatus=1
            # changed entries are [fieldname, old_value, new_value]
            for entry in changed:
                if isinstance(entry, list) and len(entry) >= 3:
                    if entry[0] == "docstatus" and str(entry[2]) == "1":
                        so = v["docname"]
                        # keep the earliest creation that shows docstatus->1
                        if so not in out:
                            out[so] = v["creation"]
                        break

    # Convert to python datetimes
    out = {k: _as_datetime(v) for k, v in out.items() if v}
    return out


def _get_dn_aggregates(so_names):
    """
    For the candidate SOs, compute:
      - first_dn_creation
      - last_dn_creation
      - dn_count (distinct)
    Uses only submitted DNs (docstatus=1).
    """
    if not so_names:
        return {}

    chunk_size = 500
    result = {}
    for i in range(0, len(so_names), chunk_size):
        chunk = so_names[i:i+chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))

        # We rely on Delivery Note Item.against_sales_order
        sql = f"""
            SELECT
                dni.against_sales_order AS so_name,
                MIN(dn.creation) AS first_dn_creation,
                MAX(dn.creation) AS last_dn_creation,
                COUNT(DISTINCT dn.name) AS dn_count
            FROM `tabDelivery Note` dn
            INNER JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
            WHERE dn.docstatus = 1
              AND IFNULL(dni.against_sales_order, '') != ''
              AND dni.against_sales_order IN ({placeholders})
            GROUP BY dni.against_sales_order
        """
        for row in frappe.db.sql(sql, chunk, as_dict=True):
            result[row["so_name"]] = {
                "first_dn_creation": _as_datetime(row.get("first_dn_creation")),
                "last_dn_creation": _as_datetime(row.get("last_dn_creation")),
                "dn_count": int(row.get("dn_count") or 0)
            }
    return result


def _build_monthly_chart(buckets, from_date, to_date):
    """
    Build a 12-month line chart of monthly average lead time.
    Labels are months from from_date..to_date (inclusive) in YYYY-MM.
    """
    # Normalize to YYYY-MM list for the interval
    months = _month_range(from_date, to_date)
    labels = []
    data = []

    for m in months:
        labels.append(m)
        vals = buckets.get(m, [])
        if vals:
            avg = sum(vals) / float(len(vals))
            data.append(round(avg, 2))
        else:
            data.append(None)  # gaps render cleanly in Frappe charts

    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": "Avg days to first DN",
                    "values": data
                }
            ]
        },
        "type": "line"
    }
    return chart


def _build_report_summary(rows, chart):
    """
    Compute overall average, p90, and a simple trend:
    compare last 3 months average to prior 3 months average.
    """
    lead_vals = [r["days_to_first_dn"] for r in rows if r["days_to_first_dn"] is not None]
    if not lead_vals:
        return []

    lead_vals_sorted = sorted(lead_vals)
    n = len(lead_vals_sorted)
    p90 = lead_vals_sorted[int(0.90 * (n - 1))]

    overall_avg = round(sum(lead_vals_sorted) / float(n), 2)

    # Trend: last 3 months vs prior 3 months from chart data
    labels = chart.get("data", {}).get("labels", [])
    values = chart.get("data", {}).get("datasets", [{}])[0].get("values", [])

    last3 = [v for v in values[-3:] if isinstance(v, (int, float))]
    prev3 = [v for v in values[-6:-3] if isinstance(v, (int, float))]

    trend_txt = "n/a"
    if last3 and prev3:
        last_avg = sum(last3) / len(last3)
        prev_avg = sum(prev3) / len(prev3)
        if prev_avg != 0:
            change = ((last_avg - prev_avg) / prev_avg) * 100.0
            arrow = "↓" if change < 0 else "↑"
            trend_txt = f"{arrow} {round(change, 1)}% (last 3 vs prior 3)"
        else:
            trend_txt = "n/a"

    return [
        {"value": overall_avg, "indicator": "Green" if overall_avg <= p90 else "Blue",
         "label": "Average days to first DN"},
        {"value": round(p90, 2), "indicator": "Orange", "label": "P90 (days)"},
        {"value": trend_txt, "indicator": "Blue", "label": "Trend"}
    ]


def _get_columns():
    return [
        {"fieldname": "sales_order", "label": "Sales Order", "fieldtype": "Link", "options": "Sales Order", "width": 180},
        {"fieldname": "company", "label": "Company", "fieldtype": "Link", "options": "Company", "width": 130},
        {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "width": 180},
        {"fieldname": "transaction_date", "label": "SO Date", "fieldtype": "Date", "width": 110},
        {"fieldname": "submitted_at", "label": "Submitted At", "fieldtype": "Datetime", "width": 170},
        {"fieldname": "first_dn_created_at", "label": "First DN Created At", "fieldtype": "Datetime", "width": 170},
        {"fieldname": "last_dn_created_at", "label": "Last DN Created At", "fieldtype": "Datetime", "width": 170},
        {"fieldname": "dn_count", "label": "# DNs", "fieldtype": "Int", "width": 70},
        {"fieldname": "days_to_first_dn", "label": "Days to First DN", "fieldtype": "Float", "precision": 2, "width": 140},
        {"fieldname": "days_to_last_dn", "label": "Days to Last DN", "fieldtype": "Float", "precision": 2, "width": 140}
    ]


def _round_or_none(v):
    if v is None:
        return None
    return round(float(v), 2)


def _as_datetime(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    # Frappe returns str timestamps as '%Y-%m-%d %H:%M:%S.%f' or '%Y-%m-%d %H:%M:%S'
    try:
        return frappe.utils.get_datetime(val)
    except Exception:
        return None


def _month_range(from_date, to_date):
    """Return list of YYYY-MM month keys from from_date..to_date inclusive."""
    cur = date(from_date.year, from_date.month, 1)
    end = date(to_date.year, to_date.month, 1)
    out = []
    while cur <= end:
        out.append(cur.strftime("%Y-%m"))
        # next month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return out


def _empty_result():
    return _get_columns(), [], None, {"data": {"labels": [], "datasets": []}, "type": "line"}, []
