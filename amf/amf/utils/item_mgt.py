from amf.amf.utils.stock_entry import _get_or_create_log, update_log_entry
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

@frappe.whitelist()
def update_all_item_valuation_rates_enq():
    frappe.enqueue("amf.amf.utils.item_mgt.update_all_item_valuation_rates", queue='long', timeout=15000)
    return None

@frappe.whitelist()
def update_all_item_valuation_rates():
    """
    Updates the 'valuation_rate' for all items in the system.
    The valuation rate is determined based on the following priority:
    1. If a default Bill of Materials (BOM) exists for the item, the valuation rate
       is set to the total cost of the BOM.
    2. If no default BOM exists, the valuation rate is set to the price from the
       last purchase invoice.
    3. If neither of the above is available, no change is made.
    """
    doc = frappe._dict({
        "doctype": "Item",
        "name": f"Valuation Rate Process Run on {now_datetime()}"
    })
    log_id = _get_or_create_log(doc)
    
    # Get all items to process
    items = frappe.get_all("Item", fields=["name", "item_name"], filters={"disabled": 0})
    updated_items = []
    skipped_items = []

    for item_data in items:
        update_log_entry(log_id, f"[{now_datetime()}] Row {item_data}<br>")
        item_doc = frappe.get_doc("Item", item_data.name)
        new_valuation_rate = 0.0

        # 1. Check for a default BOM
        default_bom = frappe.db.get_value("BOM", {"item": item_doc.name, "is_default": 1}, "name")
        update_log_entry(log_id, f"[{now_datetime()}] Row {item_data}: default_bom {default_bom}<br>")
        if default_bom:
            try:
                bom_cost = frappe.db.get_value("BOM", {"name": default_bom}, "total_cost")
                if bom_cost:
                    new_valuation_rate = bom_cost
                    update_log_entry(log_id, f"[{now_datetime()}] Row {item_data}: new_valuation_rate {new_valuation_rate}<br>")
            except Exception as e:
                frappe.log_error(f"Error calculating BOM cost for {item_doc.name}: {e}", "Valuation Rate Update Error")


        # 2. If no BOM rate, check for the last purchase price
        if new_valuation_rate == 0.0:
            last_purchase_rate = frappe.db.get_all(
                "Purchase Invoice Item",
                filters={"item_code": item_doc.name, "docstatus": 1},
                fields=["rate"],
                order_by="creation desc",
                limit=1
            )
            if last_purchase_rate:
                new_valuation_rate = last_purchase_rate[0].rate
                update_log_entry(log_id, f"[{now_datetime()}] Row {item_data}: last_purchase_rate[0].rate {new_valuation_rate}<br>")

        # 3. Update the item's valuation rate if a new rate was found
        if new_valuation_rate > 0.0 and item_doc.valuation_rate != new_valuation_rate:
            try:
                item_doc.valuation_rate = new_valuation_rate
                item_doc.save(ignore_permissions=True)
                updated_items.append({"item": item_doc.name, "rate": new_valuation_rate})
                update_log_entry(log_id, f"[{now_datetime()}] Row {item_data}: finale rate {new_valuation_rate}<br>")
            except Exception as e:
                frappe.log_error(f"Error saving item {item_doc.name}: {e}", "Valuation Rate Update Error")
        else:
            skipped_items.append({"item": item_doc.name, "reason": "No default BOM cost or last purchase price found, or rate is unchanged."})

    # Commit the changes
    frappe.db.commit()
    
    update_log_entry(log_id, f"[{now_datetime()}] Valuation Rate Update Complete.<br>"
                    f"Updated {len(updated_items)} items.<br>"
                    f"Skipped {len(skipped_items)} items.<br>")
