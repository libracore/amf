import json
import frappe
from frappe import _, ValidationError
from frappe.utils import flt, now_datetime
from datetime import datetime
from amf.amf.utils.work_order_creation import get_default_bom
from amf.amf.utils.utilities import update_log_entry


@frappe.whitelist()
def make_stock_entry(source_work_order_id, serial_no_id=None, batch_no_id=None):
    """
    Creates and submits a 'Manufacture' Stock Entry for the first suitable Work Order 
    found via 'get_serialized_items_with_existing_work_orders(source_work_order_id)'.
    Optionally associates a serial number with the final item.

    :param source_work_order_id: The Work Order from which to find item codes.
    :param serial_no_id: (Optional) The serial number to use on the final item line.
    :return: A submitted Stock Entry doc or an error dict.
    """
    # Create a new Log Entry (global log_id is set within create_log_entry).
    create_log_entry("DEBUG: Entered make_stock_entry()")
    update_log_entry(
        log_id, f"DEBUG: source_work_order_id={source_work_order_id}, serial_no_id={serial_no_id}, batch_no_id={batch_no_id}")

    logger = frappe.logger("api", True)
    logger.info(
        f"make_stock_entry called with Work Order: {source_work_order_id}, Serial No: {serial_no_id}, and Batch No: {batch_no_id}")

    # 1) Find candidate Work Orders that match items from the given source Work Order
    update_log_entry(
        log_id, "DEBUG: Calling get_serialized_items_with_existing_work_orders() ...")
    matching_wos = get_serialized_items_with_existing_work_orders(
        source_work_order_id)
    logger.info(f"Found matching Work Orders: {matching_wos}")
    update_log_entry(log_id, f"DEBUG: matching_wos returned: {matching_wos}")

    spare_prod = frappe.db.get_value("Work Order", source_work_order_id, "spare_part_production")
    
    # 2) Select the first matched Work Order to proceed (if any exist)
    if not matching_wos:
        if not spare_prod:
            update_log_entry(
                log_id, "DEBUG: No suitable Work Order found. Returning error dict.")
            msg = _("DEBUG: No suitable Work Order found. Returning error dict.")
            logger.error(msg)
            return {"error": f"No suitable Work Order found from {source_work_order_id}."}
    
    if spare_prod:
        target_wo_id = source_work_order_id
        spare_batch_no = frappe.db.get_value("Work Order", source_work_order_id, "spare_batch_no")
    else:
        target_wo_id = matching_wos[0]["work_order_name"]
    update_log_entry(log_id, f"DEBUG: Chosen target_wo_id: {target_wo_id}")

    # 3) If needed, start the Work Order (moves materials to WIP) if status is 'Not Started'
    current_status = frappe.db.get_value("Work Order", target_wo_id, "status")
    update_log_entry(
        log_id, f"DEBUG: Current Work Order status: {current_status}")
    if current_status == 'Not Started':
        update_log_entry(
            log_id, "DEBUG: Work Order is 'Not Started'. Calling start_work_order() ...")
        start_work_order(target_wo_id)
    else:
        update_log_entry(
            log_id, "DEBUG: Work Order already In Process or another status, skipping start_work_order().")

    try:
        update_log_entry(
            log_id, "DEBUG: Entering try block in make_stock_entry() ...")

        # 4) Validate the target Work Order existence
        if not frappe.db.exists("Work Order", target_wo_id):
            msg = _("Work Order does not exist.")
            logger.error(msg)
            update_log_entry(log_id, f"DEBUG: {msg}")
            raise ValidationError(msg)

        work_order_doc = frappe.get_doc("Work Order", target_wo_id)
        update_log_entry(
            log_id, f"DEBUG: Retrieved work_order_doc: {work_order_doc.name}")

        # 5) Validate that there's enough quantity left to produce
        remaining_qty = work_order_doc.qty - work_order_doc.produced_qty
        update_log_entry(
            log_id, f"DEBUG: Work Order remaining_qty: {remaining_qty}")
        if remaining_qty <= 0:
            msg = _("Work Order cannot produce additional quantity.")
            logger.error(msg)
            update_log_entry(log_id, f"DEBUG: {msg}")
            raise ValidationError(msg)

        # 6) Determine the WIP warehouse logic
        if not work_order_doc.wip_step:
            wip_warehouse = "Work In Progress - AMF21"
        else:
            wip_warehouse = "Main Stock - AMF21"
        update_log_entry(log_id, f"DEBUG: Using wip_warehouse={wip_warehouse}")

        # 7) Create and configure the Stock Entry for manufacturing
        update_log_entry(
            log_id, "DEBUG: Creating new Stock Entry (Manufacture).")
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
            update_log_entry(log_id, f"DEBUG: {msg}")
            raise ValidationError(msg)

        stock_entry.inspection_required = 0
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = "Main Stock - AMF21"
        stock_entry.project = work_order_doc.project

        # 8) Configure the Stock Entry items from BOM
        update_log_entry(
            log_id, "DEBUG: Setting stock entry type and getting items from BOM.")
        stock_entry.set_stock_entry_type()
        stock_entry.get_items()

        # Calculate quantities from the BOM
        update_log_entry(
            log_id, f"DEBUG: Retrieving BOM doc: {stock_entry.bom_no}")
        bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
        required_qty_map = {
            item.item_code: item.qty * stock_entry.fg_completed_qty
            for item in bom_doc.items
        }
        update_log_entry(
            log_id, f"DEBUG: required_qty_map based on BOM: {required_qty_map}")

        # Update item lines
        for se_item in stock_entry.items:
            update_log_entry(
                log_id, f"DEBUG: Processing stock entry item: {se_item.item_code}")
            if se_item.item_code in required_qty_map:
                se_item.qty = flt(required_qty_map[se_item.item_code])
                se_item.transfer_qty = flt(
                    se_item.qty * se_item.conversion_factor)
                se_item.manual_source_warehouse_selection = 1
                if not work_order_doc.wip_step:
                    se_item.s_warehouse = "Work In Progress - AMF21"
                else:
                    se_item.s_warehouse = "Main Stock - AMF21"
                update_log_entry(
                    log_id,
                    f"DEBUG: Updated item qty={se_item.qty}, s_warehouse={se_item.s_warehouse}"
                )

        # 9) If last item is serialized, attach the provided serial_no_id (if any)
        if stock_entry.items:
            last_item = stock_entry.items[-1]
            update_log_entry(
                log_id, f"DEBUG: Checking if last_item {last_item.item_code} is serialized...")
            if frappe.db.get_value("Item", last_item.item_code, "has_serial_no") == 1:
                update_log_entry(log_id, "DEBUG: Item is serialized.")
                if not serial_no_id:
                    msg = _("Serial number is required for the final item.")
                    logger.error(msg)
                    update_log_entry(log_id, f"DEBUG: {msg}")
                    raise ValidationError(msg)

                # Ensure that this serial doesn't already exist for the same item
                existing_serial = frappe.db.exists(
                    {
                        "doctype": "Serial No",
                        "serial_no": serial_no_id,
                        "item_code": last_item.item_code
                    }
                )
                if existing_serial:
                    msg = _("The specified Serial No already exists for this item.")
                    logger.error(msg)
                    update_log_entry(log_id, f"DEBUG: {msg}")
                    raise ValidationError(msg)

                last_item.serial_no = serial_no_id
                last_item.manual_target_warehouse_selection = 1
                last_item.t_warehouse = "Main Stock - AMF21"
                update_log_entry(
                    log_id, f"DEBUG: Assigned serial_no {serial_no_id} to last item.")

            # Batch handling (if item has_batch_no = 1)
            update_log_entry(
                log_id, "DEBUG: Checking if last_item has batch-tracking...")
            last_item.auto_batch_no_generation = 0
            if not spare_prod:
                last_item.batch_no = assign_or_create_batch_for_last_item(
                    target_wo_id, last_item)
                update_log_entry(
                    log_id, f"DEBUG: last_item.batch_no set to {last_item.batch_no}")
            else:
                if frappe.db.get_value("Item", last_item.item_code, "has_batch_no") == 1:
                    update_log_entry(log_id, "DEBUG: Item is batchable with auto WO batch no.")
                    print("spare_batch_no:", spare_batch_no)
                    last_item.batch_no = spare_batch_no
                    update_log_entry(
                        log_id, f"DEBUG: last_item.batch_no set to {last_item.batch_no}")

        # 10) Save and submit the Stock Entry
        update_log_entry(
            log_id, f"DEBUG: Saving Stock Entry doc {stock_entry.name}...")
        stock_entry.save()

        # Update rate and availability
        update_log_entry(
            log_id, "DEBUG: Calling update_rate_and_availability_ste()...")
        update_rate_and_availability_ste(stock_entry, None)

        update_log_entry(log_id, "DEBUG: Submitting the Stock Entry...")
        stock_entry.submit()
        logger.info(
            f"Successfully created and submitted Stock Entry {stock_entry.name}."
        )
        update_log_entry(
            log_id, f"DEBUG: Stock Entry submitted successfully: {stock_entry.name}")

        if not spare_prod:
            start_work_order_final(source_work_order_id, serial_no_id, batch_no_id)

        return stock_entry

    except ValidationError as ve:
        frappe.log_error(
            title="Validation Error in make_stock_entry",
            message=frappe.get_traceback()
        )
        update_log_entry(
            log_id, "DEBUG: Caught ValidationError in make_stock_entry()")
        update_log_entry(log_id, f"DEBUG: ValidationError message: {str(ve)}")
        return {"error": str(ve)}

    except Exception as e:
        frappe.log_error(
            title="Unexpected Error in make_stock_entry",
            message=frappe.get_traceback()
        )
        update_log_entry(
            log_id, "DEBUG: Caught general Exception in make_stock_entry()")
        update_log_entry(log_id, f"DEBUG: Exception message: {str(e)}")
        return {"error": str(e)}


def start_work_order(work_order_id):
    """
    Moves materials from 'Main Stock - AMF21' to 'Work In Progress - AMF21'
    for the specified Work Order to transition it from Not Started to In Process.
    """
    update_log_entry(log_id, "DEBUG: Entered start_work_order()")
    update_log_entry(log_id, f"DEBUG: work_order_id={work_order_id}")

    work_order_doc = frappe.get_doc("Work Order", work_order_id)
    update_log_entry(
        log_id, f"DEBUG: Retrieved work_order_doc: {work_order_doc.name}")

    # Create a 'Material Transfer for Manufacture' Stock Entry
    update_log_entry(
        log_id, "DEBUG: Creating 'Material Transfer for Manufacture' Stock Entry.")
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
        update_log_entry(log_id, f"DEBUG: {msg}")
        raise ValidationError(msg)

    update_log_entry(
        log_id, "DEBUG: Setting stock entry type and getting items from BOM.")
    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    # Calculate and set BOM item quantities
    update_log_entry(
        log_id, f"DEBUG: Retrieving BOM doc for start_work_order: {stock_entry.bom_no}")
    bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
    required_qty_map = {
        item.item_code: item.qty * stock_entry.fg_completed_qty
        for item in bom_doc.items
    }
    update_log_entry(
        log_id, f"DEBUG: required_qty_map in start_work_order: {required_qty_map}")

    for se_item in stock_entry.items:
        if se_item.item_code in required_qty_map:
            se_item.qty = flt(required_qty_map[se_item.item_code])
            se_item.transfer_qty = flt(se_item.qty * se_item.conversion_factor)
            update_log_entry(
                log_id,
                f"DEBUG: Updated item {se_item.item_code} qty={se_item.qty}"
            )

    # Move from Main to WIP
    stock_entry.inspection_required = 0
    stock_entry.from_warehouse = "Main Stock - AMF21"
    stock_entry.to_warehouse = "Work In Progress - AMF21"
    stock_entry.project = work_order_doc.project
    stock_entry.save()

    update_log_entry(
        log_id, f"DEBUG: Saving and submitting start_work_order Stock Entry: {stock_entry.name}")

    # Update valuation and availability
    update_log_entry(
        log_id, "DEBUG: Calling update_rate_and_availability_ste() from start_work_order()...")
    update_rate_and_availability_ste(stock_entry, None)
    stock_entry.submit()
    update_log_entry(log_id, "DEBUG: Material Transfer Stock Entry submitted.")


import frappe
from frappe import _, ValidationError
from frappe.utils import flt
import json

def start_work_order_final(work_order_id, serial_no_id=None, batch_no_id=None):
    """
    Moves materials from 'Main Stock - AMF21' to 'Main Stock - AMF21' 
    for the specified Work Order, with the Stock Entry purpose set to 'Manufacture'.

    Steps Implemented:
      1. Validate the Work Order + BOM
      2. Create Stock Entry (purpose = 'Manufacture')
      3. Pull items from BOM (stock_entry.get_items()), update BOM-based qty
      4. For each row in batch_no_id (if present):
         - fetch item_code from 'Batch'
         - run the SQL query joining `tabStock Ledger Entry` + `tabBin`
         - gather results with item_code, warehouse, and a non-zero qty_after_transaction
      5. In the for-loop of stock_entry.items, if se_item.item_code matches,
         update se_item.s_warehouse (or create new lines) with the retrieved warehouse,
         set se_item.batch_no, and set the correct qty if desired
      6. Assign serial_no to any items that are serialized
      7. On the last row, also set product_serial_no = serial_no_id
      8. Save, update rate/availability, and submit
    """

    update_log_entry(log_id, "DEBUG: Entered start_work_order_final()")
    update_log_entry(
        log_id, f"DEBUG: work_order_id={work_order_id}, serial_no_id={serial_no_id}, batch_no_id={batch_no_id}"
    )

    # 1) Fetch and validate the Work Order
    work_order_doc = frappe.get_doc("Work Order", work_order_id)
    update_log_entry(log_id, f"DEBUG: Retrieved work_order_doc: {work_order_doc.name}")

    if not frappe.db.exists("BOM", work_order_doc.bom_no):
        msg = _("BOM does not exist for this Work Order.")
        update_log_entry(log_id, f"DEBUG: {msg}")
        raise ValidationError(msg)

    # 2) Create Stock Entry (purpose = 'Manufacture')
    update_log_entry(log_id, "DEBUG: Creating 'Manufacture' Stock Entry.")
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = 'Manufacture'
    stock_entry.work_order = work_order_id
    stock_entry.company = "Advanced Microfluidics SA"
    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order_doc.bom_no
    stock_entry.use_multi_level_bom = 0
    stock_entry.fg_completed_qty = 1  # Hard-coded for 1 unit, adjust if needed
    stock_entry.inspection_required = 0
    stock_entry.from_warehouse = "Main Stock - AMF21"
    stock_entry.to_warehouse = "Main Stock - AMF21"
    stock_entry.project = work_order_doc.project

    # 3) Pull items from BOM + recalc qty
    update_log_entry(log_id, "DEBUG: Setting stock entry type and getting items from BOM.")
    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    update_log_entry(log_id, f"DEBUG: Retrieving BOM doc: {stock_entry.bom_no}")
    bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
    required_qty_map = {
        item.item_code: item.qty * stock_entry.fg_completed_qty
        for item in bom_doc.items
    }
    update_log_entry(
        log_id, f"DEBUG: required_qty_map in start_work_order_final => {required_qty_map}"
    )

    # 4) For each row in batch_no_id, fetch item_code from 'Batch', run SQL
    #    We'll accumulate a list of dict like:
    #    {"item_code": ..., "warehouse": ..., "batch_no": ..., "qty": ...}
    #    If batch_no_id is not given, no special batch logic is done.
    batch_info_results = []  # will hold the final combined info

    if batch_no_id:
        # parse JSON if needed
        if isinstance(batch_no_id, str):
            try:
                batch_no_id = json.loads(batch_no_id)
            except Exception as e:
                raise ValidationError(f"Invalid batch_no_id JSON: {str(e)}")

        if not isinstance(batch_no_id, list):
            raise ValidationError("batch_no_id must be a list of dicts with batch_no, etc.")

        update_log_entry(log_id, "DEBUG: Handling batch_no_id logic ...")

        for row in batch_no_id:
            bn = row.get("batch_no")
            if not bn:
                update_log_entry(log_id, "DEBUG: Skipping row missing 'batch_no'.")
                continue

            # fetch item_code from 'Batch'
            item_code = frappe.db.get_value("Batch", bn, "item")
            if not item_code:
                update_log_entry(log_id, f"DEBUG: No item_code found for Batch {bn}, skipping.")
                continue

            # run the SQL query to get warehouse + qty_after_transaction
            # (making sure it's != 0)
            # we assume only one or multiple rows might come back
            query = """
                SELECT
                    sle.item_code,
                    sle.warehouse,
                    sle.qty_after_transaction AS qty
                FROM `tabStock Ledger Entry` AS sle
                JOIN `tabBin` AS bin
                    ON bin.item_code   = sle.item_code
                    AND bin.warehouse  = sle.warehouse
                    AND bin.actual_qty >= sle.actual_qty
                    AND bin.actual_qty > 0
                WHERE sle.batch_no = %(batch_no)s
                  AND sle.item_code = %(item_code)s
                  AND sle.qty_after_transaction != 0
                GROUP BY sle.item_code, sle.warehouse
            """
            query_vals = {"batch_no": bn, "item_code": item_code}
            results = frappe.db.sql(query, query_vals, as_dict=True)

            if not results:
                # no matching stock ledger records for this batch
                update_log_entry(log_id,
                    f"DEBUG: No SLE rows found for batch={bn}, item_code={item_code}."
                )
                continue

            for r in results:
                # We'll store the combined info
                batch_info_results.append({
                    "item_code": r["item_code"],
                    "warehouse": r["warehouse"],
                    "batch_no": bn,
                    "qty": r["qty"]
                })
                update_log_entry(log_id,
                    f"DEBUG: Found warehouse={r['warehouse']} qty={r['qty']} for item_code={r['item_code']} batch={bn}"
                )

    # 5) Update auto-created BOM lines. 
    #    - set the BOM-based qty
    #    - if we have batch_info_results for the same item_code, 
    #      we can either update this line or create new ones. 
    #      We'll do the simplest approach: if there's exactly one row 
    #      from batch_info for that item_code, we update the existing line. 
    #      If there's multiple, we'll show how to create additional lines.

    # We'll track item_codes -> a list of batch rows
    from collections import defaultdict
    batch_map = defaultdict(list)
    for row in batch_info_results:
        batch_map[row["item_code"]].append(row)

    stock_items_to_add = []  # if we need additional lines

    for idx, se_item in enumerate(stock_entry.items):
        item_code = se_item.item_code

        # 5a) If BOM says we need X quantity for this item, set it
        if item_code in required_qty_map:
            se_item.qty = flt(required_qty_map[item_code])
            se_item.transfer_qty = flt(se_item.qty * se_item.conversion_factor)
            update_log_entry(
                log_id, f"DEBUG: Updated item {item_code} qty={se_item.qty}"
            )

        # 5b) Always set warehouses / flags
        se_item.manual_source_warehouse_selection = 1
        se_item.s_warehouse = "Main Stock - AMF21"
        se_item.auto_batch_no_generation = 0

        # 5c) If serialized, set serial_no
        #     (Your code sets it for every item that is serialized)
        has_serial = frappe.db.get_value("Item", se_item.item_code, "has_serial_no")
        if has_serial == 1:
            se_item.serial_no = serial_no_id
            se_item.manual_source_warehouse_selection = 1
            se_item.s_warehouse = frappe.db.get_value("Serial No", serial_no_id, "warehouse")
            update_log_entry(
                log_id, f"DEBUG: Set serial_no={serial_no_id} on {se_item.item_code} for warehouse {se_item.s_warehouse}"
            )

        # If it's the last row, also set product_serial_no
        is_last = (idx == len(stock_entry.items) - 1)
        if is_last:
            se_item.manual_target_warehouse_selection = 1
            se_item.t_warehouse = "Main Stock - AMF21"
            se_item.product_serial_no = serial_no_id
            update_log_entry(
                log_id,
                f"DEBUG: Set product_serial_no={serial_no_id} on last row {se_item.item_code} (serialized)."
            )

        # 5d) If we have batch rows for this item_code, let's handle them
        batch_rows = batch_map.get(item_code, [])
        if len(batch_rows) == 1:
            # If exactly one row, let's just update the existing line
            row = batch_rows[0]
            # Possibly override the warehouse from SLE
            se_item.s_warehouse = row["warehouse"]
            se_item.batch_no = row["batch_no"]
            # If you want to override the quantity from the SLE:
            # se_item.qty = flt(row["qty"])
            # se_item.transfer_qty = flt(se_item.qty * se_item.conversion_factor)

            update_log_entry(
                log_id,
                f"DEBUG: Updated existing line {item_code} with batch_no={row['batch_no']} warehouse={row['warehouse']} qty={row['qty']}"
            )
        elif len(batch_rows) > 1:
            # If multiple rows, we can update the first line with the first row
            # and create new lines for the others
            first = batch_rows[0]
            se_item.s_warehouse = first["warehouse"]
            se_item.batch_no = first["batch_no"]
            # If you want to override the quantity from the SLE:
            # se_item.qty = flt(first["qty"])
            # se_item.transfer_qty = flt(se_item.qty * se_item.conversion_factor)

            update_log_entry(
                log_id,
                f"DEBUG: Updated existing line {item_code} with the first batch row batch_no={first['batch_no']} warehouse={first['warehouse']} qty={first['qty']}"
            )

            # For the rest, create new lines
            for extra_row in batch_rows[1:]:
                new_line = stock_entry.append("items", {})
                new_line.item_code = item_code
                new_line.qty = se_item.qty  # or flt(extra_row["qty"]) if you prefer
                new_line.transfer_qty = flt(new_line.qty * (new_line.conversion_factor or 1.0))
                new_line.manual_source_warehouse_selection = 1
                new_line.s_warehouse = extra_row["warehouse"]
                new_line.manual_target_warehouse_selection = 1
                new_line.t_warehouse = se_item.t_warehouse
                new_line.auto_batch_no_generation = 0
                new_line.batch_no = extra_row["batch_no"]

                # If item is serialized, possibly set new_line.serial_no = serial_no_id
                # but typically you only have one serial_no per line
                if has_serial == 1:
                    new_line.serial_no = serial_no_id

                update_log_entry(
                    log_id,
                    f"DEBUG: Added new line for item_code={item_code} batch_no={extra_row['batch_no']} warehouse={extra_row['warehouse']} qty={extra_row['qty']}"
                )

    # 6) Save, update rate/availability, and submit
    stock_entry.save()
    update_log_entry(log_id, f"DEBUG: Saving Stock Entry {stock_entry.name} ...")

    update_log_entry(log_id, "DEBUG: Calling update_rate_and_availability_ste() from start_work_order_final()...")
    update_rate_and_availability_ste(stock_entry, None)

    update_log_entry(log_id, "DEBUG: Submitting Stock Entry...")
    stock_entry.submit()
    update_log_entry(log_id, "DEBUG: Material Transfer Stock Entry submitted.")

    return stock_entry

def create_new_wo(item_code='520100', sales_order="", qty=1):
    update_log_entry(log_id, "DEBUG: Entered create_new_wo()")
    update_log_entry(
        log_id, f"DEBUG: item_code={item_code}, sales_order={sales_order}, qty={qty}")

    # Make a single Work Order for the given item
    bom_no = get_default_bom(item_code)
    update_log_entry(log_id, f"DEBUG: get_default_bom returned: {bom_no}")

    work_order = frappe.get_doc(dict(
        doctype='Work Order',
        production_item=item_code,
        bom_no=bom_no,
        qty=qty,
        company='Advanced Microfluidics SA',
        sales_order=sales_order,
        fg_warehouse='Main Stock - AMF21',
        simple_description='Auto-generated Work Order from non-available stock via FFTest.'
    )).insert()

    update_log_entry(
        log_id, "DEBUG: New Work Order inserted. Setting operations...")
    work_order.set_work_order_operations()
    work_order.save()
    work_order.submit()
    update_log_entry(
        log_id, f"DEBUG: Work Order created and submitted: {work_order.name}")

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
    update_log_entry(
        log_id, "DEBUG: Entered get_serialized_items_with_existing_work_orders()")
    update_log_entry(log_id, f"DEBUG: work_order_id={work_order_id}")

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
    update_log_entry(
        log_id, f"DEBUG: item_codes with has_serial_no=1: {item_codes}")

    # If no serialized items found, return early
    if not item_codes:
        update_log_entry(
            log_id, "DEBUG: No serialized items found. Checking current WO.")
        item_to_manuf = frappe.db.get_value("Work Order", work_order_id, 'production_item')
        if item_to_manuf.startswith('5'):
            update_log_entry(
            log_id, "DEBUG: Current WO is already a 5XXXXX production item WO. Returning current WO.")
            return [{"work_order_name": work_order_id, "production_item": item_to_manuf}]
        else:
            update_log_entry(
            log_id, "DEBUG: After check, no wo found. Something is wrong. Call assistance.")
            return []

    # Step 2: Get existing Work Orders that produce these item codes,
    #         are 'Not Started' or 'In Process',
    #         and (optionally) have 'parent_work_order' == work_order_id
    update_log_entry(
        log_id, "DEBUG: Searching for existing Work Orders with these item_codes.")
    wo_filters = {
        "production_item": ["in", item_codes],
        "status": ["in", ["Not Started", "In Process"]],
        "parent_work_order": work_order_id
    }

    existing_work_orders = frappe.get_all(
        "Work Order",
        filters=wo_filters,
        fields=["name", "production_item"]
    )
    update_log_entry(
        log_id, f"DEBUG: existing_work_orders found: {existing_work_orders}")

    if not existing_work_orders:
        update_log_entry(
            log_id, "DEBUG: No matching existing WOs found. Attempting secondary lookup.")
        # 1) Attempt a second lookup with different filters
        secondary_wos = frappe.get_all(
            "Work Order",
            filters={
                "production_item": ["in", item_codes],
                "status": ["in", ["Not Started", "In Process"]],
                "sales_order": "",
                "parent_work_order": "",
            },
            fields=["name", "production_item"]
        )
        update_log_entry(
            log_id, f"DEBUG: secondary_wos found: {secondary_wos}")

        if secondary_wos:
            existing_work_orders = secondary_wos
        else:
            # 2) If still empty, create new Work Orders for each item_code
            update_log_entry(
                log_id, "DEBUG: Still no WOs found. Creating new WOs for each serialized item code.")
            newly_created_wos = []
            for code in item_codes:
                update_log_entry(
                    log_id, f"DEBUG: Creating new WO for item_code={code}")
                wo_doc = create_new_wo(code)
                newly_created_wos.append({
                    "name": wo_doc.name,
                    "production_item": wo_doc.production_item
                })
            existing_work_orders = newly_created_wos

    # Step 3: Build a unique set of (name, production_item) pairs
    update_log_entry(log_id, "DEBUG: Building unique set of Work Orders...")
    unique_wo_pairs = {
        (wo["name"], wo["production_item"]) for wo in existing_work_orders
    }
    update_log_entry(log_id, f"DEBUG: unique_wo_pairs: {unique_wo_pairs}")

    # Convert tuples back into dicts for the final result
    final_result = [
        {"work_order_name": wo_name, "production_item": prod_item}
        for (wo_name, prod_item) in unique_wo_pairs
    ]
    update_log_entry(
        log_id, f"DEBUG: get_serialized_items_with_existing_work_orders final_result: {final_result}")
    return final_result


def assign_or_create_batch_for_last_item(work_order_id, last_item):
    """
    If the last_item's item_code has_batch_no = 1, try to find an existing Batch with
    matching Work Order and Item. Otherwise create a new Batch. Returns the batch name or None.
    """
    update_log_entry(
        log_id, "DEBUG: Entered assign_or_create_batch_for_last_item()")
    update_log_entry(
        log_id, f"DEBUG: work_order_id={work_order_id}, last_item={last_item.item_code}")

    logger = frappe.logger()
    logger.info("assign_or_create_batch_for_last_item called.")

    # Check if the item is batch-tracked
    has_batch_no = frappe.db.get_value(
        "Item", last_item.item_code, "has_batch_no")
    update_log_entry(
        log_id, f"DEBUG: has_batch_no for {last_item.item_code} => {has_batch_no}")
    if has_batch_no == 1:
        # Attempt to find an existing batch for this item + Work Order
        existing_batch_name = frappe.db.get_value(
            "Batch",
            filters={"work_order": work_order_id, "item": last_item.item_code},
            fieldname="name"
        )
        if existing_batch_name:
            logger.info(
                f"Found existing batch {existing_batch_name} for Work Order {work_order_id}."
            )
            update_log_entry(
                log_id, f"DEBUG: Found existing batch {existing_batch_name}")
            return existing_batch_name

        # Otherwise create a new batch
        logger.info(f"No batch found for {work_order_id}; creating a new one.")
        update_log_entry(log_id, "DEBUG: Creating a new Batch doc...")
        work_order_doc = frappe.get_doc("Work Order", work_order_id)

        batch_doc = frappe.new_doc("Batch")
        batch_doc.name = create_batch_name(last_item.item_code)
        batch_doc.batch_id = batch_doc.name
        batch_doc.item = last_item.item_code
        batch_doc.work_order = work_order_id
        batch_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        update_log_entry(log_id, f"DEBUG: New batch created: {batch_doc.name}")
        return batch_doc.name

    # If not batch-tracked
    logger.info("Item is not batch-tracked. Returning None.")
    update_log_entry(
        log_id, "DEBUG: Item is not batch-tracked, returning None.")
    return None


def create_batch_name(item_code):
    """
    Generate a batch name:
    - current datetime as YYYYMMDDHHMMSS
    - item_code
    - 'AMF'
    """
    update_log_entry(log_id, "DEBUG: Entered create_batch_name()")
    timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S')
    generated_name = f"{timestamp_str} {item_code} AMF"
    update_log_entry(
        log_id, f"DEBUG: Generated batch name => {generated_name}")
    return generated_name


def update_rate_and_availability_ste(stock_entry_doc, method):
    """
    Recomputes stock rate and availability for the given Stock Entry doc.
    :param stock_entry_doc: A Stock Entry document to update.
    :param method: Unused standard Frappe hook param.
    """
    update_log_entry(
        log_id, "DEBUG: Entered update_rate_and_availability_ste()")
    logger = frappe.logger()
    logger.info("update_rate_and_availability_ste called.")

    update_log_entry(
        log_id, f"DEBUG: Calling get_stock_and_rate() on {stock_entry_doc.name} ...")
    stock_entry_doc.get_stock_and_rate()
    update_log_entry(log_id, "DEBUG: Completed get_stock_and_rate().")


def create_log_entry(message, category=None):
    """ 
    Create a new Log Entry and store its name in global log_id for subsequent update_log_entry calls. 
    """
    import datetime  # If not already imported at top-level
    log_doc = frappe.get_doc({
        "doctype": "Log Entry",
        "timestamp": datetime.datetime.now(),
        "category": category,
        "message": message,
        "reference_name": f"FFTest Stock Entry: {now_datetime()}"
    })
    log_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # Store name in a global variable so subsequent calls to update_log_entry() can reference it.
    global log_id
    log_id = log_doc.name

    # Replace print(...) with an update_log_entry about the newly created log entry
    update_log_entry(log_id, f"DEBUG: Created new log entry with ID: {log_id}")
    return None

@frappe.whitelist()
def fetch_sn(product_id):
    """
    1) Finds the highest serial number for the given product_id.
    2) Increments that serial by 1.
    3) Returns the new serial.
    """
    # Example: Suppose your doctype is "Item Serial"
    # and it stores a field called "serial_no" (as an int) plus "product_id".
    # 
    # Step A: Query for the maximum serial_no belonging to product_id:
    print("product_id:",product_id)
    highest_sn = frappe.db.sql("""
        SELECT MAX(serial_no)
        FROM `tabSerial No`
        WHERE item_code = %s
    """, (product_id,), as_list=True)
    print("highest_sn:",highest_sn)
    # highest_sn is a list of lists, e.g. [[123]] or [[None]] if no rows
    if highest_sn and highest_sn[0][0] is not None:
        last_sn = int(highest_sn[0][0])
    else:
        # If not found, define a default. E.g. 999 or 1000
        last_sn = 0

    # Step B: increment
    new_sn = last_sn + 1
    print("new_sn:",new_sn)
    # Return the new_sn in a JSON-friendly format:
    return {"sn": str(new_sn)}