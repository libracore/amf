# custom_stock_check.py
import frappe
from frappe import _


@frappe.whitelist()
def check_sales_order_stock_availability(sales_order_name):
    sales_order = frappe.get_doc("Sales Order", sales_order_name)
    items_shortage_details = []
    for item in sales_order.items:
        highest_stock = 0  # Initialize variable to store the highest stock value
        all_warehouses = frappe.get_all("Warehouse", filters={"disabled": 0})
        # Filter out specific warehouses
        filtered_warehouses = [
            wh
            for wh in all_warehouses
            if "AMF_OLD" not in wh.name and "Scrap - AMF21" not in wh.name
        ]

        for warehouse in filtered_warehouses:

            current_stock = (
                frappe.db.get_value(
                    "Bin",
                    {"item_code": item.item_code, "warehouse": warehouse.name},
                    "actual_qty",
                )
                or 0
            )
            # Update the highest stock value if the current stock is higher
            if current_stock > highest_stock:
                highest_stock = current_stock
        # If the highest stock is less than the quantity ordered, record the shortage and stock level
        if highest_stock < item.qty:
            shortage_detail = f"Item: {item.item_code}, Ordered: {item.qty}, Available: {highest_stock}"
            items_shortage_details.append(shortage_detail)

    # Format the shortage message for better readability
    if items_shortage_details:
        # Start the table with headers for better clarity and specific styling
        shortage_message = (_("<strong>Shortage in items as of today:</strong>") + "<br><table style=\"width:100%; border-collapse: collapse; border: 2px solid black;\">" +
                            "<tr style=\"background-color: #2b47d9; color: white;\">" +
                            "<th style=\"border: 1px solid grey; padding: 8px; text-align: left; border-bottom: 1px solid black;\">Item Code</th>" +
                            "<th style=\"border: 1px solid grey; padding: 8px; text-align: left; border-bottom: 1px solid black;\">Ordered Qty</th>" +
                            "<th style=\"border: 1px solid grey; padding: 8px; text-align: left; border-bottom: 1px solid black;\">Available Stock</th>" +
                            "</tr>")


        # Loop through each item in shortage to add a row to the table
        for detail in items_shortage_details:
            item_code, ordered_qty, available_stock = detail.split(", ")
            shortage_message += f"<tr>" \
                                f"<td style=\"border: 1px solid lightgrey; padding: 8px;\">{item_code.split(': ')[1]}</td>" \
                                f"<td style=\"border: 1px solid lightgrey; padding: 8px;\">{ordered_qty.split(': ')[1]}</td>" \
                                f"<td style=\"border: 1px solid lightgrey; padding: 8px;\">{available_stock.split(': ')[1]}</td>" \
                                "</tr>"

        shortage_message += "</table>"
        return shortage_message
    else:
        return _("Stock OK")
