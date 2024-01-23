from erpnext.stock.doctype.stock_entry.stock_entry import get_additional_costs
import frappe
from frappe.utils.data import flt
from frappe import _, ValidationError

@frappe.whitelist()
def make_stock_entry(work_order_id, serial_no_id=None):
    print("make_stock_entry")
    try:
        print("Creating New Stock Entry.")
        
        # Validate work_order_id
        if not frappe.db.exists("Work Order", work_order_id):
            raise ValidationError(_("Work Order ID does not exist."))
        
        work_order = frappe.get_doc("Work Order", work_order_id)
        
        # Validate produced quantity
        if (work_order.qty - work_order.produced_qty) <= 0:
            raise ValidationError(_("Invalid produced quantity in Work Order."))
        
        # Determine WIP warehouse
        if not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group") and not work_order.skip_transfer:
            wip_warehouse = work_order.wip_warehouse
        else:
            wip_warehouse = None  # Add logic to handle this case if necessary
        
        # Initialize and populate Stock Entry
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = 'Manufacture'  # For this example, purpose is hard-coded
        stock_entry.work_order = work_order_id
        stock_entry.company = work_order.company
        stock_entry.from_bom = 1
        stock_entry.bom_no = work_order.bom_no
        stock_entry.use_multi_level_bom = work_order.use_multi_level_bom
        stock_entry.fg_completed_qty = 1  # For this example, fg_completed_qty is hard-coded
        
        # Validate BOM
        if not frappe.db.exists("BOM", work_order.bom_no):
            raise ValidationError(_("BOM does not exist."))
        
        stock_entry.inspection_required = frappe.db.get_value('BOM', work_order.bom_no, 'inspection_required')
        
        # Set warehouse and project fields
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = work_order.fg_warehouse
        stock_entry.project = work_order.project
        
        # Additional costs for manufacturing
        # additional_costs = get_additional_costs(work_order, fg_qty=stock_entry.fg_completed_qty)
        # stock_entry.set("additional_costs", additional_costs)
        
        stock_entry.set_stock_entry_type()
        stock_entry.get_items()
        
        # Fetch and process the BOM
        bom = frappe.get_doc("BOM", stock_entry.bom_no)
        bom_item_quantities = {}
        
        for item in bom.items:
            bom_item_quantities[item.item_code] = item.qty * stock_entry.fg_completed_qty
        
        for item in stock_entry.items:
            if item.item_code in bom_item_quantities:
                item.qty = frappe.utils.flt(bom_item_quantities[item.item_code])
                item.transfer_qty = frappe.utils.flt(item.qty * item.conversion_factor)
        
        # Handle serial numbers
        last_item_idx = len(stock_entry.items) - 1
        last_item = stock_entry.items[last_item_idx]
        
        if frappe.db.get_value("Item", last_item.item_code, "has_serial_no") == 1:
            if not serial_no_id:
                raise ValidationError(_("Serial number is required for the last item."))
            
			# Check if the serial number already exists in the database for this item
            serial_exists = frappe.db.exists({
                "doctype": "Serial No",
                "serial_no": serial_no_id,
                "item_code": last_item.item_code
            })
    
            if serial_exists:
                raise ValidationError(_("Serial number already exists for this item in the database."))
    
            last_item.serial_no = serial_no_id
        
        stock_entry.get_stock_and_rate()
        print(f"Stock Entry: {stock_entry.name}, Rate and Stock Updated")

        # Commit changes
        stock_entry.save()
        stock_entry.submit()
        
        return stock_entry
    
    except ValidationError as ve:
        print(f"Validation Error: {ve}")
        return {"error": str(ve)}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {"error": str(e)}