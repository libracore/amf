import frappe
import math
import datetime
import statistics
import numpy as np
import pandas as pd
from frappe.core.doctype.communication.email import make
from frappe.utils import date_diff

# Constants
SERVICE_LEVEL_Z = 1.64  # Z-score for 95% service level
DEFAULT_LEAD_TIME = 30  # Default lead time in days
DEFAULT_STD_DEV_LEAD_TIME = 10  # Default standard deviation of lead time
TEST_MODE = False

@frappe.whitelist()
def check_stock_levels(test_mode=TEST_MODE):
    """
    Main function to check stock levels, calculate safety stock and reorder levels,
    and send email notifications for items requiring reordering.

    Args:
        test_mode (bool): Whether to run the function in test mode.
    """
    items = fetch_items(test_mode)
    items_to_email = []

    for item in items:
        if test_mode:
            print(item)
        if item["is_purchase_item"]:
            avg_lead_time, std_dev_lead_time = calculate_dynamic_lead_time(item["name"])
        else:
            avg_lead_time = DEFAULT_LEAD_TIME
            std_dev_lead_time = DEFAULT_STD_DEV_LEAD_TIME

        monthly_outflows = calculate_monthly_outflows(item["name"])
        avg_monthly_outflow = statistics.mean(monthly_outflows) if monthly_outflows else 0
        annual_outflows = sum(monthly_outflows)
        
        if test_mode:
            print("avg_monthly_outflow:", avg_monthly_outflow)
            print("avg_annual_outflow:", annual_outflows)

        # Calculate safety stock and reorder levels
        safety_stock, reorder_level = calculate_safety_stock_and_reorder_level(monthly_outflows, avg_lead_time, std_dev_lead_time)

        update_item_fields(item["name"], avg_monthly_outflow, annual_outflows, safety_stock, reorder_level, avg_lead_time)

        # Check stock levels across warehouses
        highest_stock = get_highest_stock(item["name"])
        if highest_stock < reorder_level:
            frappe.db.set_value("Item", item["name"], "reorder", 1)
            items_to_email.append(item)
        else:
            frappe.db.set_value("Item", item["name"], "reorder", 0)

        frappe.db.commit()

    # Send email notifications
    if not TEST_MODE:
        if items_to_email:
            send_email_notifications(items_to_email)
            print("Done sending emails.")
        else:
            print("No items need reordering. No email sent.")

    print("Done checking stock levels.")


def fetch_items(test_mode):
    """
    Fetches all stock items from the database.

    Args:
        test_mode (bool): Whether to fetch only test items.

    Returns:
        list: List of items.
    """
    filters = {'is_stock_item': 1, 'disabled': 0}
    if test_mode:
        filters["name"] = "420047"
    return frappe.get_all(
        "Item",
        filters=filters,
        fields=["name", "item_name", "item_group", "safety_stock", "reorder_level", "reorder", "average_monthly_outflow", "is_purchase_item"])


def calculate_dynamic_lead_time(item_code):
    """
    Dynamically calculates lead time and its standard deviation for an item.

    Args:
        item_code (str): Item code.

    Returns:
        tuple: Average lead time, standard deviation of lead time.
    """
    query = """
        SELECT
            DATEDIFF(pri.creation, poi.schedule_date) AS lead_time
        FROM
            `tabPurchase Receipt Item` pri
        INNER JOIN
            `tabPurchase Order Item` poi ON poi.name = pri.purchase_order_item
        WHERE
            pri.docstatus = 1 AND poi.docstatus = 1 AND pri.item_code = %s
    """
    data = frappe.db.sql(query, item_code, as_dict=True)
    lead_times = [entry["lead_time"] for entry in data if entry["lead_time"] > 0]

    if not lead_times:
        return 0, 0

    if TEST_MODE:
        print("lead_times:", lead_times)
    return calculate_lead_time_statistics(lead_times)


def calculate_monthly_outflows(item_code):
    """
    Calculates monthly outflows for the past 12 months for an item.

    Args:
        item_code (str): Item code.

    Returns:
        list: Monthly outflows.
    """
    monthly_outflows = []
    current_date = datetime.datetime.now()

    for month_offset in range(12):
        target_date = current_date.replace(day=1) - datetime.timedelta(days=month_offset * 30)
        target_month, target_year = target_date.month, target_date.year

        monthly_outflow = frappe.db.sql(
            """
                SELECT
                    SUM(sle.actual_qty) AS total_outflow
                FROM
                    `tabStock Ledger Entry` sle
                JOIN
                    `tabItem` i ON sle.item_code = i.item_code
                LEFT JOIN
                    `tabStock Entry` se ON sle.voucher_no = se.name
                WHERE
                    sle.item_code = %s
                    AND sle.actual_qty < 0
                    AND (
                            (sle.voucher_type = 'Stock Entry' AND se.purpose = 'Manufacture') OR
                            (sle.voucher_type = 'Delivery Note')
                        )
                    AND MONTH(sle.posting_date) = %s
                    AND YEAR(sle.posting_date) = %s
                    AND i.disabled = 0
            """,
            (item_code, target_month, target_year))

        monthly_outflows.append(-monthly_outflow[0][0] if monthly_outflow and monthly_outflow[0][0] else 0)

    if TEST_MODE:
        print("monthly:", monthly_outflows)
    
    return monthly_outflows


def calculate_safety_stock_and_reorder_level(monthly_outflows, avg_lead_time, std_dev_lead_time):
    """
    Calculates safety stock and reorder levels using demand and lead time statistics.

    Args:
        monthly_outflows (list): Monthly outflows.
        avg_lead_time (float): Average lead time.
        std_dev_lead_time (float): Standard deviation of lead time.

    Returns:
        tuple: Safety stock, reorder level.
    """
    if not monthly_outflows:
        return 0, 0

    avg_demand = statistics.mean(monthly_outflows) / 30
    std_dev_demand = statistics.stdev(monthly_outflows) / 30

    safety_stock = SERVICE_LEVEL_Z * math.sqrt(
        (avg_demand * std_dev_lead_time ** 2) +
        (avg_lead_time * std_dev_demand ** 2)
    )
    reorder_level = safety_stock + avg_demand * avg_lead_time
    
    if TEST_MODE:
        print("safety_stock:", math.ceil(safety_stock), "reorder_level:", math.ceil(reorder_level))
        
    return math.ceil(safety_stock), math.ceil(reorder_level)


def update_item_fields(item_code, avg_monthly_outflow, annual_outflows, safety_stock, reorder_level, lead_time_days):
    """
    Updates the Item doctype with calculated fields.

    Args:
        item_code (str): Item code.
        avg_monthly_outflow (float): Average monthly outflow.
        annual_outflows (float): Annual outflows.
        safety_stock (float): Safety stock.
        reorder_level (float): Reorder level.
        lead_time_days (float): Lead time in days.
    """
    frappe.db.set_value("Item", item_code, "average_monthly_outflow", math.ceil(avg_monthly_outflow))
    frappe.db.set_value("Item", item_code, "annual_outflow", math.ceil(annual_outflows))
    frappe.db.set_value("Item", item_code, "safety_stock", math.ceil(safety_stock))
    frappe.db.set_value("Item", item_code, "reorder_level", math.ceil(reorder_level))
    frappe.db.set_value("Item", item_code, "lead_time_days", lead_time_days)

def get_highest_stock(item_code):
    """
    Gets the highest stock level across all warehouses for an item.

    Args:
        item_code (str): Item code.

    Returns:
        float: Highest stock level.
    """
    warehouses = frappe.get_all("Warehouse", filters={
                                "name": ["not in", ["AMF_OLD", "Scrap - AMF21", "R&D - AMF21"]]})
    
    if TEST_MODE:
        print("max_stock:", max(
        frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": wh["name"]}, "actual_qty") or 0
        for wh in warehouses
    ))
    return max(
        frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": wh["name"]}, "actual_qty") or 0
        for wh in warehouses
    )


def send_email_notifications(items):
    """
    Sends email notifications for items requiring reordering.

    Args:
        items (list): List of items.
    """
    email_content = build_email_content(items)
    email_context = {
        'recipients': 'alexandre.ringwald@amf.ch',
        'content': email_content,
        'subject': "Safety Stock Report on Items",
        'communication_medium': 'Email',
        'send_email': True,
        'cc': 'alexandre.trachsel@amf.ch',
    }
    make(**email_context)
    print("Email sent successfully.")


def build_email_content(items):
    """
    Builds email content for reorder notifications.

    Args:
        items (list): List of items.

    Returns:
        str: HTML email content.
    """
    content = "<p>The following items have reached their reorder level:</p>"
    content += "<table style='border-collapse: collapse; width: 100%;'>"
    content += """
        <tr style='background-color: #2b47d9; color: white;'>
            <th>Item Code</th><th>Item Name</th><th>Current Stock</th>
            <th>Monthly Outflow</th><th>Reorder Level</th><th>Safety Stock</th>
        </tr>
    """

    for item in items:
        content += f"""
            <tr>
                <td>{item['name']}</td>
                <td>{item['item_name']}</td>
                <td>{item.get('highest_stock', 0)}</td>
                <td>{item.get('average_monthly_outflow', 0)}</td>
                <td>{item.get('reorder_level', 0)}</td>
                <td>{item.get('safety_stock', 0)}</td>
            </tr>
        """

    content += "</table>"
    return content


def calculate_lead_time_statistics(lead_times):
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

    if TEST_MODE:
        print("mean_lead_times:", mean, "std_lead_times:", std_dev)

    return mean, std_dev
