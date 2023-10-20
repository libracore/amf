import json
import frappe

@frappe.whitelist()
def get_item_information(item_code):
    try:
        item = frappe.get_doc('Item', item_code)
        # ... process the item as required

    except frappe.DoesNotExistError:
        print("Item not found.")
        return {"status": "not_found"}

    except Exception as e:  # Catch any other unexpected exceptions
        print("An error occurred:", e)
        frappe.log_error(frappe.get_traceback(), "Error in get_item_information")
        return {"status": "error", "message": str(e)}

    warehouse_info = []
    
    # Use frappe.db.sql() to execute the SQL query and get the actual_qty from tabBin
    stock_entries = frappe.db.sql("""
        SELECT warehouse, actual_qty
        FROM `tabBin`
        WHERE item_code = %s AND warehouse not rlike 'AMF_OLD'
    """, (item_code,), as_dict=True)
    #print(stock_entries)
    # Group quantities by warehouse
    warehouse_balances = {}
    for entry in stock_entries:
        if entry.warehouse not in warehouse_balances:
            warehouse_balances[entry.warehouse] = 0
        warehouse_balances[entry.warehouse] = entry.actual_qty
        #print("entry.actual_qty:",entry.actual_qty)
        #print("entry.warehouse:",entry.warehouse)
    if 'Quality Control - AMF21' not in warehouse_balances:
        warehouse_balances['Quality Control - AMF21'] = 0
    if 'Main Stock - AMF21' not in warehouse_balances:
        warehouse_balances['Main Stock - AMF21'] = 0
    if 'Assemblies - AMF21' not in warehouse_balances:
        warehouse_balances['Assemblies - AMF21'] = 0
    if 'Scrap - AMF21' not in warehouse_balances:
        warehouse_balances['Scrap - AMF21'] = 0

    print(warehouse_balances)

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
    print(warehouses)
    stock_reconciliation = frappe.new_doc("Stock Reconciliation")
    stock_reconciliation.ignore_remove_items_with_no_change = 1
    for warehouse in warehouses:
        # Only add warehouses where the update value is not null or empty
        if warehouse["update_value"]:
            item_entry = {
                "item_code": item_code,
                "item_name": item_name,
                "warehouse": warehouse["name"],
                "qty": warehouse["update_value"]  # Assuming the fieldname for quantity in Stock Reconciliation Item is 'qty'
            }
            
            # Check if batches exist and are not empty
            batch_no = warehouse.get("batches")
            if batch_no:
                # Check if the batch exists in the ERP database
                existing_batch = frappe.get_value("Batch", {"name": batch_no})
                if not existing_batch:
                    # If the batch doesn't exist, create a new batch
                    batch = frappe.new_doc("Batch")
                    batch.item = item_code
                    batch.batch_id = batch_no
                    # Add any other necessary fields for the batch here
                    batch.save()
                item_entry["batch_no"] = batch_no
            
            # Check if serial_nos exist and are not empty
            if warehouse.get("serial_nos"):
                item_entry["serial_no"] = warehouse["serial_nos"]
            print(item_entry)
            stock_reconciliation.append("items", item_entry)

    stock_reconciliation.save()
    return "success"

from frappe.model.mapper import get_mapped_doc

@frappe.whitelist()
def zero_out_stock_for_items(name):
    source_stock_reconciliation = frappe.get_doc("Stock Reconciliation", name)
    print(source_stock_reconciliation)
    # Create a new Stock Reconciliation document
    new_stock_reconciliation = frappe.new_doc("Stock Reconciliation")
    new_stock_reconciliation.ignore_remove_items_with_no_change = 1
    item_code = ""
    for item in source_stock_reconciliation.items:
        if (item_code != item.item_code):
            item_code = item.item_code
            print("item_code:",item_code)
            # Get all warehouses and batches where this item exists
            warehouses = frappe.db.sql("""SELECT * FROM `tabWarehouse` WHERE name NOT RLIKE 'OLD' AND disabled = 0""", as_dict=True)
            batches = frappe.db.sql("""SELECT name FROM `tabBatch` WHERE item = %s""", item_code, as_dict=True)

            for warehouse in warehouses:
                for batch in batches:
                    new_item_entry = {
                        "item_code": item_code,
                        "item_name": item.item_name,
                        "warehouse": warehouse.name,
                        "qty": 0,  # Setting quantity to zero
                        "batch_no": batch.name
                    }
                    new_stock_reconciliation.append("items", new_item_entry)

    new_stock_reconciliation.save()
    
    return "success"

