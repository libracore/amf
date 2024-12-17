from frappe.core.doctype.communication.email import make
import frappe
import math
import datetime
import statistics
from frappe.utils import date_diff
import numpy as np
import pandas as pd


@frappe.whitelist()
def check_stock_levels():
    # Test Mode
    test_mode = 1
    # Constants
    Z = 1.64  # Z-score for 95% service level
    # avg_lead_time = 90  # Average lead time in days
    # std_dev_lead_time = 15  # Standard deviation of lead time in days
    item_group_data = {
        "Kit": {"lead_time": 30, "std_dev_lead_time": 6},
        "Glass": {"lead_time": 90, "std_dev_lead_time": 20},
        "Cable": {"lead_time": 15, "std_dev_lead_time": 5},
        "Plunger": {"lead_time": 90, "std_dev_lead_time": 20},
        "Syringe": {"lead_time": 90, "std_dev_lead_time": 20},
        "Valve Head": {"lead_time": 15, "std_dev_lead_time": 5},
        "Raw Material": {"lead_time": 120, "std_dev_lead_time": 30},
        "Electronic Board": {"lead_time": 90, "std_dev_lead_time": 20},
        "Plug": {"lead_time": 30, "std_dev_lead_time": 10},
        "Valve Seat": {"lead_time": 60, "std_dev_lead_time": 20},
        "Part": {"lead_time": 15, "std_dev_lead_time": 5},
        "Product": {"lead_time": 30, "std_dev_lead_time": 6},
        "Body": {"lead_time": 30, "std_dev_lead_time": 6}
    }
    # Get the current year and calculate last year's dates
    current_year = datetime.datetime.now().year

    items = frappe.get_all("Item", filters={'is_stock_item': 1, 'disabled': 0}, fields=[
                           "name", "item_name", "safety_stock", "reorder_level", "reorder", "item_group", "average_monthly_outflow", "is_purchase_item"])
    if test_mode:
        # Test Line
        items = frappe.get_all("Item", fields=["name", "item_name", "safety_stock", "reorder_level", "reorder",
                               "item_group", "average_monthly_outflow", "is_purchase_item"], filters={"name": "300040"})

    # print("items:",items)
    # input()

    items_to_email = []  # Create an empty list to hold items that need reordering
    for item in items:
        # print("item:",item)
        # Fetch outflow for this item for each month of the last year


        # Fetch dynamic lead time using calculate_real_lead_time
        if item.get("is_purchase_item"):
            lead_time_stats, std_dev_lead_time = calculate_real_lead_time(item=item["name"])
        else:
            lead_time_stats, std_dev_lead_time = None, None

        # Determine average lead time with fallback
        avg_lead_time = lead_time_stats if isinstance(lead_time_stats, int) else item_group_data.get("lead_time", 30)

        # Determine standard deviation of lead time with fallback
        std_dev_lead_time = std_dev_lead_time if isinstance(std_dev_lead_time, int) else item_group_data.get("std_dev_lead_time", 10)

        monthly_outflows = []
        annual_outflows = 0
        current_date = datetime.datetime.now()
        for month_offset in range(0, 12):
            # Calculate the target month and year
            target_date = current_date.replace(
                day=1) - datetime.timedelta(days=month_offset * 30)
            target_month = target_date.month
            target_year = target_date.year
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
                (item["name"], target_month, target_year),
            )

            monthly_outflow = (
                monthly_outflow[0][0]
                if monthly_outflow and monthly_outflow[0][0]
                else 0
            )
            # Converting outflow to positive numbers for demand
            monthly_outflows.append(-monthly_outflow)
        # print("monthly_outflows:",monthly_outflows)
        # Default values if needed.
        group_data = item_group_data.get(
            item['item_group'], {"lead_time": 30, "std_dev_lead_time": 6})
        # avg_lead_time = group_data["lead_time"]
        # std_dev_lead_time = group_data["std_dev_lead_time"]
        annual_outflows = sum(monthly_outflows)
        avg_monthly_outflow = statistics.mean(monthly_outflows)
        # print("avg_monthly_outflow:",avg_monthly_outflow)
        # print("annual_outflows:",annual_outflows)
        # input()
        # Calculate standard deviation and average of monthly outflows (demands)
        std_dev_demand = statistics.stdev(monthly_outflows) / 30
        # Assuming 30 days in a month to get daily demand
        avg_demand = (statistics.mean(monthly_outflows) / 30)
        # Calculate safety stock using the composite distribution formula
        safety_stock = Z * math.sqrt(
            avg_demand * (std_dev_lead_time) ** 2
            + (avg_lead_time * std_dev_demand) ** 2
        )
        order_point = safety_stock + avg_demand * avg_lead_time
        # safety_stock = (Z * std_dev_demand * math.sqrt(avg_lead_time)) + (Z * avg_demand * std_dev_lead_time)

        if safety_stock < 1:
            safety_stock = 0

        # Test Print
        if test_mode:
            print("Item:", item["name"])
            print("avg_lead_time:", math.ceil(avg_lead_time))
            print("std_dev_lead_time:", math.ceil(std_dev_lead_time))
            print("monthly_outflows:", monthly_outflows)
            print("avg_monthly_outflow:", math.ceil(avg_monthly_outflow))
            print("annual_outflows:", math.ceil(annual_outflows))
            print("std_dev_demand:", math.ceil(std_dev_demand))
            print("avg_demand:", math.ceil(avg_demand))
            print("safety_stock:", math.ceil(safety_stock))
            print("order_point:", math.ceil(order_point))

        # Update safety stock value in Item doctype
        item["average_monthly_outflow"] = avg_monthly_outflow
        item["safety_stock"] = safety_stock
        item["reorder_level"] = order_point
        frappe.db.set_value(
            "Item", item["name"], "average_monthly_outflow", math.ceil(avg_monthly_outflow))
        frappe.db.set_value(
            "Item", item["name"], "annual_outflow", math.ceil(annual_outflows))
        frappe.db.set_value(
            "Item", item["name"], "safety_stock", math.ceil(safety_stock))
        frappe.db.set_value(
            "Item", item["name"], "reorder_level", math.ceil(order_point))
        frappe.db.set_value(
            "Item", item["name"], "lead_time_days", avg_lead_time)
        # Now let's check the stock levels against this new safety stock
        highest_stock = 0  # Initialize variable to store the highest stock value
        all_warehouses = frappe.get_all("Warehouse")
        filtered_warehouses = [
            wh for wh in all_warehouses if "AMF_OLD" not in wh.name and "Scrap - AMF21" not in wh.name and "R&D - AMF21" not in wh.name]

        for warehouse in filtered_warehouses:
            current_stock = (
                frappe.db.get_value(
                    "Bin",
                    {"item_code": item["name"], "warehouse": warehouse.name},
                    "actual_qty",
                )
                or 0
            )
            # Update the highest stock value if the current stock is higher
            if current_stock > highest_stock:
                highest_stock = current_stock

        # Assign highest_stock to the item dictionary
        item['highest_stock'] = highest_stock

        if highest_stock < item["reorder_level"]:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item["name"], "reorder", 1)
            # print(f"Setting 'reorder' to 1 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")
            # Add the item to the items_to_email list
            items_to_email.append(item)
        else:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item["name"], "reorder", 0)
            # print(f"Setting 'reorder' to 0 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")

        frappe.db.commit()


    if test_mode:
        items_to_email = None

    # Send the email for items that need reordering
    if items_to_email:
        sendmail(items_to_email)
        print("Done sending emails.")
    else:
        print("No items need reordering. No email sent.")

    print("Done checking stock levels.")
        
        # Test Line
        #print(f"Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")

def sendmail(items):
    print("Sending email...")
    #print(items)
    if not items:
        return "No items to reorder."
    
    # Sort items by item_group
    items = sorted(items, key=lambda x: x.get('item_group', ''))
    #print(items)
    # Base URL for item links
    base_url = "https://amf.libracore.ch/desk#Form/Item/"
    # Constructing the email content with an HTML table
    email_content = """
        <p>The following items have reached their reorder level:</p>
        <table style='border-collapse: collapse; width: 100%;'>
            <tr style='background-color: #2b47d9; color: white;'>
                <th style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>Item Code</th>
                <th style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>Item Name</th>
                <th style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>Item Group</th>
                <th style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>Current Stock</th>
                <th style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>Monthly Outflow</th>
                <th style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>Reorder Level</th>
                <th style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>Safety Stock</th>
            </tr>
    """

    # Define row colors for zebra striping
    row_color_1 = '#f2f2f2'  # Light grey
    row_color_2 = '#ffffff'  # White

    for index, item in enumerate(items):
        stock_int = int(round(item.get('highest_stock', 0)))
        reorder_level_int = int(round(item.get('reorder_level', 0)))  # Convert to int and round
        safety_stock_int = int(round(item.get('safety_stock', 0)))  # Convert to int and round
        monthly_outflow_int = int(round(item.get('average_monthly_outflow', 0)))  # Convert to int and round
        item_url = f"{base_url}{item.get('name')}"
        # Alternating row color
        if stock_int == 0:
            row_color = '#FFCCCC'
        else:
            row_color = row_color_1 if index % 2 == 0 else row_color_2
        email_content += f"""
            <tr style='background-color: {row_color};'>
                <td style='border: 1px solid #dddddd; text-align: left; padding: 8px;'><a href='{item_url}'>{item["name"]}</a></td>
                <td style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>{item["item_name"]}</td>
                <td style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>{item["item_group"]}</td>
                <td style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>{stock_int}</td>
                <td style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>{monthly_outflow_int}</td>
                <td style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>{reorder_level_int}</td>
                <td style='border: 1px solid #dddddd; text-align: left; padding: 8px;'>{safety_stock_int}</td>
            </tr>
        """
    
    email_content += "</table>"
    
    # Creating email context
    email_context = {
        'recipients': 'alexandre.ringwald@amf.ch',
        'content': email_content,
        'subject': "Safety Stock Report on Items",
        'communication_medium': 'Email',
        'send_email': True,
        'cc': 'alexandre.trachsel@amf.ch',
        'attachments': [],  # Add any attachments if necessary
    }

    # Creating communication and sending email
    try:
        comm = make(**email_context)
        print("'make' email return successfully.")
        return comm
    except AttributeError as e:
        print(f"AttributeError occurred: {str(e)}")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")

    return None

def calculate_real_lead_time(item=None):
    print(item)
    # Query Purchase Receipt Items with their corresponding Purchase Order Items
    query = """
        SELECT
            pri.item_code AS item_code,
            pri.creation AS receipt_date,
            poi.schedule_date AS order_date,
            poi.creation AS purchase_order,
            pri.parent AS purchase_receipt
        FROM
            `tabPurchase Receipt Item` pri
        INNER JOIN
            `tabPurchase Order Item` poi ON poi.name = pri.purchase_order_item
        WHERE
            pri.docstatus = 1 AND poi.docstatus = 1
    """
    if item:
        query += f" AND pri.item_code = '{item}'"
    data = frappe.db.sql(query, as_dict=True)
    
     # Calculate the lead time for each item
    lead_time_data = []
    for entry in data:
        if entry.get("receipt_date") and entry.get("order_date"):
            lead_time = date_diff(entry["receipt_date"], entry["order_date"])
            # Only include positive lead times
            if lead_time >= 0:
                lead_time_data.append({
                    "item_code": entry["item_code"],
                    "purchase_order": entry["purchase_order"],
                    "purchase_receipt": entry["purchase_receipt"],
                    "lead_time": lead_time
                })
    
    # Group lead times by item_code
    grouped_lead_times = {}
    for record in lead_time_data:
        item_code = record["item_code"]
        if item_code not in grouped_lead_times:
            grouped_lead_times[item_code] = []
        grouped_lead_times[item_code].append(record["lead_time"])
    
    # Calculate lead time statistics for each item
    item_lead_time_stats = {}
    for item_code, lead_times in grouped_lead_times.items():
        stats = calculate_lead_time_statistics(lead_times)
        item_lead_time_stats[item_code] = stats

    # Add the statistics to each record in lead_time_data
    for record in lead_time_data:
        record["lead_time_stats"] = item_lead_time_stats[record["item_code"]]

    # Log or print the lead time data
    #for record in lead_time_data:
        #frappe.log(f"Item: {record['item_code']} / Lead Time: {record['lead_time']} days")
        #print(f"Item: {record['item_code']} / PREC: {record['purchase_receipt']} / "
        #      f"Lead Time: {record['lead_time']} days / Stats: {record['lead_time_stats']}")
        
    return record['lead_time_stats']

def filter_negative_values(lead_times):
    """
    Removes negative values from the list of lead times.

    Args:
        lead_times (list): List of lead times (can include negative values).

    Returns:
        list: List with negative values removed.
    """
    return [lt for lt in lead_times if lt > 0]

def calculate_lead_time_statistics(lead_times=None):
    """
    Calculate lead time statistics and filter outliers.
    
    Args:
        lead_times (list): List of lead time values in days.
        
    Returns:
        dict: Dictionary containing lead time statistics.
    """
    
    #lead_times = [318, 350, 122, 20, 137, 96, 0, 50, 146, 124, 158, 318, 158, 131]
    
    if not lead_times:
        return {"Error": "Lead time list is empty."}

    # Filter out zeros or invalid values if needed
    lead_times = filter_negative_values(lead_times)
    if not lead_times:
        return {"Error": "No valid lead times after filtering."}
    # Convert to a pandas DataFrame for easier manipulation
    df = pd.DataFrame({"Lead Time": lead_times})

    # Key statistics
    mean_lead_time = float(np.mean(lead_times))  # Convert to float
    median_lead_time = float(np.median(lead_times))  # Convert to float
    mode_lead_time = (
        float(df["Lead Time"].mode().iloc[0]) if not df["Lead Time"].mode().empty else None
    )
    min_lead_time = int(np.min(lead_times))  # Convert to int
    max_lead_time = int(np.max(lead_times))  # Convert to int
    range_lead_time = max_lead_time - min_lead_time

    # Remove outliers using IQR
    q1 = np.percentile(lead_times, 25)
    q3 = np.percentile(lead_times, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    filtered_lead_times = [
        int(lt) for lt in lead_times if lower_bound <= lt <= upper_bound
    ]

    # Recalculate after removing outliers
    filtered_mean = float(np.mean(filtered_lead_times)) if filtered_lead_times else None
    filtered_median = float(np.median(filtered_lead_times)) if filtered_lead_times else None
    filtered_std_dev = float(np.std(filtered_lead_times, ddof=1)) if filtered_lead_times else None

    # Return results as a dictionary
    results = {
        "Mean": mean_lead_time,
        "Median": median_lead_time,
        "Mode": mode_lead_time,
        "Min": min_lead_time,
        "Max": max_lead_time,
        "Range": range_lead_time,
        "Filtered Mean": filtered_mean,
        "Filtered Median": filtered_median,
        "Filtered Std Dev": filtered_std_dev,
        "Outliers Removed": len(lead_times) - len(filtered_lead_times),
        "Filtered Data": filtered_lead_times,
    }
    
    print(results)
    
    return int(filtered_mean), int(filtered_std_dev)