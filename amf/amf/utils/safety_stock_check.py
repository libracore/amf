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
from datetime import datetime, timedelta
from statistics import mean, stdev
import numpy as np
from frappe.core.doctype.communication.email import make
from amf.amf.utils.stock_entry import _get_or_create_log, update_log_entry
from amf.amf.utils.stock_entry import now_datetime

# Constants
SERVICE_LEVEL_Z = 1.64  # Z-score for 95% service level
DEFAULT_LEAD_TIME = 15  # days
DEFAULT_STD_DEV_LEAD_TIME = 15  # days
EXCLUDED_WAREHOUSES = ["AMF_OLD", "Scrap - AMF21", "R&D - AMF21"]

doc = frappe._dict({
        "doctype": "Bin",
        "name": f"[{now_datetime()}] Auto Stock Level"
    })
log_id = _get_or_create_log(doc)

@frappe.whitelist()   
def check_stock_levels(test_mode=0):
    """
    Main entry: calculate safety stocks, reorder levels and flag items for reorder.
    """
    # Update purchase status - no doc context for top-level, so omitted logging
    
    
    update_item_purchase_status(test_mode, log_id)

    items = _get_items(test_mode)
    to_notify = []

    for item in items:
        # Initialize log for this Item
        
        update_log_entry(log_id, f"[{now_datetime()}] check_stock_levels start for Item {item.name}")

        # Lead time calculation
        if item.is_purchase_item:
            # update_log_entry(log_id, f"[{now_datetime()}] Calculating lead time for purchase item")
            avg_lt, std_lt = _calc_lead_time(item.name)
            update_log_entry(log_id, f"[{now_datetime()}] Lead time stats: avg_lt={avg_lt}, std_lt={std_lt}")
        else:
            update_log_entry(log_id, f"[{now_datetime()}] Using default lead time for non-purchase item")
            avg_lt, std_lt = DEFAULT_LEAD_TIME, DEFAULT_STD_DEV_LEAD_TIME

        # Demand data
        # update_log_entry(log_id, f"[{now_datetime()}] Fetching monthly outflows")
        outflows = _get_monthly_outflows(item.name)
        avg_monthly = math.ceil(mean(outflows)) if outflows else 0
        annual = sum(outflows)
        update_log_entry(log_id, f"[{now_datetime()}] Demand: avg_monthly={avg_monthly}, annual={annual}")

        # Safety stock & reorder level
        ss, ro = _compute_safety_and_reorder(outflows, avg_lt, std_lt)
        update_log_entry(log_id, f"[{now_datetime()}] Calculated safety_stock={ss}, reorder_level={ro}")
        _update_item(item.name, avg_monthly, annual, ss, ro, avg_lt)
        # update_log_entry(log_id, f"[{now_datetime()}] Updated Item {item.name} with new stock params")

        # Stock evaluation
        max_stock = _get_max_stock(item.name)
        update_log_entry(log_id, f"[{now_datetime()}] Max stock across warehouses={max_stock}")
        needs_reorder = max_stock < ro
        frappe.db.set_value("Item", item.name, "reorder", int(needs_reorder))
        update_log_entry(log_id, f"[{now_datetime()}] Set reorder flag={int(needs_reorder)} for Item {item.name}")

        if needs_reorder:
            to_notify.append({
                "code": item.name,
                "name": item.item_name,
                "stock": max_stock,
                "avg_monthly": avg_monthly,
                "ro": ro,
                "ss": ss
            })
            update_log_entry(log_id, f"[{now_datetime()}] Item {item.name} queued for notification")

    frappe.db.commit()

    if to_notify and not test_mode:
        update_log_entry(log_id, f"[{now_datetime()}] Sending notifications to recipients")
        _send_notifications(to_notify)
        update_log_entry(log_id, f"[{now_datetime()}] Notifications sent")


# --- Data Fetching Helpers ---
def _get_items(test_mode: bool):
    """
    Fetch stock items, excluding those with 'GX' in their name.
    In test mode, only return the specific test item.
    """
    fields = ["name", "item_name", "is_purchase_item"]
    
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

def _calc_lead_time(item_code: str) -> tuple[float, float]:
    """
    Calculate average and std deviation of positive lead times for an item.
    Excludes zero or negative durations via SQL filter and Python.
    """
    query = (
        "SELECT DATEDIFF(pr.creation, pri.schedule_date) AS lt "
        "FROM `tabPurchase Receipt Item` pri "
        "JOIN `tabPurchase Receipt` pr ON pri.parent=pr.name "
        "WHERE pri.docstatus=1 "
        "  AND pri.item_code=%s "
    )
    rows = frappe.db.sql(query, item_code, as_dict=True)
    # Exclude any null or non-positive values
    lead_times = [r.lt for r in rows if r.lt is not None]
    update_log_entry(log_id, f"[{now_datetime()}] Lead time stats: {lead_times}")
    return _calculate_lead_time_statistics(lead_times)

def _calculate_lead_time_statistics(lead_times):
    """
    Calculates lead time statistics including mean and standard deviation.

    Args:
        lead_times (list): List of lead times.

    Returns:
        tuple: Mean and standard deviation of lead times.
    """
    if not lead_times:
        return 0, 0

    # Calculate interquartile range (IQR) for outlier removal
    q1, q3 = np.percentile(lead_times, [25, 75])
    iqr = q3 - q1
    filtered_lead_times = [
        lt for lt in lead_times if q1 - 1.5 * iqr <= lt <= q3 + 1.5 * iqr
    ]

    # Handle cases with insufficient data
    if len(filtered_lead_times) == 0:
        return 0, 0  # No data after filtering
    elif len(filtered_lead_times) == 1:
        return filtered_lead_times[0], 0  # Single value, no variance

    # Calculate and return mean and standard deviation
    mean = statistics.mean(filtered_lead_times)
    std_dev = statistics.stdev(filtered_lead_times)
    update_log_entry(log_id, f"[{now_datetime()}] Mean LT: {mean} and Std Dev: {std_dev}")
    return mean, std_dev


def _get_monthly_outflows(item_code: str) -> list[int]:
    now = datetime.now()
    outflows = []
    for i in range(12):
        start = (now.replace(day=1) - timedelta(days=30*i)).replace(hour=0, minute=0)
        end = (start + timedelta(days=32)).replace(day=1)
        total = frappe.db.sql(
            """
            SELECT COALESCE(-SUM(sle.actual_qty),0)
            FROM `tabStock Ledger Entry` sle
            LEFT JOIN `tabStock Entry` se ON se.name=sle.voucher_no
            WHERE sle.item_code=%s
              AND sle.actual_qty<0
              AND (
                  sle.voucher_type='Delivery Note' OR
                  (sle.voucher_type='Stock Entry' AND se.purpose='Manufacture')
              )
              AND sle.posting_date>= %s AND sle.posting_date < %s
            """,
            (item_code, start, end)
        )
        outflows.append(total[0][0] if total else 0)
    update_log_entry(log_id, f"[{now_datetime()}] Monthly outflows {outflows}")
    return outflows


def _get_max_stock(item_code: str) -> float:
    # Fetch warehouse list
    wh_records = frappe.get_all(
        "Warehouse",
        filters={"name": ["not in", EXCLUDED_WAREHOUSES]},
        fields=["name"]
    )
    whs = [w.name for w in wh_records] if wh_records else []
    if not whs:
        return 0

    # Raw SQL to avoid escape issues
    placeholders = ",".join(["%s"] * len(whs))
    query = f"SELECT actual_qty FROM `tabBin` WHERE item_code=%s AND warehouse IN ({placeholders})"
    args = [item_code] + whs
    rows = frappe.db.sql(query, tuple(args), as_dict=True)
    return max((r.actual_qty for r in rows), default=0)

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

def _compute_safety_and_reorder(monthly: list[int], avg_lt: float, std_lt: float) -> tuple[int, int]:
    """
    Compute safety stock and reorder level, excluding zero-demand months and guarding against negative variance.
    """
    # Exclude months with zero demand
    pos_monthly = [m for m in monthly if m > 0]
    if not pos_monthly:
        return 0, 0

    # Compute daily demand metrics
    daily_mean = mean(pos_monthly) / 30
    daily_std = stdev(pos_monthly) / 30 if len(pos_monthly) > 1 else 0

    # Calculate variance term and guard against negative
    var_term = (daily_mean * std_lt ** 2) + (avg_lt * daily_std ** 2)
    if var_term < 0:
        var_term = 0

    ss = SERVICE_LEVEL_Z * math.sqrt(var_term)
    ro = ss + daily_mean * avg_lt

    return math.ceil(ss), math.ceil(ro)


def _update_item(item_code: str, avg_month: int, annual: int, ss: int, ro: int, lt: float):
    frappe.db.set_value("Item", item_code, {
        "average_monthly_outflow": avg_month,
        "annual_outflow": annual,
        "safety_stock": ss,
        "reorder_level": ro,
        "lead_time_days": lt
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
