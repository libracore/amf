# import frappe
# import math
# import datetime
# import statistics
# import numpy as np
# import pandas as pd
# from frappe.core.doctype.communication.email import make
# from frappe.utils import date_diff

# # Constants
# SERVICE_LEVEL_Z = 1.64  # Z-score for 95% service level
# DEFAULT_LEAD_TIME = 15  # Default lead time in days
# DEFAULT_STD_DEV_LEAD_TIME = 10  # Default standard deviation of lead time
# TEST_MODE = 0

# @frappe.whitelist()
# def check_stock_levels(test_mode=TEST_MODE):
#     """
#     Main function to check stock levels, calculate safety stock and reorder levels,
#     and send email notifications for items requiring reordering.

#     Args:
#         test_mode (bool): Whether to run the function in test mode.
#     """
    
#     update_item_purchase_status()
    
#     items = fetch_items(test_mode)
#     items_to_email = []

#     for item in items:
#         if test_mode:
#             print(item)
#         if item["is_purchase_item"]:
#             avg_lead_time, std_dev_lead_time = calculate_dynamic_lead_time(item["name"])
#         else:
#             avg_lead_time = DEFAULT_LEAD_TIME
#             std_dev_lead_time = DEFAULT_STD_DEV_LEAD_TIME

#         monthly_outflows = calculate_monthly_outflows(item["name"])
#         avg_monthly_outflow = statistics.mean(monthly_outflows) if monthly_outflows else 0
#         annual_outflows = sum(monthly_outflows)
        
#         if test_mode:
#             print("avg_monthly_outflow:", avg_monthly_outflow)
#             print("avg_annual_outflow:", annual_outflows)

#         # Calculate safety stock and reorder levels
#         safety_stock, reorder_level = calculate_safety_stock_and_reorder_level(monthly_outflows, avg_lead_time, std_dev_lead_time)

#         update_item_fields(item["name"], avg_monthly_outflow, annual_outflows, safety_stock, reorder_level, avg_lead_time)

#         # Check stock levels across warehouses
#         highest_stock = get_highest_stock(item["name"])
#         if highest_stock < reorder_level:
#             frappe.db.set_value("Item", item["name"], "reorder", 1)
#             items_to_email.append(item)
#         else:
#             frappe.db.set_value("Item", item["name"], "reorder", 0)

#         frappe.db.commit()

#     # Send email notifications
#     if not TEST_MODE:
#         if items_to_email:
#             send_email_notifications(items_to_email)
#             print("Done sending emails.")
#         else:
#             print("No items need reordering. No email sent.")

#     print("Done checking stock levels.")


# def fetch_items(test_mode):
#     """
#     Fetches all stock items from the database.

#     Args:
#         test_mode (bool): Whether to fetch only test items.

#     Returns:
#         list: List of items.
#     """
#     filters = {'is_stock_item': 1, 'disabled': 0}
#     if test_mode:
#         filters["name"] = "RVM.3301"
#     return frappe.get_all(
#         "Item",
#         filters=filters,
#         fields=["name", "item_name", "item_group", "safety_stock", "reorder_level", "reorder", "average_monthly_outflow", "is_purchase_item"])


# def calculate_dynamic_lead_time(item_code):
#     """
#     Dynamically calculates lead time and its standard deviation for an item.

#     Args:
#         item_code (str): Item code.

#     Returns:
#         tuple: Average lead time, standard deviation of lead time.
#     """
#     query = """
#         SELECT
#             DATEDIFF(pri.creation, poi.schedule_date) AS lead_time
#         FROM
#             `tabPurchase Receipt Item` pri
#         INNER JOIN
#             `tabPurchase Order Item` poi ON poi.name = pri.purchase_order_item
#         WHERE
#             pri.docstatus = 1 AND poi.docstatus = 1 AND pri.item_code = %s
#     """
#     data = frappe.db.sql(query, item_code, as_dict=True)
#     lead_times = [entry["lead_time"] for entry in data if entry["lead_time"] > 0]

#     if not lead_times:
#         return 0, 0

#     if TEST_MODE:
#         print("lead_times:", lead_times)
#     return calculate_lead_time_statistics(lead_times)


# def calculate_monthly_outflows(item_code):
#     """
#     Calculates monthly outflows for the past 12 months for an item.

#     Args:
#         item_code (str): Item code.

#     Returns:
#         list: Monthly outflows.
#     """
#     monthly_outflows = []
#     current_date = datetime.datetime.now()

#     for month_offset in range(12):
#         target_date = current_date.replace(day=1) - datetime.timedelta(days=month_offset * 30)
#         target_month, target_year = target_date.month, target_date.year
#         if TEST_MODE:
#             print("target_date:",target_date,"/ target_month:",target_month," / target_year:",target_year)
#         monthly_outflow = frappe.db.sql(
#             """
#                 SELECT
#                     SUM(sle.actual_qty) AS total_outflow
#                 FROM
#                     `tabStock Ledger Entry` sle
#                 JOIN
#                     `tabItem` i ON sle.item_code = i.item_code
#                 LEFT JOIN
#                     `tabStock Entry` se ON sle.voucher_no = se.name
#                 WHERE
#                     sle.item_code = %s
#                     AND sle.actual_qty < 0
#                     AND (
#                             (sle.voucher_type = 'Stock Entry' AND se.purpose = 'Manufacture') OR
#                             (sle.voucher_type = 'Delivery Note')
#                         )
#                     AND MONTH(sle.posting_date) = %s
#                     AND YEAR(sle.posting_date) = %s
#                     AND i.disabled = 0
#             """,
#             (item_code, target_month, target_year))

#         monthly_outflows.append(-monthly_outflow[0][0] if monthly_outflow and monthly_outflow[0][0] else 0)

#     if TEST_MODE:
#         print("monthly:", monthly_outflows)
    
#     return monthly_outflows


# def calculate_safety_stock_and_reorder_level(monthly_outflows, avg_lead_time, std_dev_lead_time):
#     """
#     Calculates safety stock and reorder levels using demand and lead time statistics.

#     Args:
#         monthly_outflows (list): Monthly outflows.
#         avg_lead_time (float): Average lead time.
#         std_dev_lead_time (float): Standard deviation of lead time.

#     Returns:
#         tuple: Safety stock, reorder level.
#     """
#     if TEST_MODE:
#         print("monthly_outflows:", monthly_outflows, "avg_lead_time:", avg_lead_time, "std_dev_lead_time", std_dev_lead_time)
    
#     if not monthly_outflows:
#         return 0, 0

#     avg_demand = statistics.mean(monthly_outflows) / 30
#     std_dev_demand = statistics.stdev(monthly_outflows) / 30

#     safety_stock = SERVICE_LEVEL_Z * math.sqrt(
#         (avg_demand * std_dev_lead_time ** 2) +
#         (avg_lead_time * std_dev_demand ** 2)
#     )
#     reorder_level = safety_stock + avg_demand * avg_lead_time
    
#     if TEST_MODE:
#         print("safety_stock:", math.ceil(safety_stock), "reorder_level:", math.ceil(reorder_level))
        
#     return math.ceil(safety_stock), math.ceil(reorder_level)


# def update_item_fields(item_code, avg_monthly_outflow, annual_outflows, safety_stock, reorder_level, lead_time_days):
#     """
#     Updates the Item doctype with calculated fields.

#     Args:
#         item_code (str): Item code.
#         avg_monthly_outflow (float): Average monthly outflow.
#         annual_outflows (float): Annual outflows.
#         safety_stock (float): Safety stock.
#         reorder_level (float): Reorder level.
#         lead_time_days (float): Lead time in days.
#     """
#     frappe.db.set_value("Item", item_code, "average_monthly_outflow", math.ceil(avg_monthly_outflow))
#     frappe.db.set_value("Item", item_code, "annual_outflow", math.ceil(annual_outflows))
#     frappe.db.set_value("Item", item_code, "safety_stock", math.ceil(safety_stock))
#     frappe.db.set_value("Item", item_code, "reorder_level", math.ceil(reorder_level))
#     frappe.db.set_value("Item", item_code, "lead_time_days", lead_time_days)

# def get_highest_stock(item_code):
#     """
#     Gets the highest stock level across all warehouses for an item.

#     Args:
#         item_code (str): Item code.

#     Returns:
#         float: Highest stock level.
#     """
#     warehouses = frappe.get_all("Warehouse", filters={
#                                 "name": ["not in", ["AMF_OLD", "Scrap - AMF21", "R&D - AMF21"]]})
    
#     if TEST_MODE:
#         print("max_stock:", max(
#         frappe.db.get_value(
#             "Bin", {"item_code": item_code, "warehouse": wh["name"]}, "actual_qty") or 0
#         for wh in warehouses
#     ))
#     return max(
#         frappe.db.get_value(
#             "Bin", {"item_code": item_code, "warehouse": wh["name"]}, "actual_qty") or 0
#         for wh in warehouses
#     )


# def send_email_notifications(items):
#     """
#     Sends email notifications for items requiring reordering.

#     Args:
#         items (list): List of items.
#     """
#     email_content = build_email_content(items)
#     email_context = {
#         'recipients': 'alexandre.ringwald@amf.ch',
#         'content': email_content,
#         'subject': "Safety Stock Report on Items",
#         'communication_medium': 'Email',
#         'send_email': True,
#         'cc': 'alexandre.trachsel@amf.ch',
#     }
#     make(**email_context)
#     print("Email sent successfully.")


# def build_email_content(items):
#     """
#     Builds email content for reorder notifications.

#     Args:
#         items (list): List of items.

#     Returns:
#         str: HTML email content.
#     """
#     content = "<p>The following items have reached their reorder level:</p>"
#     content += "<table style='border-collapse: collapse; width: 100%;'>"
#     content += """
#         <tr style='background-color: #2b47d9; color: white;'>
#             <th>Item Code</th><th>Item Name</th><th>Current Stock</th>
#             <th>Monthly Outflow</th><th>Reorder Level</th><th>Safety Stock</th>
#         </tr>
#     """

#     for item in items:
#         content += f"""
#             <tr>
#                 <td>{item['name']}</td>
#                 <td>{item['item_name']}</td>
#                 <td>{item.get('highest_stock', 0)}</td>
#                 <td>{item.get('average_monthly_outflow', 0)}</td>
#                 <td>{item.get('reorder_level', 0)}</td>
#                 <td>{item.get('safety_stock', 0)}</td>
#             </tr>
#         """

#     content += "</table>"
#     return content


# def calculate_lead_time_statistics(lead_times):
#     """
#     Calculates lead time statistics including mean and standard deviation.

#     Args:
#         lead_times (list): List of lead times.

#     Returns:
#         tuple: Mean and standard deviation of lead times.
#     """
#     if not lead_times:
#         return 0, 0

#     # Calculate interquartile range (IQR) for outlier removal
#     q1, q3 = np.percentile(lead_times, [25, 75])
#     iqr = q3 - q1
#     filtered_lead_times = [
#         lt for lt in lead_times if q1 - 1.5 * iqr <= lt <= q3 + 1.5 * iqr
#     ]

#     # Handle cases with insufficient data
#     if len(filtered_lead_times) == 0:
#         return 0, 0  # No data after filtering
#     elif len(filtered_lead_times) == 1:
#         return filtered_lead_times[0], 0  # Single value, no variance

#     # Calculate and return mean and standard deviation
#     mean = statistics.mean(filtered_lead_times)
#     std_dev = statistics.stdev(filtered_lead_times)

#     if TEST_MODE:
#         print("mean_lead_times:", mean, "std_lead_times:", std_dev)

#     return mean, std_dev

# import frappe

# def update_item_purchase_status():
#     """
#     For all items that are not disabled, check if there is at least one Purchase Receipt Item
#     associated with the item (via the 'item_code' field). If none is found, update the
#     'is_purchase_item' field to 0.
#     """
#     # Retrieve all enabled items (assuming "disabled" is stored as 0 for enabled)
#     items = frappe.get_all("Item", filters={"disabled": 0}, fields=["name", "item_group"])

#     for item in items:
#         # Check if a Purchase Receipt Item exists for this item
#         purchase_exists = frappe.db.exists("Purchase Receipt Item", {"item_code": item.name})
#         if purchase_exists or item.item_group == "Raw Material":
#             frappe.db.set_value("Item", item.name, "is_purchase_item", 1)

#     # Optional: commit the changes if this script runs outside of a Frappe request context.
#     frappe.db.commit()

import statistics
import frappe
import math
from datetime import date, datetime, time, timedelta
from statistics import mean, stdev
from typing import Optional
import numpy as np
from frappe.core.doctype.communication.email import make
from frappe.utils import cstr, get_datetime
from amf.amf.utils.stock_entry import _get_or_create_log, update_log_entry
from amf.amf.utils.stock_entry import now_datetime

# Constants
SERVICE_LEVEL_Z = 1.64  # Z-score for 95% service level
DEFAULT_LEAD_TIME = 15  # days
DEFAULT_STD_DEV_LEAD_TIME = 15  # days
EXCLUDED_WAREHOUSES = ["AMF_OLD", "Scrap - AMF21", "R&D - AMF21"]
DEMAND_LOOKBACK_DAYS = 365
DEMAND_MONTH_DAYS = 30.0
QUERY_CHUNK_SIZE = 100
DEMAND_VOUCHER_TYPES = ("Delivery Note", "Sales Invoice")
DEMAND_STOCK_ENTRY_PURPOSES = (
    "Manufacture",
    "Material Consumption for Manufacture",
    "Material Issue",
    "Repack",
)
DEMAND_OUTLIER_MIN_NON_ZERO_DAYS = 8
LEAD_TIME_FALLBACK_STD_DEV_RATIO = 0.25
LEAD_TIME_SAMPLE_LIMIT = 50
MANUFACTURED_LEAD_TIME_HIGH_CONFIDENCE_SOURCES = (
    "planning_stock_entry",
    "planning_work_order",
    "timer",
    "work_order_actual",
)

doc = frappe._dict({
        "doctype": "Bin",
        "name": f"[{now_datetime()}] Auto Stock Level"
    })
log_id = _get_or_create_log(doc)

@frappe.whitelist()
def check_stock_levels(test_mode=0, dry_run=0, send_email=1, recompute_lead_time=0, verbose_log=0):
    """
    Main entry: calculate safety stocks, reorder levels and flag items for reorder.
    """
    test_mode = _is_truthy(test_mode)
    dry_run = _is_truthy(dry_run)
    send_email = _is_truthy(send_email)
    recompute_lead_time = _is_truthy(recompute_lead_time)
    verbose_log = _is_truthy(verbose_log)

    # Update purchase status - no doc context for top-level, so omitted logging
    
    
    # update_item_purchase_status(test_mode, log_id)

    items = _get_items(test_mode)
    demand_profiles = _get_demand_profiles_for_items(items)
    stock_positions = _get_stock_positions_for_items([item.name for item in items])
    to_notify = []
    result = {
        "dry_run": dry_run,
        "items_checked": len(items),
        "items_with_demand": 0,
        "items_to_reorder": 0,
        "items_updated": 0,
        "changes": [],
    }

    for item in items:
        # Initialize log for this Item
        
        _stock_check_log(verbose_log, f"[{now_datetime()}] check_stock_levels start for Item {item.name}")

        lead_time = _get_item_lead_time_stats(item, recompute_history=recompute_lead_time)
        _stock_check_log(
            verbose_log,
            f"[{now_datetime()}] Lead time stats: source={lead_time.source}, "
            f"avg_lt={lead_time.avg_days}, std_lt={lead_time.std_days}"
        )

        # Demand data
        demand = demand_profiles.get(item.name) or _empty_demand_profile()
        if demand.annual_outflow:
            result["items_with_demand"] += 1

        avg_monthly = math.ceil(demand.average_monthly_outflow)
        annual = math.ceil(demand.annual_outflow)
        _stock_check_log(
            verbose_log,
            f"[{now_datetime()}] Demand: avg_monthly={avg_monthly}, annual={annual}, "
            f"history_days={demand.history_days}, demand_days={demand.demand_days}"
        )

        # Safety stock & reorder level
        ss, ro = _compute_safety_and_reorder(
            demand.daily_outflows,
            lead_time.avg_days,
            lead_time.std_days,
        )
        _stock_check_log(verbose_log, f"[{now_datetime()}] Calculated safety_stock={ss}, reorder_level={ro}")

        # Stock evaluation
        stock_position = stock_positions.get(item.name) or _empty_stock_position()
        _stock_check_log(
            verbose_log,
            f"[{now_datetime()}] Stock position actual={stock_position.actual_qty}, "
            f"projected={stock_position.projected_qty}"
        )
        needs_reorder = stock_position.projected_qty < ro
        if needs_reorder:
            result["items_to_reorder"] += 1

        old_values = {
            "average_monthly_outflow": item.average_monthly_outflow,
            "annual_outflow": item.annual_outflow,
            "safety_stock": item.safety_stock,
            "reorder_level": item.reorder_level,
            "lead_time_days": item.lead_time_days,
            "reorder": item.reorder,
        }
        new_values = {
            "average_monthly_outflow": avg_monthly,
            "annual_outflow": annual,
            "safety_stock": ss,
            "reorder_level": ro,
            "lead_time_days": int(math.ceil(lead_time.avg_days or 0)),
            "reorder": int(needs_reorder),
        }

        if _item_stock_fields_changed(old_values, new_values):
            result["items_updated"] += 1
            result["changes"].append({
                "item_code": item.name,
                "old": old_values,
                "new": new_values,
                "lead_time_source": lead_time.source,
                "stock_actual_qty": stock_position.actual_qty,
                "stock_projected_qty": stock_position.projected_qty,
            })

        if not dry_run:
            _update_item(item.name, avg_monthly, annual, ss, ro, lead_time.avg_days)
            frappe.db.set_value("Item", item.name, "reorder", int(needs_reorder))
        _stock_check_log(verbose_log, f"[{now_datetime()}] Set reorder flag={int(needs_reorder)} for Item {item.name}")

        if needs_reorder:
            to_notify.append({
                "code": item.name,
                "name": item.item_name,
                "stock": stock_position.actual_qty,
                "avg_monthly": avg_monthly,
                "ro": ro,
                "ss": ss
            })
            _stock_check_log(verbose_log, f"[{now_datetime()}] Item {item.name} queued for notification")

    if not dry_run:
        frappe.db.commit()

    if to_notify and not test_mode and send_email and not dry_run:
        _stock_check_log(verbose_log, f"[{now_datetime()}] Sending notifications to recipients")
        _send_notifications(to_notify)
        _stock_check_log(verbose_log, f"[{now_datetime()}] Notifications sent")

    return result


def run_weekly_stock_level_update():
    """Scheduled weekly refresh of safety stock, reorder levels, and reorder flags."""
    return check_stock_levels(
        dry_run=0,
        send_email=0,
        recompute_lead_time=0,
        verbose_log=0,
    )


@frappe.whitelist()
def update_purchase_item_lead_times(dry_run=0, item_code=None):
    """
    Refresh Item.lead_time_days for purchase items from linked PO/PREC history only.

    This intentionally does not recalculate safety stock, reorder levels, reorder
    flags, or notifications. Items without reliable linked Purchase Order to
    Purchase Receipt history are left unchanged.
    """
    dry_run = cstr(dry_run).lower() in ("1", "true", "yes")
    filters = {
        "is_purchase_item": 1,
        "disabled": 0,
    }
    if item_code:
        filters["name"] = item_code

    items = frappe.get_all("Item", filters=filters, fields=["name", "lead_time_days"])
    result = {
        "dry_run": dry_run,
        "items_checked": len(items),
        "items_with_history": 0,
        "items_updated": 0,
        "items_unchanged": 0,
        "items_without_history": 0,
        "changes": [],
    }

    for item in items:
        update_result = _refresh_purchase_item_lead_time(item.name, dry_run=dry_run)
        _merge_lead_time_update_result(result, update_result)

    if not dry_run:
        frappe.db.commit()

    return result


@frappe.whitelist()
def update_manufactured_item_lead_times(dry_run=0, item_code=None):
    """
    Refresh Item.lead_time_days for manufactured items from production history only.

    The finish event is the submitted Manufacture Stock Entry. The start event is
    selected from the best available operational evidence: Planning, Timer
    Production, Work Order actual/custom fields, then Work Order planned/creation
    fallback. Safety stock, reorder levels, reorder flags, and notifications are
    not recalculated here.
    """
    dry_run = cstr(dry_run).lower() in ("1", "true", "yes")
    filters = {
        "is_stock_item": 1,
        "is_purchase_item": 0,
        "disabled": 0,
    }
    if item_code:
        filters["name"] = item_code

    items = frappe.get_all("Item", filters=filters, fields=["name", "lead_time_days"])
    result = {
        "dry_run": dry_run,
        "items_checked": len(items),
        "items_with_history": 0,
        "items_updated": 0,
        "items_unchanged": 0,
        "items_without_history": 0,
        "items_low_confidence_only": 0,
        "source_counts": {},
        "changes": [],
    }

    for item in items:
        update_result = _refresh_manufactured_item_lead_time(item.name, dry_run=dry_run)
        _merge_lead_time_update_result(result, update_result)

    if not dry_run:
        frappe.db.commit()

    return result


def update_purchase_item_lead_times_from_receipt(doc, method=None):
    """Refresh lead time for purchase items touched by a submitted Purchase Receipt."""
    item_codes = sorted({row.item_code for row in doc.get("items", []) if row.item_code})
    for item_code in item_codes:
        _refresh_purchase_item_lead_time(item_code, dry_run=False)


def update_manufactured_item_lead_time_from_stock_entry(doc, method=None):
    """Refresh lead time for the produced item when a Manufacture Stock Entry is submitted."""
    if doc.purpose != "Manufacture" or not doc.work_order:
        return

    item_code = frappe.db.get_value("Work Order", doc.work_order, "production_item")
    if item_code:
        _refresh_manufactured_item_lead_time(item_code, dry_run=False)


def _is_truthy(value):
    return cstr(value).lower() in ("1", "true", "yes", "y")


def _stock_check_log(enabled, message):
    if enabled:
        update_log_entry(log_id, message)


def _chunked(values, chunk_size=QUERY_CHUNK_SIZE):
    for index in range(0, len(values), chunk_size):
        yield values[index:index + chunk_size]


def _get_item_lead_time_stats(item, recompute_history=False):
    avg_lt = None
    std_lt = None
    source = None

    if recompute_history:
        if item.is_purchase_item:
            avg_lt, std_lt = _calc_lead_time(item.name)
            source = "purchase_history"
        else:
            avg_lt, std_lt, _context = _calc_manufactured_lead_time(item.name)
            source = "manufacturing_history"

    if avg_lt is None:
        avg_lt = float(item.lead_time_days or DEFAULT_LEAD_TIME)
        std_lt = _get_fallback_lead_time_std_dev(avg_lt)
        source = "item_lead_time" if item.lead_time_days else "default_lead_time"

    return frappe._dict({
        "avg_days": max(0.0, float(avg_lt or 0)),
        "std_days": max(0.0, float(std_lt or 0)),
        "source": source,
    })


def _get_fallback_lead_time_std_dev(avg_lead_time):
    avg_lead_time = float(avg_lead_time or 0)
    if avg_lead_time <= 0:
        return 0.0

    return max(1.0, min(DEFAULT_STD_DEV_LEAD_TIME, avg_lead_time * LEAD_TIME_FALLBACK_STD_DEV_RATIO))


def _item_stock_fields_changed(old_values, new_values):
    for fieldname, new_value in new_values.items():
        old_value = old_values.get(fieldname)
        if isinstance(new_value, float):
            if abs(float(old_value or 0) - new_value) > 0.0001:
                return True
        elif int(old_value or 0) != int(new_value or 0):
            return True

    return False


# --- Data Fetching Helpers ---
def _get_items(test_mode: bool):
    """
    Fetch stock items, excluding those with 'GX' in their name.
    In test mode, only return the specific test item.
    """
    fields = [
        "name",
        "item_name",
        "creation",
        "is_purchase_item",
        "lead_time_days",
        "average_monthly_outflow",
        "annual_outflow",
        "safety_stock",
        "reorder_level",
        "reorder",
    ]
    
    # 1. Simple equals filters
    base_filters = [
        ["is_stock_item", "=", 1],
        ["disabled",      "=", 0],
    ]

    # 2. Fixed-list exclusion
    group_exclusions = ["Product", "Body"]
    group_filter      = ["item_group", "not in", group_exclusions]

    # 3. Wildcard exclusions via NOT LIKE
    #    (underscore here is the SQL single‑char wildcard; if you really want
    #     a literal “_” then escape it as "\\_" in Python)
    name_exclude_patterns = ["11_%", "21_%", "%GX%"]
    name_filters = [
        ["name", "not like", pattern]
        for pattern in name_exclude_patterns
    ]

    # 4. Combine them into one filters list
    filters = base_filters + [group_filter] + name_filters
    
    if test_mode:
        return frappe.get_all(
            "Item",
            filters={"name": "100040"},
            fields=fields
        )

    return frappe.get_all(
        "Item",
        filters=filters,
        fields=fields
    )


def _refresh_purchase_item_lead_time(item_code, dry_run=False):
    item = frappe.db.get_value(
        "Item",
        item_code,
        ["name", "lead_time_days", "is_purchase_item", "disabled"],
        as_dict=True,
    )
    if not item or not item.is_purchase_item or item.disabled:
        return {"status": "skipped"}

    avg_lt, _std_lt = _calc_lead_time(item.name)
    if avg_lt is None:
        return {"status": "without_history"}

    return _set_item_lead_time_days(
        item.name,
        item.lead_time_days,
        int(math.ceil(avg_lt or 0)),
        dry_run=dry_run,
    )


def _refresh_manufactured_item_lead_time(item_code, dry_run=False):
    item = frappe.db.get_value(
        "Item",
        item_code,
        ["name", "lead_time_days", "is_stock_item", "is_purchase_item", "disabled"],
        as_dict=True,
    )
    if not item or not item.is_stock_item or item.is_purchase_item or item.disabled:
        return {"status": "skipped"}

    avg_lt, _std_lt, lead_time_context = _calc_manufactured_lead_time(item.name)
    if avg_lt is None:
        return {"status": "without_history"}

    result = _set_item_lead_time_days(
        item.name,
        item.lead_time_days,
        int(math.ceil(avg_lt or 0)),
        dry_run=dry_run,
    )
    result.update({
        "observations": lead_time_context.get("observations"),
        "low_confidence_only": lead_time_context.get("low_confidence_only"),
        "source_counts": lead_time_context.get("source_counts", {}),
    })
    return result


def _set_item_lead_time_days(item_code, old_lead_time_days, new_lead_time_days, dry_run=False):
    old_lead_time_days = int(old_lead_time_days or 0)
    if old_lead_time_days == new_lead_time_days:
        return {"status": "unchanged"}

    if not dry_run:
        frappe.db.set_value("Item", item_code, "lead_time_days", new_lead_time_days)

    return {
        "status": "updated",
        "change": {
            "item_code": item_code,
            "old_lead_time_days": old_lead_time_days,
            "new_lead_time_days": new_lead_time_days,
        },
    }


def _merge_lead_time_update_result(result, update_result):
    status = update_result.get("status")

    if status in ("updated", "unchanged"):
        if update_result.get("low_confidence_only") and "items_low_confidence_only" in result:
            result["items_low_confidence_only"] += 1

        if "source_counts" in result:
            for source, count in update_result.get("source_counts", {}).items():
                result["source_counts"][source] = result["source_counts"].get(source, 0) + count

    if status == "without_history":
        result["items_without_history"] += 1
        return

    if status == "unchanged":
        result["items_with_history"] += 1
        result["items_unchanged"] += 1
        return

    if status != "updated":
        return

    result["items_with_history"] += 1
    result["items_updated"] += 1

    change = update_result.get("change", {})
    if update_result.get("observations") is not None:
        change["observations"] = update_result.get("observations")

    if update_result.get("low_confidence_only") is not None:
        change["low_confidence_only"] = update_result.get("low_confidence_only")

    result["changes"].append(change)


def _calc_lead_time(item_code: str) -> tuple[Optional[float], Optional[float]]:
    """
    Calculate actual purchase lead time from submitted PO date to submitted PREC date.

    ERPNext's Item.lead_time_days describes supplier delivery time. For purchased
    items, the most reliable historical signal is the exact Purchase Order Item
    row linked to each Purchase Receipt Item row:
      - PO transaction_date = date the order was placed
      - PREC posting_date = date the material was received into stock
    Required By / schedule_date is deliberately not used here because it measures
    whether the supplier was early or late against a promise, not actual lead time.
    """
    rows = _get_purchase_item_lead_time_rows(item_code)
    if not rows:
        return None, None

    lead_times = [row.lt for row in rows if row.lt is not None]
    if not lead_times:
        return None, None

    weights = [row.received_stock_qty for row in rows if row.lt is not None]
    update_log_entry(log_id, f"[{now_datetime()}] Lead time observations: {lead_times}")
    return _calculate_lead_time_statistics(lead_times, weights)


def _get_purchase_item_lead_time_rows(item_code: str, limit: int = LEAD_TIME_SAMPLE_LIMIT):
    return frappe.db.sql(
        """
        SELECT
            DATEDIFF(pr.posting_date, po.transaction_date) AS lt,
            COALESCE(NULLIF(pri.stock_qty, 0), pri.qty, 1) AS received_stock_qty,
            po.name AS purchase_order,
            pr.name AS purchase_receipt,
            po.transaction_date AS order_date,
            pr.posting_date AS receipt_date
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        INNER JOIN `tabPurchase Order Item` poi ON poi.name = pri.purchase_order_item
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        INNER JOIN `tabItem` item ON item.name = pri.item_code
        WHERE pri.item_code = %s
            AND poi.item_code = pri.item_code
            AND item.is_purchase_item = 1
            AND item.disabled = 0
            AND pri.docstatus = 1
            AND pr.docstatus = 1
            AND po.docstatus = 1
            AND IFNULL(pr.is_return, 0) = 0
            AND COALESCE(NULLIF(pri.stock_qty, 0), pri.qty, 0) > 0
            AND po.transaction_date IS NOT NULL
            AND pr.posting_date IS NOT NULL
            AND DATEDIFF(pr.posting_date, po.transaction_date) >= 0
        ORDER BY pr.posting_date DESC, pr.posting_time DESC, pr.name DESC
        LIMIT %s
        """,
        (item_code, limit),
        as_dict=True,
    )


def _calc_manufactured_lead_time(item_code: str):
    rows = _get_manufactured_item_lead_time_rows(item_code)
    observations = []

    for row in rows:
        finish_at = _combine_date_and_time(row.posting_date, row.posting_time)
        if not finish_at:
            continue

        start_at, source = _get_manufacturing_start(row, finish_at)
        if not start_at:
            continue

        lead_time_seconds = (finish_at - start_at).total_seconds()
        if lead_time_seconds < 0:
            continue

        observations.append({
            "lead_time_days": max(1, int(math.ceil(lead_time_seconds / 86400.0))),
            "weight": row.completed_qty,
            "source": source,
        })

    if not observations:
        return None, None, {}

    high_confidence_observations = [
        obs for obs in observations
        if obs.get("source") in MANUFACTURED_LEAD_TIME_HIGH_CONFIDENCE_SOURCES
    ]
    selected_observations = high_confidence_observations or observations

    lead_times = [obs.get("lead_time_days") for obs in selected_observations]
    weights = [obs.get("weight") for obs in selected_observations]
    avg_lt, std_lt = _calculate_lead_time_statistics(lead_times, weights)

    source_counts = {}
    for obs in selected_observations:
        source = obs.get("source")
        source_counts[source] = source_counts.get(source, 0) + 1

    return avg_lt, std_lt, {
        "observations": len(selected_observations),
        "low_confidence_only": not bool(high_confidence_observations),
        "source_counts": source_counts,
    }


def _get_manufactured_item_lead_time_rows(item_code: str, limit: int = LEAD_TIME_SAMPLE_LIMIT):
    return frappe.db.sql(
        """
        SELECT
            se.name AS stock_entry,
            se.posting_date,
            se.posting_time,
            se.fg_completed_qty AS completed_qty,
            wo.name AS work_order,
            wo.production_item AS item_code,
            p_stock_entry.planning_start AS planning_stock_entry_start,
            p_work_order.planning_start AS planning_work_order_start,
            timer.timer_start AS timer_start,
            wo.start_datetime AS work_order_start_datetime,
            wo.start_date_time AS work_order_start_date_time,
            wo.actual_start_date AS work_order_actual_start_date,
            wo.planned_start_date AS work_order_planned_start_date,
            wo.creation AS work_order_creation
        FROM `tabStock Entry` se
        INNER JOIN `tabWork Order` wo ON wo.name = se.work_order
        INNER JOIN `tabItem` item ON item.name = wo.production_item
        LEFT JOIN (
            SELECT
                stock_entry,
                MIN(date_de_debut) AS planning_start
            FROM `tabPlanning`
            WHERE docstatus < 2
                AND IFNULL(stock_entry, "") != ""
            GROUP BY stock_entry
        ) p_stock_entry ON p_stock_entry.stock_entry = se.name
        LEFT JOIN (
            SELECT
                work_order,
                MIN(date_de_debut) AS planning_start
            FROM `tabPlanning`
            WHERE docstatus < 2
                AND IFNULL(work_order, "") != ""
            GROUP BY work_order
        ) p_work_order ON p_work_order.work_order = wo.name
        LEFT JOIN (
            SELECT
                tp.work_order,
                MIN(wott.start_time) AS timer_start
            FROM `tabTimer Production` tp
            INNER JOIN `tabWork Order Timer Table` wott ON wott.parent = tp.name
            WHERE IFNULL(tp.work_order, "") != ""
                AND wott.start_time IS NOT NULL
            GROUP BY tp.work_order
        ) timer ON timer.work_order = wo.name
        WHERE wo.production_item = %s
            AND item.is_stock_item = 1
            AND item.is_purchase_item = 0
            AND item.disabled = 0
            AND se.docstatus = 1
            AND se.purpose = "Manufacture"
            AND IFNULL(se.work_order, "") != ""
            AND IFNULL(se.fg_completed_qty, 0) > 0
            AND se.posting_date IS NOT NULL
        ORDER BY se.posting_date DESC, se.posting_time DESC, se.name DESC
        LIMIT %s
        """,
        (item_code, limit),
        as_dict=True,
    )


def _get_manufacturing_start(row, finish_at):
    source_groups = (
        (("planning_stock_entry_start",), "planning_stock_entry"),
        (("planning_work_order_start",), "planning_work_order"),
        (("timer_start",), "timer"),
        (
            (
                "work_order_start_datetime",
                "work_order_start_date_time",
                "work_order_actual_start_date",
            ),
            "work_order_actual",
        ),
        (("work_order_planned_start_date", "work_order_creation"), "work_order_fallback"),
    )

    for fieldnames, source in source_groups:
        starts = [
            _as_datetime(row.get(fieldname))
            for fieldname in fieldnames
            if _is_valid_manufacturing_start(_as_datetime(row.get(fieldname)), finish_at)
        ]
        if starts:
            return min(starts), source

    return None, None


def _as_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    try:
        return get_datetime(value)
    except Exception:
        return None


def _combine_date_and_time(date_value, time_value=None):
    date_part = _as_datetime(date_value)
    if not date_part:
        return None

    if isinstance(time_value, timedelta):
        time_part = (datetime.min + time_value).time()
    elif isinstance(time_value, time):
        time_part = time_value
    elif time_value:
        try:
            time_part = get_datetime("1900-01-01 {0}".format(cstr(time_value))).time()
        except Exception:
            time_part = time.min
    else:
        time_part = time.min

    return datetime.combine(date_part.date(), time_part)


def _is_valid_manufacturing_start(start_at, finish_at):
    return bool(start_at and finish_at and start_at <= finish_at and start_at.year >= 2020)


def _calculate_lead_time_statistics(lead_times, weights=None):
    """
    Calculates lead time statistics including mean and standard deviation.

    Args:
        lead_times (list): List of lead times.
        weights (list): Optional quantity weights for each lead time.

    Returns:
        tuple: Mean and standard deviation of lead times.
    """
    if not lead_times:
        return 0, 0

    # Calculate interquartile range (IQR) for outlier removal
    q1, q3 = np.percentile(lead_times, [25, 75])
    iqr = q3 - q1
    weights = [float(weight or 0) for weight in (weights or [1 for _ in lead_times])]
    filtered = [
        (lt, weight) for lt, weight in zip(lead_times, weights)
        if q1 - 1.5 * iqr <= lt <= q3 + 1.5 * iqr
    ]
    filtered_lead_times = [lt for lt, _weight in filtered]
    filtered_weights = [weight for _lt, weight in filtered]

    # Handle cases with insufficient data
    if len(filtered_lead_times) == 0:
        return 0, 0  # No data after filtering
    elif len(filtered_lead_times) == 1:
        return filtered_lead_times[0], 0  # Single value, no variance

    # Calculate and return mean and standard deviation
    weighted_mean = _weighted_mean(filtered_lead_times, filtered_weights)
    std_dev = _weighted_std_dev(filtered_lead_times, filtered_weights, weighted_mean)
    update_log_entry(log_id, f"[{now_datetime()}] Mean LT: {weighted_mean} and Std Dev: {std_dev}")
    return weighted_mean, std_dev


def _weighted_mean(values, weights):
    total_weight = sum(weights)
    if not total_weight:
        return statistics.mean(values)
    return sum(value * weight for value, weight in zip(values, weights)) / total_weight


def _weighted_std_dev(values, weights, weighted_mean):
    total_weight = sum(weights)
    if not total_weight:
        return statistics.stdev(values)
    variance = sum(weight * ((value - weighted_mean) ** 2) for value, weight in zip(values, weights)) / total_weight
    return math.sqrt(variance)


def _get_demand_profile(item_code: str, item_creation=None):
    start_date, end_date = _get_demand_window(item_creation)
    demand_by_day = _get_daily_outflow_map(item_code, start_date, end_date)
    return _build_demand_profile(demand_by_day, start_date, end_date)


def _get_demand_profiles_for_items(items):
    if not items:
        return {}

    windows = {
        item.name: _get_demand_window(item.creation)
        for item in items
    }
    min_start_date = min(start_date for start_date, _end_date in windows.values())
    max_end_date = max(end_date for _start_date, end_date in windows.values())
    demand_maps = {item.name: {} for item in items}
    item_codes = [item.name for item in items]

    for item_code_chunk in _chunked(item_codes):
        rows = _get_daily_outflow_rows(item_code_chunk, min_start_date, max_end_date)
        for row in rows:
            item_code = row.item_code
            posting_date = _as_datetime(row.posting_date)
            if not posting_date or item_code not in windows:
                continue

            posting_date = posting_date.date()
            start_date, end_date = windows[item_code]
            if start_date <= posting_date <= end_date:
                demand_maps[item_code][posting_date] = float(row.qty or 0)

    return {
        item.name: _build_demand_profile(demand_maps.get(item.name, {}), *windows[item.name])
        for item in items
    }


def _build_demand_profile(demand_by_day, start_date, end_date):
    daily_outflows = _fill_daily_outflows(demand_by_day, start_date, end_date)
    adjusted_daily_outflows = _winsorize_daily_outflows(daily_outflows)
    history_days = len(daily_outflows)
    annual_outflow = sum(daily_outflows)
    average_monthly_outflow = (annual_outflow / history_days * DEMAND_MONTH_DAYS) if history_days else 0

    return frappe._dict({
        "daily_outflows": adjusted_daily_outflows,
        "raw_daily_outflows": daily_outflows,
        "history_days": history_days,
        "demand_days": sum(1 for qty in daily_outflows if qty > 0),
        "annual_outflow": annual_outflow,
        "average_monthly_outflow": average_monthly_outflow,
    })


def _empty_demand_profile():
    return frappe._dict({
        "daily_outflows": [],
        "raw_daily_outflows": [],
        "history_days": 0,
        "demand_days": 0,
        "annual_outflow": 0,
        "average_monthly_outflow": 0,
    })


def _get_demand_window(item_creation=None, lookback_days: int = DEMAND_LOOKBACK_DAYS):
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=lookback_days - 1)
    created_at = _as_datetime(item_creation)
    if created_at:
        start_date = max(start_date, created_at.date())

    if start_date > end_date:
        start_date = end_date

    return start_date, end_date


def _get_daily_outflow_map(item_code: str, start_date, end_date):
    rows = _get_daily_outflow_rows([item_code], start_date, end_date)
    demand_by_day = {}
    for row in rows:
        posting_date = _as_datetime(row.posting_date)
        if posting_date:
            demand_by_day[posting_date.date()] = float(row.qty or 0)

    return demand_by_day


def _get_daily_outflow_rows(item_codes, start_date, end_date):
    if not item_codes:
        return []

    item_placeholders = ",".join(["%s"] * len(item_codes))
    voucher_placeholders = ",".join(["%s"] * len(DEMAND_VOUCHER_TYPES))
    stock_entry_purpose_placeholders = ",".join(["%s"] * len(DEMAND_STOCK_ENTRY_PURPOSES))
    query = f"""
        SELECT
            sle.item_code,
            sle.posting_date,
            COALESCE(-SUM(sle.actual_qty), 0) AS qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabStock Entry` se
            ON se.name = sle.voucher_no
            AND sle.voucher_type = 'Stock Entry'
        WHERE sle.item_code IN ({item_placeholders})
            AND sle.actual_qty < 0
            AND IFNULL(sle.is_cancelled, 'No') = 'No'
            AND sle.posting_date >= %s
            AND sle.posting_date <= %s
            AND (
                sle.voucher_type IN ({voucher_placeholders})
                OR (
                    sle.voucher_type = 'Stock Entry'
                    AND se.purpose IN ({stock_entry_purpose_placeholders})
                )
            )
        GROUP BY sle.item_code, sle.posting_date
    """
    args = (
        list(item_codes)
        + [start_date, end_date]
        + list(DEMAND_VOUCHER_TYPES)
        + list(DEMAND_STOCK_ENTRY_PURPOSES)
    )
    return frappe.db.sql(query, tuple(args), as_dict=True)


def _fill_daily_outflows(demand_by_day, start_date, end_date):
    days = (end_date - start_date).days + 1
    return [
        demand_by_day.get(start_date + timedelta(days=offset), 0.0)
        for offset in range(days)
    ]


def _winsorize_daily_outflows(daily_outflows):
    non_zero = [qty for qty in daily_outflows if qty > 0]
    if len(non_zero) < DEMAND_OUTLIER_MIN_NON_ZERO_DAYS:
        return daily_outflows

    q1, q3 = np.percentile(non_zero, [25, 75])
    iqr = q3 - q1
    if iqr <= 0:
        return daily_outflows

    upper_fence = q3 + 1.5 * iqr
    return [
        min(qty, upper_fence) if qty > 0 else 0.0
        for qty in daily_outflows
    ]


def _get_monthly_outflows(item_code: str) -> list[int]:
    """Compatibility helper: return rolling 30-day demand buckets from the daily profile."""
    demand = _get_demand_profile(item_code)
    buckets = []
    daily_outflows = demand.raw_daily_outflows
    for start in range(0, len(daily_outflows), 30):
        buckets.append(sum(daily_outflows[start:start + 30]))

    return buckets


def _get_stock_position(item_code: str):
    return _get_stock_positions_for_items([item_code]).get(item_code) or _empty_stock_position()


def _get_stock_positions_for_items(item_codes):
    if not item_codes:
        return {}

    stock_positions = {
        item_code: _empty_stock_position()
        for item_code in item_codes
    }
    warehouse_placeholders = ",".join(["%s"] * len(EXCLUDED_WAREHOUSES))

    for item_code_chunk in _chunked(item_codes):
        item_placeholders = ",".join(["%s"] * len(item_code_chunk))
        rows = frappe.db.sql(
            f"""
            SELECT
                bin.item_code,
                COALESCE(SUM(bin.actual_qty), 0) AS actual_qty,
                COALESCE(SUM(bin.projected_qty), 0) AS projected_qty
            FROM `tabBin` bin
            INNER JOIN `tabWarehouse` warehouse ON warehouse.name = bin.warehouse
            WHERE bin.item_code IN ({item_placeholders})
                AND warehouse.disabled = 0
                AND bin.warehouse NOT IN ({warehouse_placeholders})
            GROUP BY bin.item_code
            """,
            tuple(list(item_code_chunk) + EXCLUDED_WAREHOUSES),
            as_dict=True,
        )
        for row in rows:
            stock_positions[row.item_code] = frappe._dict({
                "actual_qty": float(row.get("actual_qty") or 0),
                "projected_qty": float(row.get("projected_qty") or 0),
            })

    return stock_positions


def _empty_stock_position():
    return frappe._dict({
        "actual_qty": 0.0,
        "projected_qty": 0.0,
    })


def _get_max_stock(item_code: str) -> float:
    """Compatibility helper kept for callers that still expect this private name."""
    return _get_stock_position(item_code).actual_qty

# --- Calculations ---

def _lead_time_stats(lead_times: list[int]) -> tuple[float, float]:
    if not lead_times:
        return 0.0, 0.0
    q1, q3 = np.percentile(lead_times, [25,75])
    iqr = q3 - q1
    filtered = [lt for lt in lead_times if q1-1.5*iqr <= lt <= q3+1.5*iqr]
    if len(filtered) <= 1:
        return (filtered[0], 0.0) if filtered else (0.0, 0.0)
    return mean(filtered), stdev(filtered)

def _compute_safety_and_reorder(daily_outflows: list[float], avg_lt: float, std_lt: float) -> tuple[int, int]:
    """
    Compute safety stock and reorder point from demand during lead time.

    Formula:
        reorder point = expected demand during lead time + safety stock
        expected demand during lead time = average daily demand * average lead time
        safety stock = Z * sqrt(
            average lead time * variance of daily demand
            + variance of lead time * average daily demand^2
        )
    """
    if not daily_outflows or sum(daily_outflows) <= 0:
        return 0, 0

    avg_lt = max(0.0, float(avg_lt or 0))
    std_lt = max(0.0, float(std_lt or 0))
    daily_mean = mean(daily_outflows)
    daily_std = stdev(daily_outflows) if len(daily_outflows) > 1 else 0.0

    lead_time_demand = daily_mean * avg_lt
    var_term = (avg_lt * (daily_std ** 2)) + ((daily_mean ** 2) * (std_lt ** 2))
    var_term = max(0.0, var_term)

    ss = SERVICE_LEVEL_Z * math.sqrt(var_term)
    ro = lead_time_demand + ss

    return math.ceil(ss), math.ceil(ro)


def _update_item(item_code: str, avg_month: int, annual: int, ss: int, ro: int, lt: float):
    frappe.db.set_value("Item", item_code, {
        "average_monthly_outflow": avg_month,
        "annual_outflow": annual,
        "safety_stock": ss,
        "reorder_level": ro,
        "lead_time_days": int(math.ceil(lt or 0))
    })

# --- Purchase Item Status ---

def update_item_purchase_status(test_mode: bool, log_id: str):
    """
    Update is_purchase_item flags, skipping Plug and Valve Seat groups.
    """
    # Base filter: exclude disabled and GX items
    filters = {"disabled": 0, "name": ["not like", "%GX%"]}
    if test_mode:
        filters = {"name": "100040"}
        update_log_entry(log_id, f"[{now_datetime()}] Test mode: only processing Item 100040")

    items = frappe.get_all("Item", filters=filters, fields=["name", "item_group"])
    for it in items:
        # Skip specific item groups
        if it.item_group in ("Plug", "Valve Seat", "Valve Head"):
            is_purch = False
            if test_mode:
                update_log_entry(log_id, f"[{now_datetime()}] Test mode: is_purch 0 for item 100040")
        else:
            is_purch = frappe.db.exists("Purchase Receipt Item", {"item_code": it.name}) or it.item_group == "Raw Material"
        frappe.db.set_value("Item", it.name, "is_purchase_item", {int(bool(is_purch))})
            # update_log_entry(log_id, f"[{now_datetime()}] Set is_purchase_item={int(is_purch)} for Item {it.name}")

    frappe.db.commit()

# --- Notifications ---

def _send_notifications(items: list[dict]):
    html = _build_email(items)
    make(
        recipients="alexandre.ringwald@amf.ch",
        cc="alexandre.trachsel@amf.ch",
        subject="Safety Stock Report",
        content=html,
        communication_medium="Email",
        send_email=True
    )

def _build_email(items: list[dict]) -> str:
    rows = ''.join(
        f"<tr><td>{i['code']}</td><td>{i['name']}</td><td>{i['stock']}</td>"
        f"<td>{i['avg_monthly']}</td><td>{i['ro']}</td><td>{i['ss']}</td></tr>"
        for i in items
    )
    return (
        "<p>Items at or below reorder level:</p>"
        "<table style='border-collapse:collapse;width:100%;'>"
        "<tr style='background:#2b47d9;color:#fff;'><th>Code</th><th>Name</th><th>Stock</th>"
        "<th>Avg Mth</th><th>Reorder</th><th>Safety</th></tr>"
        f"{rows}</table>"
    )
