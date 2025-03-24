from amf.amf.utils.work_order_creation import get_default_bom
import frappe
from frappe import _, ValidationError
from frappe.utils import flt
from datetime import datetime

@frappe.whitelist()
def make_stock_entry(source_work_order_id, serial_no_id=None):
    """
    Creates and submits a 'Manufacture' Stock Entry for the first suitable Work Order 
    found via 'get_serialized_items_with_existing_work_orders(source_work_order_id)'.
    Optionally associates a serial number with the final item.

    :param source_work_order_id: The Work Order from which to find item codes.
    :param serial_no_id: (Optional) The serial number to use on the final item line.
    :return: A submitted Stock Entry doc or an error dict.
    """
    logger = frappe.logger()
    logger.info(
        f"make_stock_entry called with Work Order: {source_work_order_id} and Serial No: {serial_no_id}"
    )

    # 1) Find candidate Work Orders that match items from the given source Work Order
    matching_wos = get_serialized_items_with_existing_work_orders(source_work_order_id)
    logger.info(f"Found matching Work Orders: {matching_wos}")

    # 2) Select the first matched Work Order to proceed (if any exist)
    if not matching_wos:
        return {"error": f"No suitable Work Order found from {source_work_order_id}."}

    # We'll reassign the primary work_order_id to the first match in the list
    # (i.e. first in "Not Started" or "In Process" for an item requiring a serial).
    target_wo_id = matching_wos[0]["work_order_name"]
    print(target_wo_id)
    # 3) If needed, start the Work Order (moves materials to WIP) if status is 'Not Started'
    if frappe.db.get_value("Work Order", target_wo_id, "status") == 'Not Started':
        start_work_order(target_wo_id)

    try:
        # 4) Validate the target Work Order existence
        if not frappe.db.exists("Work Order", target_wo_id):
            msg = _("Work Order does not exist.")
            logger.error(msg)
            raise ValidationError(msg)

        work_order_doc = frappe.get_doc("Work Order", target_wo_id)

        # 5) Validate that there's enough quantity left to produce
        if (work_order_doc.qty - work_order_doc.produced_qty) <= 0:
            msg = _("Work Order cannot produce additional quantity.")
            logger.error(msg)
            raise ValidationError(msg)

        # 6) Determine the WIP warehouse logic
        #    If "wip_step" is empty, use "Work In Progress - AMF21"; otherwise "Main Stock - AMF21"
        if not work_order_doc.wip_step:
            wip_warehouse = "Work In Progress - AMF21"
        else:
            wip_warehouse = "Main Stock - AMF21"

        # 7) Create and configure the Stock Entry for manufacturing
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = 'Manufacture'
        stock_entry.work_order = target_wo_id
        stock_entry.company = work_order_doc.company
        stock_entry.from_bom = 1
        stock_entry.bom_no = work_order_doc.bom_no
        stock_entry.use_multi_level_bom = 0
        stock_entry.fg_completed_qty = 1  # Hard-coded to produce 1 unit

        # Validate BOM existence
        if not frappe.db.exists("BOM", work_order_doc.bom_no):
            msg = _("BOM does not exist for the Work Order.")
            logger.error(msg)
            raise ValidationError(msg)

        stock_entry.inspection_required = 0
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = "Main Stock - AMF21"
        stock_entry.project = work_order_doc.project

        # Optional: load any additional costs for manufacturing
        # additional_costs = get_additional_costs(work_order_doc, fg_qty=stock_entry.fg_completed_qty)
        # stock_entry.set("additional_costs", additional_costs)

        # 8) Configure the Stock Entry items from BOM
        stock_entry.set_stock_entry_type()
        stock_entry.get_items()

        # Calculate quantities from the BOM
        bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
        required_qty_map = {
            item.item_code: item.qty * stock_entry.fg_completed_qty
            for item in bom_doc.items
        }

        # Update item lines
        for se_item in stock_entry.items:
            if se_item.item_code in required_qty_map:
                se_item.qty = flt(required_qty_map[se_item.item_code])
                se_item.transfer_qty = flt(
                    se_item.qty * se_item.conversion_factor)
                se_item.manual_source_warehouse_selection = 1
                se_item.s_warehouse = "Work In Progress - AMF21"

        # 9) If last item is serialized, attach the provided serial_no_id (if any)
        if stock_entry.items:
            last_item = stock_entry.items[-1]
            if frappe.db.get_value("Item", last_item.item_code, "has_serial_no") == 1:
                if not serial_no_id:
                    msg = _("Serial number is required for the final item.")
                    logger.error(msg)
                    raise ValidationError(msg)

                # Ensure that this serial doesn't already exist for the same item
                existing_serial = frappe.db.exists(
                    {"doctype": "Serial No", "serial_no": serial_no_id,
                        "item_code": last_item.item_code}
                )
                if existing_serial:
                    msg = _("The specified Serial No already exists for this item.")
                    logger.error(msg)
                    raise ValidationError(msg)

                last_item.serial_no = serial_no_id
                last_item.manual_target_warehouse_selection = 1
                last_item.t_warehouse = "Main Stock - AMF21"

            # Batch handling (if item has_batch_no = 1)
            last_item.auto_batch_no_generation = 0
            last_item.batch_no = assign_or_create_batch_for_last_item(
                target_wo_id, last_item
            )

        # 10) Save and submit the Stock Entry
        stock_entry.save()

        # Update rate and availability
        update_rate_and_availability_ste(stock_entry, None)

        stock_entry.submit()
        logger.info(
            f"Successfully created and submitted Stock Entry {stock_entry.name}.")

        return stock_entry

    except ValidationError as ve:
        frappe.log_error(
            title="Validation Error in make_stock_entry",
            message=frappe.get_traceback()
        )
        return {"error": str(ve)}

    except Exception as e:
        frappe.log_error(
            title="Unexpected Error in make_stock_entry",
            message=frappe.get_traceback()
        )
        return {"error": str(e)}


def start_work_order(work_order_id):
    """
    Moves materials from 'Main Stock - AMF21' to 'Work In Progress - AMF21'
    for the specified Work Order to transition it from Not Started to In Process.
    """
    print(f"Starting Work Order: {work_order_id}")
    work_order_doc = frappe.get_doc("Work Order", work_order_id)

    # Create a 'Material Transfer for Manufacture' Stock Entry
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = 'Material Transfer for Manufacture'
    stock_entry.work_order = work_order_id
    stock_entry.company = "Advanced Microfluidics SA"
    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order_doc.bom_no
    stock_entry.use_multi_level_bom = 0
    stock_entry.fg_completed_qty = 1  # Hard-coded for 1 unit

    # Validate BOM
    if not frappe.db.exists("BOM", work_order_doc.bom_no):
        msg = _("BOM does not exist for this Work Order.")
        raise ValidationError(msg)

    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    # Calculate and set BOM item quantities
    bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
    required_qty_map = {
        item.item_code: item.qty * stock_entry.fg_completed_qty
        for item in bom_doc.items
    }
    for se_item in stock_entry.items:
        if se_item.item_code in required_qty_map:
            se_item.qty = flt(required_qty_map[se_item.item_code])
            se_item.transfer_qty = flt(se_item.qty * se_item.conversion_factor)

    # Move from Main to WIP
    stock_entry.inspection_required = 0
    stock_entry.from_warehouse = "Main Stock - AMF21"
    stock_entry.to_warehouse = "Work In Progress - AMF21"
    stock_entry.project = work_order_doc.project

    stock_entry.save()

    # Update valuation and availability
    update_rate_and_availability_ste(stock_entry, None)
    stock_entry.submit()

def create_new_wo(item_code='520100', sales_order="", qty=1):
    print("creating wo for item:",item_code)
    '''Make a single Work Order for the given item'''
    bom_no = get_default_bom(item_code)

    work_order = frappe.get_doc(dict(
        doctype='Work Order',
        production_item=item_code,
        bom_no=bom_no,
        qty=qty,
        company='Advanced Microfluidics SA',
        sales_order=sales_order,
        fg_warehouse='Main Stock - AMF21',  # Replace with the appropriate warehouse
        simple_description='Auto-generated Work Order from non-available stock via FFTest.'
    )).insert()
   
    work_order.set_work_order_operations()
    work_order.save()
    work_order.submit()
    return work_order

@frappe.whitelist()
def get_serialized_items_with_existing_work_orders(work_order_id):
    """
    1. Finds which item codes from 'Work Order Item' for a given work_order_id
       have has_serial_no=1 (joined from 'Item').
    2. Retrieves all existing Work Orders that have those item codes 
       as 'production_item', are either 'Not Started' or 'In Process', 
       and match 'parent_work_order'=work_order_id (if that's your desired filter).
    3. Returns a list of dicts: [{ "work_order_name": ..., "production_item": ... }, ...]
    """
    # Step 1: SQL join to get all distinct item_codes with has_serial_no=1
    sql_query = """
        SELECT DISTINCT w.item_code
        FROM `tabWork Order Item` AS w
        INNER JOIN `tabItem` AS i ON i.item_code = w.item_code
        WHERE w.parent = %s
          AND i.has_serial_no = 1
    """
    results = frappe.db.sql(sql_query, (work_order_id,), as_dict=True)
    item_codes = [row["item_code"] for row in results]

    # If no serialized items found, return early
    if not item_codes:
        return []

    # Step 2: Get existing Work Orders that produce these item codes,
    #         are 'Not Started' or 'In Process',
    #         and (optionally) have 'parent_work_order' == work_order_id
    #         (if that's truly needed).
    wo_filters = {
        "production_item": ["in", item_codes],
        "status": ["in", ["Not Started", "In Process"]],
        "parent_work_order": work_order_id  # Remove this if not required
    }

    existing_work_orders = frappe.get_all(
        "Work Order",
        filters=wo_filters,
        fields=["name", "production_item"]
    )
    
    if not existing_work_orders:
        # 1) Attempt a second lookup with different filters
        secondary_wos = frappe.get_all(
            "Work Order",
            filters={
                "production_item": ["in", item_codes],
                "status": ["in", ["Not Started", "In Process"]],
                "sales_order": "",        # Remove if not required
                "parent_work_order": "",  # Remove if not required
            },
            fields=["name", "production_item"]
        )

        if secondary_wos:
            existing_work_orders = secondary_wos
        else:
            # 2) If still empty, create new Work Orders for each item_code
            newly_created_wos = []
            for code in item_codes:
                print(code)
                wo_doc = create_new_wo(code)
                # Convert the Work Order doc into a dict that matches get_all() structure
                newly_created_wos.append({
                    "name": wo_doc.name,
                    "production_item": wo_doc.production_item
                })
            existing_work_orders = newly_created_wos

    # Step 3: Build a unique set of (name, production_item) pairs
    unique_wo_pairs = {
        (wo["name"], wo["production_item"]) for wo in existing_work_orders
    }


    # Convert tuples back into dicts for the final result
    return [
        {"work_order_name": wo_name, "production_item": prod_item}
        for (wo_name, prod_item) in unique_wo_pairs
    ]


def assign_or_create_batch_for_last_item(work_order_id, last_item):
    """
    If the last_item's item_code has_batch_no = 1, try to find an existing Batch with
    matching Work Order and Item. Otherwise create a new Batch. Returns the batch name or None.
    """
    logger = frappe.logger()
    logger.info("assign_or_create_batch_for_last_item called.")

    # Check if the item is batch-tracked
    has_batch_no = frappe.db.get_value(
        "Item", last_item.item_code, "has_batch_no")
    if has_batch_no == 1:
        # Attempt to find an existing batch for this item + Work Order
        existing_batch_name = frappe.db.get_value(
            "Batch",
            filters={"work_order": work_order_id, "item": last_item.item_code},
            fieldname="name"
        )
        if existing_batch_name:
            logger.info(
                f"Found existing batch {existing_batch_name} for Work Order {work_order_id}.")
            return existing_batch_name

        # Otherwise create a new batch
        logger.info(f"No batch found for {work_order_id}; creating a new one.")
        work_order_doc = frappe.get_doc("Work Order", work_order_id)

        batch_doc = frappe.new_doc("Batch")
        batch_doc.name = create_batch_name(last_item.item_code)
        batch_doc.batch_id = batch_doc.name
        batch_doc.item = last_item.item_code
        batch_doc.work_order = work_order_id
        batch_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return batch_doc.name

    # If not batch-tracked
    logger.info("Item is not batch-tracked. Returning None.")
    return None


def create_batch_name(item_code):
    """
    Generate a batch name:
    - current datetime as YYYYMMDDHHMMSS
    - item_code
    - 'AMF'
    """
    timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{timestamp_str} {item_code} AMF"


def update_rate_and_availability_ste(stock_entry_doc, method):
    """
    Recomputes stock rate and availability for the given Stock Entry doc.
    :param stock_entry_doc: A Stock Entry document to update.
    :param method: Unused standard Frappe hook param.
    """
    logger = frappe.logger()
    logger.info("update_rate_and_availability_ste called.")
    stock_entry_doc.get_stock_and_rate()
    return
