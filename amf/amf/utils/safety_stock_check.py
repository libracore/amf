from frappe.core.doctype.communication.email import make
import frappe
import math
import datetime
import statistics

def check_stock_levels():
    # Constants
    Z = 1.64  # Z-score for 95% service level
    # avg_lead_time = 90  # Average lead time in days
    # std_dev_lead_time = 15  # Standard deviation of lead time in days
    item_group_data = {
        "Kits": {"lead_time": 30, "std_dev_lead_time": 6},
        "Glass": {"lead_time": 90, "std_dev_lead_time": 20},
        "Cables": {"lead_time": 15, "std_dev_lead_time": 5},
        "Plunger": {"lead_time": 90, "std_dev_lead_time": 20},
        "Syringe": {"lead_time": 90, "std_dev_lead_time": 20},
        "Valve Head": {"lead_time": 15, "std_dev_lead_time": 5},
        "Raw Materials": {"lead_time": 120, "std_dev_lead_time": 30},
        "Electronic Boards": {"lead_time": 90, "std_dev_lead_time": 20},
        "Plug": {"lead_time": 60, "std_dev_lead_time": 10},
        "Valve Seat": {"lead_time": 90, "std_dev_lead_time": 20},
        "Parts": {"lead_time": 15, "std_dev_lead_time": 5},
        "Products": {"lead_time": 30, "std_dev_lead_time": 6}
    }
    # Get the current year and calculate last year's dates
    current_year = datetime.datetime.now().year

    items = frappe.get_all("Item", filters={'is_stock_item': 1, 'disabled': 0}, fields=["name", "item_name", "safety_stock", "reorder_level", "reorder", "item_group", "average_monthly_outflow"])

    # Test Line
    #items = frappe.get_all("Item", fields=["name", "item_name", "safety_stock", "reorder_level", "reorder", "item_group", "average_monthly_outflow"], filters={"name": "SPL.1212-C"})
    items_to_email = []  # Create an empty list to hold items that need reordering
    for item in items:
        #print(item)
        # Fetch outflow for this item for each month of the last year
        monthly_outflows = []
        for month in range(1, 13):
            monthly_outflow = frappe.db.sql(
                """
                SELECT SUM(sle.actual_qty)
                FROM `tabStock Ledger Entry` AS sle
                JOIN `tabItem` AS item ON sle.item_code = item.item_code
                WHERE sle.item_code = %s
                AND MONTH(sle.posting_date) = %s
                AND YEAR(sle.posting_date) = %s
                AND sle.actual_qty < 0 AND sle.voucher_type NOT RLIKE 'Stock Reconciliation' AND item.disabled = 0
            """,
                (item["name"], month, current_year - 1),
            )

            monthly_outflow = (
                monthly_outflow[0][0]
                if monthly_outflow and monthly_outflow[0][0]
                else 0
            )
            monthly_outflows.append(-monthly_outflow)  # Converting outflow to positive numbers for demand

        group_data = item_group_data.get(item['item_group'], {"lead_time": 30, "std_dev_lead_time": 6}) # Default values if needed.
        avg_lead_time = group_data["lead_time"]
        std_dev_lead_time = group_data["std_dev_lead_time"]
        #print("avg_lead_time:",avg_lead_time)
        #print("std_dev_lead_time:",std_dev_lead_time)
        avg_monthly_outflow = float(statistics.mean(monthly_outflows))
        # Calculate standard deviation and average of monthly outflows (demands)
        std_dev_demand = statistics.stdev(monthly_outflows) / 30
        avg_demand = (statistics.mean(monthly_outflows) / 30)  # Assuming 30 days in a month to get daily demand
        
        #print(item["average_monthly_outflow"])
        #print(type(avg_monthly_outflow))
        #print(avg_monthly_outflow)
        # Calculate safety stock using the composite distribution formula
        safety_stock = Z * math.sqrt(
            avg_demand * (std_dev_lead_time) ** 2
            + (avg_lead_time * std_dev_demand) ** 2
        )
        order_point = safety_stock + avg_demand * avg_lead_time
        # safety_stock = (Z * std_dev_demand * math.sqrt(avg_lead_time)) + (Z * avg_demand * std_dev_lead_time)

        if safety_stock < 1:
            safety_stock = 0
        # Update safety stock value in Item doctype
        item["average_monthly_outflow"] = avg_monthly_outflow
        item["safety_stock"] = safety_stock
        item["reorder_level"] = order_point
        #print("Reorder Level: " + str(order_point) + " for Item: " + item["name"])
        #print("Safety Stock: " + str(safety_stock) + " for Item: " + item["name"])
        # Now let's check the stock levels against this new safety stock
        highest_stock = 0  # Initialize variable to store the highest stock value
        all_warehouses = frappe.get_all("Warehouse")
        filtered_warehouses = [wh for wh in all_warehouses if "AMF_OLD" not in wh.name and "Scrap - AMF21" not in wh.name]

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

        item['highest_stock'] = highest_stock  # Assign highest_stock to the item dictionary

        if highest_stock < item["reorder_level"]:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item["name"], "reorder", 1)
            #print(f"Setting 'reorder' to 1 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")
            # Add the item to the items_to_email list
            items_to_email.append(item)
        else:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item["name"], "reorder", 0)
            #print(f"Setting 'reorder' to 0 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")
        
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
    # print(email_content)
    # Creating email context
    email_context = {
        'recipients': ['alexandre.ringwald@amf.ch', 'alexandre.trachsel@amf.ch'],
        'content': email_content,
        'subject': "Safety Stock Report on Items",
        'communication_medium': 'Email',
        'doctype': 'Item',
        'send_email': True,
        'attachments': [],  # Add any attachments if necessary
    }
    
    # Creating communication and sending email
    comm = make(**email_context)
    return comm