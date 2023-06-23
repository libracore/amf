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
        warehouse_info.append({"name": warehouse, "balance": balance})

    # print("item.item_name:", item.item_name)
    # print("warehouse_info:", warehouse_info)
    return {
        "item_name": item.item_name,
        "warehouse_info": warehouse_info
    }