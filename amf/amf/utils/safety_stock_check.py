import frappe
import math
import datetime
import statistics

def update_safety_stock_and_check_levels():
    # Get the current year and calculate last year's dates
    current_year = datetime.datetime.now().year
    last_year_start = datetime.date(current_year - 1, 1, 1)
    last_year_end = datetime.date(current_year - 1, 12, 31)

    items = frappe.get_all("Item", fields=["name", "safety_stock", "reorder"])
    for item in items:
        # Fetch total outflow for this item for the last year
        total_outflow = frappe.db.sql("""
            SELECT SUM(actual_qty)
            FROM `tabStock Ledger Entry`
            WHERE item_code = %s
            AND posting_date BETWEEN %s AND %s
            AND actual_qty < 0
        """, (item['name'], last_year_start, last_year_end))
        # The SQL query returns a list of tuples, so we need to extract the actual value
        total_outflow = total_outflow[0][0] if total_outflow and total_outflow[0][0] else 0

        # Calculate safety stock as 25% more than the average monthly outflow
        average_monthly_outflow = abs(total_outflow / 12)
        safety_stock = math.ceil(average_monthly_outflow * 1.25)  # Add 25% buffer
        # Update safety stock value in Item doctype
        frappe.db.set_value("Item", item['name'], "safety_stock", safety_stock)
        
        # Now let's check the stock levels against this new safety stock
        highest_stock = 0  # Initialize variable to store the highest stock value
        all_warehouses = frappe.get_all("Warehouse")
        filtered_warehouses = [wh for wh in all_warehouses if "AMF_OLD" not in wh.name]
        
        for warehouse in filtered_warehouses:
            current_stock = frappe.db.get_value("Bin", {"item_code": item['name'], "warehouse": warehouse.name}, "actual_qty") or 0
            # Update the highest stock value if the current stock is higher
            if current_stock > highest_stock:
                highest_stock = current_stock
        
        if highest_stock < item['safety_stock']:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item['name'], "reorder", 1)
            print(f"Setting 'reorder' to 1 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']}")

def check_stock_levels():
    # Constants
    Z = 1.64  # Z-score for 95% service level
    avg_lead_time = 90  # Average lead time in days
    std_dev_lead_time = 15  # Standard deviation of lead time in days
    
    # Get the current year and calculate last year's dates
    current_year = datetime.datetime.now().year
    
    items = frappe.get_all("Item", fields=["name", "safety_stock", "reorder", "item_group"])

    # Test Line
    # items = frappe.get_all("Item", fields=["name", "safety_stock", "reorder", "item_group"], filters={"name": "SPL.1210-P"})

    for item in items:
        # print(item)
        # Fetch outflow for this item for each month of the last year
        monthly_outflows = []
        for month in range(1, 13):
            monthly_outflow = frappe.db.sql("""
                SELECT SUM(actual_qty)
                FROM `tabStock Ledger Entry`
                WHERE item_code = %s
                AND MONTH(posting_date) = %s
                AND YEAR(posting_date) = %s
                AND actual_qty < 0 AND voucher_type NOT RLIKE 'Stock Reconciliation'
            """, (item['name'], month, current_year - 1))
            
            monthly_outflow = monthly_outflow[0][0] if monthly_outflow and monthly_outflow[0][0] else 0
            monthly_outflows.append(-monthly_outflow)  # Converting outflow to positive numbers for demand
        # Calculate standard deviation and average of monthly outflows (demands)
        std_dev_demand = statistics.stdev(monthly_outflows) / 30
        print(monthly_outflows)
        avg_demand = statistics.mean(monthly_outflows) / 30  # Assuming 30 days in a month to get daily demand
        # Calculate safety stock using the composite distribution formula
        safety_stock = Z * math.sqrt((avg_demand * std_dev_lead_time)**2 + (avg_lead_time * std_dev_demand)**2)
        
        # safety_stock = (Z * std_dev_demand * math.sqrt(avg_lead_time)) + (Z * avg_demand * std_dev_lead_time)
        
        if(safety_stock < 1):
            safety_stock = 0
        print("Safety Stock: " + str(safety_stock) + " for Item: " + item['name'])
        # Update safety stock value in Item doctype
        frappe.db.set_value("Item", item['name'], "safety_stock", safety_stock)

        # Now let's check the stock levels against this new safety stock
        highest_stock = 0  # Initialize variable to store the highest stock value
        all_warehouses = frappe.get_all("Warehouse")
        filtered_warehouses = [wh for wh in all_warehouses if "AMF_OLD" not in wh.name]
        
        for warehouse in filtered_warehouses:
            current_stock = frappe.db.get_value("Bin", {"item_code": item['name'], "warehouse": warehouse.name}, "actual_qty") or 0
            # Update the highest stock value if the current stock is higher
            if current_stock > highest_stock:
                highest_stock = current_stock
        
        if highest_stock < item['safety_stock']:
            # Set the "Reorder" checkbox to True (checked)
            frappe.db.set_value("Item", item['name'], "reorder", 1)
            print(f"Setting 'reorder' to 1 / Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']}")
        
        # Test Line
        # print(f"Item: {item['name']} / Stock Value = {highest_stock} / Safety Stock = {item['safety_stock']}")
