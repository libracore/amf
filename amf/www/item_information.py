import json
import frappe

@frappe.whitelist()
def get_item_information(item_code):
    item = frappe.get_doc('Item', item_code)

    if not item:
        frappe.throw("Item not found.")

    warehouse_info = []
    
    # Use frappe.db.sql() to execute the SQL query and get the actual_qty from tabBin
    stock_entries = frappe.db.sql("""
        SELECT warehouse, actual_qty
        FROM `tabBin`
        WHERE item_code = %s AND warehouse not rlike 'AMF_OLD'
    """, (item_code,), as_dict=True)

    # Group quantities by warehouse
    warehouse_balances = {}
    for entry in stock_entries:
        if entry.warehouse not in warehouse_balances:
            warehouse_balances[entry.warehouse] = 0
        warehouse_balances[entry.warehouse] = entry.actual_qty
        # print("entry.actual_qty:",entry.actual_qty)
        # print("entry.warehouse:",entry.warehouse)

    # Convert the warehouse_balances dictionary to the warehouse_info list
    for warehouse, balance in warehouse_balances.items():
        #warehouse_info.append({"name": warehouse, "balance": balance})
        warehouse_data = {"name": warehouse, "balance": balance}
        # If the item has batches, fetch the batches for the warehouse
        if item.has_batch_no:
            batches = frappe.get_all("Batch", filters={"item": item_code}, fields=["name"])
            print(batches)
            warehouse_data["batches"] = [batch["name"] for batch in batches]

        # If the item has serial numbers, fetch the serial numbers for the warehouse
        if item.has_serial_no:
            serial_nos = frappe.get_all("Serial No", filters={"item_code": item_code, "warehouse": warehouse}, fields=["name"])
            warehouse_data["serial_nos"] = [serial["name"] for serial in serial_nos]

        warehouse_info.append(warehouse_data)

    # print("item.item_name:", item.item_name)
    # print("warehouse_info:", warehouse_info)
    return {
        "item_name": item.item_name,
        "warehouse_info": warehouse_info
    }

@frappe.whitelist()
def create_stock_reconciliation(item_code, item_name, warehouses):
    
    # Ensure warehouses is a list of dictionaries
    if isinstance(warehouses, str):
        warehouses = json.loads(warehouses)
    
    stock_reconciliation = frappe.new_doc("Stock Reconciliation")
    
    for warehouse in warehouses:
        # Only add warehouses where the update value is not null or empty
        if warehouse["update_value"]:
            stock_reconciliation.append("items", {
                "item_code": item_code,
                "item_name": item_name,
                "warehouse": warehouse["name"],
                "qty": warehouse["update_value"],  # Assuming the fieldname for quantity in Stock Reconciliation Item is 'qty'
                "batch_no": warehouse["batches"],
                "serial_no": warehouse["serial_nos"]

            })

    stock_reconciliation.save()
    return "success"
