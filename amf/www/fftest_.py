import frappe
from frappe import _, ValidationError
from frappe.utils import flt
from datetime import datetime
# from erpnext.stock.doctype.stock_entry.stock_entry import get_additional_costs

@frappe.whitelist()
def make_stock_entry(work_order_id, serial_no_id=None):
    """
    Create a Stock Entry for the given Work Order, optionally specifying a serial number
    for the finished item.

    :param work_order_id: The name/ID of the Work Order document (string).
    :param serial_no_id: The optional serial number to link to the finished item (string).
    :return: On success, returns the submitted Stock Entry doc as a dict.
             On error, returns a dict with a key "error" containing the error message.
    """

    logger = frappe.logger("FFTest")  # Adjust logger name as needed

    try:
        # ---------------------------------------------------------------------
        # Preliminary Validations
        # ---------------------------------------------------------------------
        if not work_order_id:
            raise ValidationError(_("Work Order ID is missing."))

        if not frappe.db.exists("Work Order", work_order_id):
            raise ValidationError(_("Work Order <b>{0}</b> does not exist.").format(work_order_id))

        work_order = frappe.get_doc("Work Order", work_order_id)

        # Check if there's any quantity left to produce
        remaining_qty = (work_order.qty - work_order.produced_qty)
        if remaining_qty <= 0:
            raise ValidationError(_("No more quantity left to produce in Work Order <b>{0}</b>.").format(work_order_id))

        # Ensure BOM is valid
        if not work_order.bom_no:
            raise ValidationError(_("No BOM linked to Work Order <b>{0}</b>.").format(work_order_id))
        if not frappe.db.exists("BOM", work_order.bom_no):
            raise ValidationError(_("BOM <b>{0}</b> does not exist.").format(work_order.bom_no))

        # ---------------------------------------------------------------------
        # Determine WIP warehouse (if needed) and initialize Stock Entry
        # ---------------------------------------------------------------------
        wip_warehouse = None
        # This checks if the WIP Warehouse is valid and not a group warehouse
        # and also that the WO does not skip transfer.
        if (work_order.wip_warehouse
            and not frappe.db.get_value("Warehouse", work_order.wip_warehouse, "is_group")
            and not work_order.skip_transfer):
            wip_warehouse = work_order.wip_warehouse

        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = 'Manufacture'  # Purpose is hard-coded for this example
        stock_entry.work_order = work_order.name
        stock_entry.company = work_order.company
        stock_entry.from_bom = 1
        stock_entry.bom_no = work_order.bom_no
        stock_entry.use_multi_level_bom = work_order.use_multi_level_bom

        # Hard-coding 1 as the completed qty for demonstration
        stock_entry.fg_completed_qty = 1

        # If BOM requires inspection
        stock_entry.inspection_required = frappe.db.get_value(
            "BOM", 
            work_order.bom_no, 
            "inspection_required"
        )

        # Set source (WIP) and target (FG) warehouses
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = work_order.fg_warehouse
        stock_entry.project = work_order.project

        # (Optional) Additional manufacturing costs
        # additional_costs = get_additional_costs(work_order, fg_qty=stock_entry.fg_completed_qty)
        # stock_entry.set("additional_costs", additional_costs)

        # ---------------------------------------------------------------------
        # Populate Items from BOM
        # ---------------------------------------------------------------------
        stock_entry.set_stock_entry_type()
        stock_entry.get_items()  # fetches items from BOM

        bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
        # Build a dict of required item_code -> quantity
        bom_item_quantities = {
            itm.item_code: (itm.qty * stock_entry.fg_completed_qty)
            for itm in bom_doc.items
        }

        # Update item rows in the stock entry
        for item_row in stock_entry.items:
            if item_row.item_code in bom_item_quantities:
                item_row.qty = flt(bom_item_quantities[item_row.item_code])
                item_row.transfer_qty = flt(item_row.qty * item_row.conversion_factor)

        # ---------------------------------------------------------------------
        # Handle Serial Number (on the "last item" row)
        # ---------------------------------------------------------------------
        if not stock_entry.items:
            raise ValidationError(_("No items were added to the Stock Entry."))

        last_item = stock_entry.items[-1]

        # If last item requires a serial number, validate or raise
        if frappe.db.get_value("Item", last_item.item_code, "has_serial_no") == 1:
            if not serial_no_id:
                raise ValidationError(_("Serial number is required for item <b>{0}</b>.").format(last_item.item_code))

            # Check if this serial number already exists for that item
            serial_exists = frappe.db.exists({
                "doctype": "Serial No",
                "serial_no": serial_no_id,
                "item_code": last_item.item_code
            })

            if serial_exists:
                raise ValidationError(
                    _("Serial number <b>{0}</b> already exists for item <b>{1}</b>.").format(serial_no_id, last_item.item_code)
                )

            last_item.serial_no = serial_no_id

        # ---------------------------------------------------------------------
        # Handle Batch Number
        # ---------------------------------------------------------------------
        if frappe.db.get_value("Item", last_item.item_code, "has_batch_no") == 1:
            last_item.batch_no = assign_or_create_batch_for_last_item(work_order_id, last_item)

        # ---------------------------------------------------------------------
        # Recalculate stock and rates
        # ---------------------------------------------------------------------
        update_rate_and_availability_ste(stock_entry, None)

        # ---------------------------------------------------------------------
        # Save & Submit the Stock Entry
        # ---------------------------------------------------------------------
        stock_entry.save()
        stock_entry.submit()

        logger.info("Created and submitted Stock Entry: {0}".format(stock_entry.name))
        return stock_entry.as_dict()

    except ValidationError as ve:
        # Known or intentional validation failure
        frappe.log_error(title="FFTest - Validation Error", message=frappe.get_traceback())
        return {"error": str(ve)}
    except Exception as e:
        # Any unexpected error
        frappe.log_error(title="FFTest - Unexpected Error", message=frappe.get_traceback())
        return {"error": str(e)}


def assign_or_create_batch_for_last_item(work_order_id, last_item):
    """
    Determine a batch number for the last item row in a Stock Entry.
    If the Item requires a batch number, this function:
      1. Searches for an existing Batch linked to the given Work Order and item.
      2. If found, reuses it.
      3. Otherwise, creates a new Batch, links it to the Work Order, and returns its name.

    :param work_order_id: The name/ID of the Work Order (string).
    :param last_item: A Stock Entry Item row dict-like object containing item_code, etc.
    :return: The name of the existing or newly-created Batch (string) or None if not applicable.
    """
    logger = frappe.logger("FFTest")

    logger.debug("assign_or_create_batch_for_last_item() called")

    existing_batch_name = frappe.db.get_value(
        "Batch",
        filters={"work_order": work_order_id, "item": last_item.item_code},
        fieldname="name"
    )

    if existing_batch_name:
        logger.debug(f"Found existing batch: {existing_batch_name}")
        return existing_batch_name
    else:
        # Create a new Batch and link it to the Work Order
        batch_doc = frappe.new_doc("Batch")
        batch_doc.name = create_batch_name(last_item.item_code)
        # This is sometimes used as an internal naming field
        batch_doc.batch_id = batch_doc.name  
        batch_doc.item = last_item.item_code
        batch_doc.work_order = work_order_id

        batch_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        logger.debug(f"Created new batch: {batch_doc.name}")
        return batch_doc.name


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
    Recalculate item rates and stock availability for the Stock Entry
    before submission. This calls `doc.get_stock_and_rate()` internally.

    :param doc: The Stock Entry document.
    :param method: ERPNext event hook (optional, not used here).
    """
    doc.get_stock_and_rate()
    # Additional custom logic can go here if needed
    return
