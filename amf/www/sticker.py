import frappe
from frappe import _

@frappe.whitelist()
def get_details_for_work_order(work_order_name):
    # Fetch the main Work Order details
    work_order = frappe.get_doc("Work Order", work_order_name)
    if not work_order:
        return {"error": _("No Work Order found for name {0}").format(work_order_name)}
    
    # Initialize your infoDocType structure with details from the Work Order
    infoDocType = {
        "production_item": work_order.production_item,
        "item_name": work_order.item_name,
        "assembly_specialist_start": work_order.assembly_specialist_start,
        "produced_qty": work_order.produced_qty,
        "qrcode": work_order.qrcode,
    }
    
    # Fetch Stock Entries related to the Work Order, excluding "Material Transfer for Manufacture"
    stock_entries = frappe.get_list("Stock Entry",
                                    filters={
                                        "work_order": work_order_name,
                                        "docstatus": 1,
                                        "purpose": ["!=", "Material Transfer for Manufacture"]
                                    },
                                    fields=["name", "purpose", "posting_date", "posting_time"]
                                   )

    # Fetch the child table items for each Stock Entry and find the last item with batch_no or serial_no
    last_item_with_batch_or_serial = None
    rawMatCode = None
    for entry in stock_entries:
        items = frappe.get_all("Stock Entry Detail",
                               filters={"parent": entry.name},
                               fields=["item_code", "item_name", "qty", "batch_no", "serial_no"])
        
        # Filter items with batch_no or serial_no and update rawMatCode if item_code starts with "MAT"
        filtered_items = [item for item in items if item.get("batch_no") or item.get("serial_no")]
        for item in items:
            print(item)
            if item["item_code"].startswith("MAT") and not rawMatCode:
                rawMatCode = f"{item['item_code']} {item['item_name']}"
        
        if filtered_items:
            last_item_with_batch_or_serial = filtered_items[-1]  # Take the last item
        
    # Update infoDocType with details from the last relevant Stock Entry item
    if last_item_with_batch_or_serial:
        infoDocType.update({
            "batch_no": last_item_with_batch_or_serial.get("batch_no", ""),
            "serial_no": last_item_with_batch_or_serial.get("serial_no", ""),
            "rawMat": rawMatCode
        })
    return infoDocType