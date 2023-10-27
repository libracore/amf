import frappe
from amf.amf.utils.qr_code_generator import generate_qr_code

@frappe.whitelist()
def generate_serial_number_qr_codes(stock_entry):
    doc = frappe.get_doc("Stock Entry", stock_entry)
    stock_entry_qr = []
    for item in doc.items:
        if item.serial_no:
            serial_numbers = item.serial_no.split('\n')
            for serial_number in serial_numbers:
                if serial_number.strip():
                    qr_code_base64 = generate_qr_code(serial_number)
                    stock_entry_qr.append({"serial_number": serial_number, "qr_code": qr_code_base64})
                    # Create a new child table entry for each QR code
                    doc.append('stock_entry_qr', {"serial_number": serial_number, "qr_code": qr_code_base64})
    doc.save()  # Save the document to persist the new child table entries
    doc.reload()
    return stock_entry_qr

def update_sales_order(doc, method):
    # Dictionary to store aggregated quantities
    item_qty_map = {}
    print("doc.items:", doc.items)
    # Loop through the items in the Delivery Note
    sales_order_ref = None
    for item in doc.items:
        if sales_order_ref == None:
            sales_order_ref = item.against_sales_order
        item_code = item.item_code
        quantity = item.qty
        batch = item.batch_no
        print("item_code:", item_code)
        print("quantity:", quantity)
        print("batch:", batch)
        # Aggregate the quantity based on item code
        if item_code in item_qty_map:
            item_qty_map[item_code] += quantity
        else:
            item_qty_map[item_code] = quantity
    print("item_qty_map:", item_qty_map)
    print("sales_order_ref:", sales_order_ref)
    # Get the Sales Order linked with the Delivery Note
    sales_order = frappe.get_doc("Sales Order", sales_order_ref)

    # Loop through the items in the Sales Order and update the delivered quantity
    for item in sales_order.items:
        item_code = item.item_code

        if item_code in item_qty_map:
            # Update the delivered_qty field (assuming it exists)
            item.delivered_qty = item_qty_map[item_code]
    
    # Get the DocType
    doctype = frappe.get_doc("DocType", "Sales Order Item")

    # Loop through the fields to find the one you want
    for field in doctype.fields:
        if field.fieldname == 'delivered_qty':
            # Change the "Allow on Submit" setting
            if field.allow_on_submit == 0:
                field.allow_on_submit = 1

    # Save the changes
    doctype.save()

    # Bypass read-only restriction
    # sales_order.flags.ignore_permissions = True
    
    # Save the updated Sales Order
    sales_order.save()