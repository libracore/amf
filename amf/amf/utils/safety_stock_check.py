from frappe.core.doctype.communication.email import make
import frappe
import math
import datetime
import statistics


def update_safety_stock_and_check_levels():
    # Get the current year and calculate last year's dates
    current_year = datetime.datetime.now().year
    last_year_start = datetime.date(current_year - 1, 1, 1)
    last_year_end = datetime.date(current_year - 1, 12, 31)

    items = frappe.get_all("Item", filters={'is_stock_item': 1, 'disabled': 0}, fields=["name", "safety_stock", "reorder"])
    for item in items:
        # Fetch total outflow for this item for the last year
        total_outflow = frappe.db.sql(
            """
            SELECT SUM(actual_qty)
            FROM `tabStock Ledger Entry`
            WHERE item_code = %s
            AND posting_date BETWEEN %s AND %s
            AND actual_qty < 0
        """,
            (item["name"], last_year_start, last_year_end),
        )
        # The SQL query returns a list of tuples, so we need to extract the actual value
        total_outflow = (
            total_outflow[0][0] if total_outflow and total_outflow[0][0] else 0
        )

        # Calculate safety stock as 25% more than the average monthly outflow
        average_monthly_outflow = abs(total_outflow / 12)
        safety_stock = math.ceil(average_monthly_outflow * 1.25)  # Add 25% buffer
        # Update safety stock value in Item doctype
        frappe.db.set_value("Item", item["name"], "safety_stock", safety_stock)

        # Now let's check the stock levels against this new safety stock
        highest_stock = 0  # Initialize variable to store the highest stock value
        all_warehouses = frappe.get_all("Warehouse")
        filtered_warehouses = [wh for wh in all_warehouses if "AMF_OLD" not in wh.name]

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

        if highest_stock < item["safety_stock"]:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item["name"], "reorder", 1)
            print(
                f"Setting 'reorder' to 1 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']}"
            )


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

    items = frappe.get_all("Item", filters={'is_stock_item': 1, 'disabled': 0}, fields=["name", "safety_stock", "reorder_level", "reorder", "item_group"])

    # Test Line
    #items = frappe.get_all("Item", fields=["name", "safety_stock", "reorder_level", "reorder", "item_group"], filters={"name": "SPL.3013"})

    for item in items:
        print(item)
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

        # Calculate standard deviation and average of monthly outflows (demands)
        std_dev_demand = statistics.stdev(monthly_outflows) / 30
        # print(monthly_outflows)
        avg_demand = (statistics.mean(monthly_outflows) / 30)  # Assuming 30 days in a month to get daily demand
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
        frappe.db.set_value("Item", item["name"], "safety_stock", safety_stock)
        frappe.db.set_value("Item", item["name"], "reorder_level", order_point)
        #print("Reorder Level: " + str(order_point) + " for Item: " + item["name"])
        #print("Safety Stock: " + str(safety_stock) + " for Item: " + item["name"])
        # Now let's check the stock levels against this new safety stock
        highest_stock = 0  # Initialize variable to store the highest stock value
        all_warehouses = frappe.get_all("Warehouse")
        filtered_warehouses = [wh for wh in all_warehouses if "AMF_OLD" not in wh.name]

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

        if highest_stock < item["reorder_level"]:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item["name"], "reorder", 1)
            print(f"Setting 'reorder' to 1 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")
        else:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item["name"], "reorder", 0)
            print(f"Setting 'reorder' to 0 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")
        
        # Test Line
        #print(f"Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']} / Reorder Level = {item['reorder_level']}")

@frappe.whitelist()
def sendmail(name, attachments=None):
    print("sendmail")
    # Creating email context
    email_context = {
        'recipients': 'alexandre.ringwald@amf.ch',
        'content': f"<p>Item {name} has reached Reorder Level. Please take necessary actions.</p>",
        'subject': f"Running Low on {name}",
        'doctype': 'Item',
        'name': name,
        'communication_medium': 'Email',
        'send_email': True,
        'attachments': attachments or [],
    }
    
    # Creating communication and sending email
    comm = make(**email_context)
    
    return comm

    # email_args = {
    #     'recipients': 'alexandre.ringwald@amf.ch',
    #     'message': f"<p>Item {name} has reached Reorder Level. Please take necessary actions.</p>",
    #     'subject': f"Running Low on {name}",
    #     'reference_doctype': 'Item',
    #     'reference_name': name,
    # }
    # if attachments:email_args['attachments']=attachments
    # #send mail
    # frappe.enqueue(method=frappe.sendmail, queue='short', timeout=300, **email_args)
