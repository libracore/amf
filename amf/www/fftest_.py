import frappe
from frappe import _, ValidationError
from frappe.utils import flt
from datetime import datetime
from erpnext.stock.doctype.stock_entry.stock_entry import get_additional_costs

@frappe.whitelist()
def make_stock_entry(work_order_id, serial_no_id=None):
    """
    Creates and submits a Stock Entry document for manufacturing
    based on the provided Work Order. Optionally handles serial numbers.

    :param work_order_id: The ID of the Work Order to manufacture against.
    :param serial_no_id: (Optional) The serial number to be used for the final item.
    :return: The submitted Stock Entry doc (if successful) or an error dict.
    """
    logger = frappe.logger()
    logger.info(f"make_stock_entry called with Work Order: {work_order_id} and Serial No: {serial_no_id}")
    
    try:
        # Validate the existence of the Work Order
        if not frappe.db.exists("Work Order", work_order_id):
            msg = _("Work Order ID does not exist.")
            logger.error(msg)
            raise ValidationError(msg)
        
        work_order = frappe.get_doc("Work Order", work_order_id)

        # Check produced quantity
        if (work_order.qty - work_order.produced_qty) <= 0:
            msg = _("Invalid produced quantity in Work Order.")
            logger.error(msg)
            raise ValidationError(msg)

        # Determine WIP warehouse if skip_transfer is not set
        wip_warehouse = "Main Stock - AMF21"
        if not work_order.wip_step:
            wip_warehouse = "Work In Progress - AMF21"

        # Initialize Stock Entry
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = 'Manufacture'
        stock_entry.work_order = work_order_id
        stock_entry.company = work_order.company
        stock_entry.from_bom = 1
        stock_entry.bom_no = work_order.bom_no
        stock_entry.use_multi_level_bom = 0
        stock_entry.fg_completed_qty = 1  # Hard-coded to force 1 by 1 testing irl; adjust as needed

        # Validate BOM
        if not frappe.db.exists("BOM", work_order.bom_no):
            msg = _("BOM does not exist.")
            logger.error(msg)
            raise ValidationError(msg)

        stock_entry.inspection_required = 0

        # Set warehouse and project fields
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = "Main Stock - AMF21"
        stock_entry.project = work_order.project

        # (Optional) Load any additional costs for manufacturing.
        # Uncomment and adjust if needed:
        # additional_costs = get_additional_costs(work_order, fg_qty=stock_entry.fg_completed_qty)
        # stock_entry.set("additional_costs", additional_costs)

        # Configure Stock Entry items
        stock_entry.set_stock_entry_type()

        # Optionally get items from BOM – comment or uncomment as you need:
        stock_entry.get_items()

        # Calculate BOM item quantities
        bom = frappe.get_doc("BOM", stock_entry.bom_no)
        bom_item_quantities = {
            item.item_code: item.qty * stock_entry.fg_completed_qty for item in bom.items
        }

        # Update items with correct quantities
        for item in stock_entry.items:
            if item.item_code in bom_item_quantities:
                item.qty = flt(bom_item_quantities[item.item_code])
                item.transfer_qty = flt(item.qty * item.conversion_factor)
                item.manual_source_warehouse_selection = 1
                item.s_warehouse = "Work In Progress - AMF21"

        # Handle serial numbers on the last item
        if stock_entry.items:
            last_item = stock_entry.items[-1]
            if frappe.db.get_value("Item", last_item.item_code, "has_serial_no") == 1:
                if not serial_no_id:
                    msg = _("Serial number is required for the last item.")
                    logger.error(msg)
                    raise ValidationError(msg)

                # Check if the serial number already exists for this item
                serial_exists = frappe.db.exists({
                    "doctype": "Serial No",
                    "serial_no": serial_no_id,
                    "item_code": last_item.item_code
                })

                if serial_exists:
                    msg = _("Serial number already exists for this item in the database.")
                    logger.error(msg)
                    raise ValidationError(msg)

                last_item.serial_no = serial_no_id
                last_item.manual_target_warehouse_selection = 1
                last_item.t_warehouse = "Main Stock - AMF21"

            # Assign or create a batch if needed
            last_item.auto_batch_no_generation = 0
            last_item.batch_no = assign_or_create_batch_for_last_item(work_order_id, last_item)

        # Save and submit the Stock Entry
        stock_entry.save()
        
        # Update rate and availability
        update_rate_and_availability_ste(stock_entry, None)
        
        stock_entry.submit()
        logger.info(f"Stock Entry {stock_entry.name} created and submitted successfully.")

        return stock_entry

    except ValidationError as ve:
        frappe.log_error(title="Validation Error in make_stock_entry", message=frappe.get_traceback())
        return {"error": str(ve)}
    except Exception as e:
        frappe.log_error(title="Unexpected Error in make_stock_entry", message=frappe.get_traceback())
        return {"error": str(e)}


def assign_or_create_batch_for_last_item(work_order_id, last_item):
    """
    Checks existing batches for a matching work order and item code.
    Creates a new batch if none is found. Returns the assigned or newly created batch name.

    :param work_order_id: The ID of the Work Order used to find or create the batch.
    :param last_item: The last item row in the Stock Entry for which the batch is needed.
    :return: Name of the assigned or newly created batch.
    """
    logger = frappe.logger()
    logger.info("assign_or_create_batch_for_last_item called.")

    has_batch_no = frappe.db.get_value("Item", last_item.item_code, "has_batch_no")
    if has_batch_no == 1:
        # Attempt to find an existing batch
        existing_batch_name = frappe.db.get_value(
            "Batch",
            filters={"work_order": work_order_id, "item": last_item.item_code},
            fieldname="name"
        )

        if existing_batch_name:
            logger.info(f"Found existing batch {existing_batch_name} for Work Order {work_order_id}.")
            return existing_batch_name
        else:
            logger.info(f"No existing batch for Work Order {work_order_id}; creating a new one.")
            work_order_doc = frappe.get_doc("Work Order", work_order_id)

            batch = frappe.new_doc("Batch")
            batch.name = create_batch_name(last_item.item_code, work_order_doc.qty)
            batch.batch_id = batch.name
            batch.item = last_item.item_code
            batch.work_order = work_order_id
            batch.insert(ignore_permissions=True)
            frappe.db.commit()

            return batch.name
    else:
        logger.info("Item does not require a batch. Returning None.")
        return None


def create_batch_name(item_code):
    """
    Construct a batch name using:
      1. The current date/time in YYYYMMDDHHMMSS format
      2. The item code
      3. The constant string 'AMF'

    Example output: 20250128121030 ITEM-ABC AMF
    """
    timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')  
    return f"{timestamp_str} {item_code} AMF"


def update_rate_and_availability_ste(doc, method):
    """
    Helper function to fetch and update item rates and check availability.
    Called on the Stock Entry document before saving/submitting.

    :param doc: The Stock Entry document to update.
    :param method: (Not used) Standard Frappe hook method parameter.
    """
    logger = frappe.logger()
    logger.info("update_rate_and_availability_ste called.")
    print("update_rate_and_availability_ste called.")
    doc.get_stock_and_rate()
    return
