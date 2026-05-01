import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.stock.utils import get_incoming_rate
import frappe
from frappe import _, _dict
from frappe.utils import flt

def batch_to_stock_entry(doc, method=None):
    print("Entering batch_to_stock_entry.")
    # Check if the purpose of the stock entry is 'Manufacture'
    if doc.purpose == "Manufacture" and doc.items:
        # Get the last item in the stock entry's items list
        last_item = doc.items[-1]
        # Fetch the 'has_batch_no' attribute for the item
        has_batch_no = frappe.db.get_value(
            "Item", last_item.item_code, "has_batch_no")
        # If the item has a batch number
        if has_batch_no:
            # Generate the batch_id using the given format
            batch_id = f"{last_item.item_code} {doc.posting_date} {doc.work_order} {int(doc.fg_completed_qty)}"
            print(batch_id)
            # Create a new Batch entry
            new_batch = frappe.get_doc(
                {"doctype": "Batch", "item": last_item.item_code, "batch_id": batch_id}
            ).insert()

            # Update the batch_no of the last item with the newly created batch's name
            last_item.batch_no = new_batch.name

        # Save the document changes (since we updated the batch_no)
        # doc.save()
    print("Ending batch_to_stock_entry...")


# def call_get_stock_and_rate_for_all():
#     # Fetch all Stock Entry names
#     stock_entries = frappe.get_list("Stock Entry", fields=["name"])

#     # Test Input
#     stock_entries = frappe.get_list("Stock Entry", filters={"name": "STE-04342"}, fields=["name"])

#     for entry in stock_entries:
#         # Get the Stock Entry document
#         stock_entry_doc = frappe.get_doc("Stock Entry", entry.get("name"))
#         print(f"Stock Entry: {stock_entry_doc.name}")
#         # Call the get_stock_and_rate method
#         stock_entry_doc.get_stock_and_rate()

#         # Save the Stock Entry to update changes
#         stock_entry_doc.save(ignore_permissions=True)  # Adding ignore_permissions based on your role & privileges

#         # Print the details (customize as per your requirement)
#         print(f"Stock Entry: {stock_entry_doc.name}, Rate and Stock Updated")

@frappe.whitelist()
def get_batch_item_qty_per_warehouse(item_code=None):
    """
        Returns a list of dictionaries showing the warehouse
        and the net quantity (sum of actual_qty) of a specific item
        from all batches in each warehouse using
        tabStock Ledger Entry (SLE).

        :param item_code: The Item Code whose quantity is being queried.
        :return:          A list of dicts, e.g.:
                          [
                              {"warehouse": "Stores - A", "batch_no": "BATCH001", "total_qty": 50.0},
                              {"warehouse": "Stores - B", "batch_no": "BATCH002", "total_qty": -10.0}
                          ]
                          where total_qty is the net result of actual_qty
                          from all matching entries.
        """
    if not item_code:
        item_code = '100024'
    data = frappe.db.sql(
        """
            SELECT
                sle.warehouse AS warehouse,
                sle.batch_no AS batch_no,
                SUM(sle.actual_qty) AS total_qty
            FROM `tabStock Ledger Entry` as sle
            JOIN `tabBatch` as b ON b.name = sle.batch_no
            WHERE item_code = %(item_code)s
            AND b.disabled = 0
            GROUP BY sle.warehouse, sle.batch_no
            ORDER BY sle.warehouse, sle.batch_no
            """,
        {"item_code": item_code},
        as_dict=True
    )

    return data

@frappe.whitelist()
def get_sub_bom_items(item_code=None, include_top_level=True):
    """
    Fetch the item codes of all sub-BOMs recursively for a given item_code.

    Args:
        item_code (str): The item code to fetch BOM and sub-BOMs for.
        include_top_level (bool): Whether to include the given item_code in the results. Default is True.

    Returns:
        dict: A dictionary where keys are BOM names and values are lists of item codes.
    """
    if not item_code:
        item_code = '300024'
    result = {}
    isolated_items = []

    def fetch_bom_items(bom_name):
        """Fetch items from a BOM and process sub-BOMs recursively."""
        # Fetch all BOM items
        bom_items = frappe.get_all(
            "BOM Item",
            fields=["item_code", "bom_no"],
            filters={"parent": bom_name, "docstatus": 1},
        )

        # Store items for this BOM
        result[bom_name] = []

        for item in bom_items:
            result[bom_name].append(item.item_code)
            # Stop if the 2nd digit of item_code is '0'
            if len(item.item_code) > 1 and item.item_code[1] == '0':
                isolated_items.append(item.item_code)
                continue
            # If the item has a sub-BOM, process it recursively
            if item.bom_no:
                fetch_bom_items(item.bom_no)

    # Fetch the main BOM for the item
    main_bom = frappe.get_value(
        "BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")
    if not main_bom:
        frappe.throw(f"No active default BOM found for Item: {item_code}")

    if include_top_level:
        result[main_bom] = [item_code]

    # Process the main BOM
    fetch_bom_items(main_bom)

    all_batch_data = {}

    for item in isolated_items:
        batch_data = get_batch_item_qty_per_warehouse(item)
        filtered_data = [entry for entry in batch_data if entry["total_qty"] != 0]
        if filtered_data:
            #print(filtered_data)
            all_batch_data[item] = filtered_data

    return isolated_items, all_batch_data

@frappe.whitelist()
def get_bom_batches(item_code):
    """
    Fetch plug and seat batch numbers for the given item_code from recursive BOM.

    Args:
        item_code (str): Item code to fetch batches for.

    Returns:
        dict: {
            "plug_batches": List of plug batch numbers,
            "seat_batches": List of seat batch numbers
        }
    """
    _, isolated_items = get_sub_bom_items(item_code)
    plug_batches = []
    seat_batches = []
    for item in isolated_items:
        batch_data = get_batch_item_qty_per_warehouse(item)
        for entry in batch_data:
            if entry["total_qty"] > 0 and entry["warehouse"] != 'Scrap - AMF21':
                print(entry)
                if item.startswith("1"):
                    plug_batches.append(entry["batch_no"])
                elif item.startswith("2"):
                    seat_batches.append(entry["batch_no"])

    return {
        "plug_batches": plug_batches,
        "seat_batches": seat_batches
    }

#########################################################################################################################
#########################################################################################################################
#########################################################################################################################
#########################################################################################################################

# File: amf/amf/utils/stock_entry.py

import frappe
from frappe import _
from frappe.utils import now_datetime
import datetime

# Constants
WH_TRANSFER = "Work In Progress - AMF21"
WH_MANUFACTURE = "Main Stock - AMF21"
EXPENSE_ACCOUNT = "4900 - Stock variation - AMF21"
COST_CENTER = "Automation - AMF21"

# ——— Doc Event Hooks —————————————————

def stock_entry_onload(doc, method):
    """
    Set auto-batch generation on load.
    """
    log_id = _get_or_create_log(doc)
    if not doc.auto_batch_generation_method:
        update_log_entry(log_id, f"[{now_datetime()}] Onload: auto_batch flag not set<br>")
    else:    
        for row in doc.items:
            row.auto_batch_no_generation = 1
        update_log_entry(log_id, f"[{now_datetime()}] Onload: auto_batch flag set for {len(doc.items)} row(s)<br>")


def stock_entry_validate(doc, method):
    """
    Apply defaults on Save & Submit.
    """
    log_id = _get_or_create_log(doc)
    if not doc.set_expense_and_cost_center_method:
        update_log_entry(log_id, f"[{now_datetime()}] Validate: set_expense and cost flag not set<br>")
    else:
        _set_expense_and_cost_center(doc)
        update_log_entry(log_id, f"[{now_datetime()}] Validate: set expense and cost flag set for {doc.name}<br>")
    if not doc.set_warehouse_defaults_method:
        update_log_entry(log_id, f"[{now_datetime()}] Validate: warehouse defaults flag not set<br>")
    else:
        _set_warehouse_defaults(doc, log_id)
        update_log_entry(log_id, f"[{now_datetime()}] Validate: applied expense, cost center, warehouse defaults<br>")

def stock_entry_before_save(doc, method):
    """
    Before Save:
    - Initialize or retrieve log entry
    - Update quantities and rates
    """
    log_id = _get_or_create_log(doc)
    if not doc.update_quantity_items_method:
        update_log_entry(log_id, f"[{now_datetime()}] Before Save: update quantity flag not set<br>")
    else:
        _update_quantities(doc, log_id)
        update_log_entry(log_id, f"[{now_datetime()}] Before Save: quantites set for {doc.name}<br>")
    # if not doc.update_rate_items_method:
    #     update_log_entry(log_id, f"[{now_datetime()}] Before Save: update rate flag not set<br>")
    # else:
    #     _update_rates(doc, log_id)
    #     update_log_entry(log_id, f"[{now_datetime()}] Before Save: rates set for {doc.name}<br>")
    
    if doc.update_quantity_items_method: # or doc.update_rate_items_method:
        # Retrieve log messages and display to user
        try:
            log = frappe.get_doc("Log Entry", log_id)
            # Show a popup with the log details
            frappe.msgprint(
                _(log.message),
                title=_("Changes Applied on Save"),
                indicator="green"
            )
        except Exception as e:
            frappe.log_error(message=str(e), title="Error displaying changes popup")
    

def stock_entry_before_submit(doc, method):
    """
    Main pipeline before submit:
      1) Initialize or retrieve same log entry
      2) Recalculate rates from the current rows
      3) Manufacture batch
      4) Batch assignment
    """
    log_id = _get_or_create_log(doc)
    try:
        update_log_entry(log_id, f"[{now_datetime()}] -- Submit recalculation: purpose={doc.purpose}, WO={doc.work_order} --<br>")
        # `before_save` is not executed during submit in Frappe, so any draft that goes
        # straight to submit would otherwise keep a stale finished-good rate.
        get_stock_and_rate_override(doc, method=method, log_id=log_id)
        update_log_entry(log_id, f"[{now_datetime()}] Submit recalculation completed<br>")
    except Exception as e:
        err_msg = f"Error recalculating rates before submit: {e}"
        update_log_entry(log_id, err_msg)
        frappe.log_error(err_msg, f"stock_entry_before_submit {doc.name}<br>")
        raise

    if not doc.handle_manufacture_batch_method:
        update_log_entry(log_id, f"[{now_datetime()}] Before Submit: handle manufacture batch flag not set<br>")
    else:
        try:
            update_log_entry(log_id, f"[{now_datetime()}] -- Manufacture step: purpose={doc.purpose}, WO={doc.work_order} --<br>")
            _handle_manufacture_batch(doc, log_id)
            update_log_entry(log_id, f"[{now_datetime()}] Manufacture step completed<br>")
        except Exception as e:
            err_msg = f"Error in before_submit pipeline: {e}"
            update_log_entry(log_id, err_msg)
            frappe.log_error(err_msg, f"stock_entry_before_submit {doc.name}<br>")
            raise
        
    if not doc.assign_batch_method:
        update_log_entry(log_id, f"[{now_datetime()}] Before Submit: assign batch flag not set<br>")
    else:
        try:
            update_log_entry(log_id, f"[{now_datetime()}] -- Batch assignment: {len(doc.items)} rows --<br>")
            _assign_batches(doc, log_id)
            update_log_entry(log_id, f"[{now_datetime()}] Batch assignment completed<br>")
        except Exception as e:
            err_msg = f"Error in before_submit pipeline: {e}"
            update_log_entry(log_id, err_msg)
            frappe.log_error(err_msg, f"stock_entry_before_submit {doc.name}<br>")
            raise
        
    if doc.handle_manufacture_batch_method or doc.assign_batch_method:
        # Retrieve log messages and display to user
        try:
            log = frappe.get_doc("Log Entry", log_id)
            # Show a popup with the log details
            frappe.msgprint(
                _(log.message),
                title=_("Changes Applied on Submit"),
                indicator="green"
            )
        except Exception as e:
            frappe.log_error(message=str(e), title="Error displaying changes popup<br>")


# ——— Internal Helpers —————————————————

def _set_expense_and_cost_center(doc):
    for row in doc.items:
        row.expense_account = EXPENSE_ACCOUNT
        if doc.purpose in ("Manufacture", "Material Transfer for Manufacture"):
            row.cost_center = COST_CENTER


def _set_warehouse_defaults(doc, log_id):
    if not doc.work_order:
        return
    prod = frappe.db.get_value("Work Order", doc.work_order, "production_item") or ""
    wip_step = frappe.db.get_value("Work Order", doc.work_order, "wip_step") or ""
    if not prod or prod.startswith(("10", "20")):
        return
    
    src = tgt = None

    if doc.purpose == "Manufacture" and not wip_step:
        doc.from_warehouse, doc.to_warehouse = WH_TRANSFER, WH_MANUFACTURE
        src, tgt = WH_TRANSFER, WH_MANUFACTURE
        update_log_entry(log_id, f"[{now_datetime()}] Warehouse Defaults: 'manufacture' src={src}, tgt={tgt}<br>")
    elif doc.purpose == "Manufacture" and wip_step:
        doc.from_warehouse = doc.to_warehouse = WH_MANUFACTURE
        src = tgt = WH_MANUFACTURE
        update_log_entry(log_id, f"[{now_datetime()}] Warehouse Defaults: 'manufacture skip wip' src={src}, tgt={tgt}<br>")
    elif doc.purpose == "Material Transfer for Manufacture":
        doc.from_warehouse, doc.to_warehouse = WH_MANUFACTURE, WH_TRANSFER
        src, tgt = WH_MANUFACTURE, WH_TRANSFER
        update_log_entry(log_id, f"[{now_datetime()}] Warehouse Defaults: 'transfer' src={src}, tgt={tgt}<br>")
    elif doc.purpose == "Material Issue":
        doc.from_warehouse = WH_MANUFACTURE
        src = WH_MANUFACTURE
        update_log_entry(log_id, f"[{now_datetime()}] Warehouse Defaults: 'issue' src={src}<br>")
    elif doc.purpose == "Material Receipt":
        doc.to_warehouse = WH_MANUFACTURE
        tgt = WH_MANUFACTURE
        update_log_entry(log_id, f"[{now_datetime()}] Warehouse Defaults: 'receipt' tgt={tgt}<br>")
    else:
        update_log_entry(log_id, f"[{now_datetime()}] No Warehouse Defaults: return<br>")
        return

    # Apply to each row, skipping last row for Manufacture purpose
    last_idx = len(doc.items) - 1
    for idx, row in enumerate(doc.items):
        # Manufacture: split source/target across rows
        if doc.purpose == "Manufacture":
            if idx < last_idx:
                if not row.manual_source_warehouse_selection:
                    row.s_warehouse = src
                    update_log_entry(log_id, f"[{now_datetime()}] Row {idx+1} - s_warehouse set to {src}<br>")
            else:
                if not row.manual_target_warehouse_selection:
                    row.t_warehouse = tgt
                    update_log_entry(log_id, f"[{now_datetime()}] Last row - t_warehouse set to {tgt}<br>")
        else:
            # Other purposes: apply whichever is set
            if src and not row.manual_source_warehouse_selection:
                row.s_warehouse = src
                update_log_entry(log_id, f"[{now_datetime()}] Row {idx+1} - s_warehouse set to {src}<br>")
            if tgt and not row.manual_target_warehouse_selection:
                row.t_warehouse = tgt
                update_log_entry(log_id, f"[{now_datetime()}] Row {idx+1} - t_warehouse set to {tgt}<br>")


def _handle_manufacture_batch(doc, log_id):
    """
    Apply spare or generate batch for production_item.
    """
    if doc.purpose != "Manufacture":
        update_log_entry(log_id, f"[{now_datetime()}] Skipped manufacture: purpose={doc.purpose}<br>")
        return
    if not doc.work_order:
        update_log_entry(log_id, f"[{now_datetime()}] Skipped manufacture: no work_order<br>")
        return

    wo = frappe.get_doc("Work Order", doc.work_order)
    prod_item = wo.production_item or ""
    if not prod_item:
        update_log_entry(log_id, f"[{now_datetime()}] Skipped manufacture: no production_item on WO<br>")
        return

    spare = wo.spare_batch_no if wo.spare_part_production else None
    # Find target row
    target = next((row for row in doc.items if row.item_code == prod_item), None)
    if not target:
        update_log_entry(log_id, f"[{now_datetime()}] Skipped manufacture: no row for {prod_item}<br>")
        return

    if spare:
        target.auto_batch_no_generation = 0
        target.batch_no = spare
        update_log_entry(log_id, f"[{now_datetime()}] Applied spare batch {spare} to {prod_item}<br>")
    else:
        update_log_entry(log_id, f"[{now_datetime()}] Generating batch for {prod_item}<br>")
        _assign_batch_for_row(target, doc, log_id)


def _assign_batches(doc, log_id):
    """
    Loop through doc.items and assign batches where needed.
    """
    # Cache has_batch_no values
    items = [row.item_code for row in doc.items if row.item_code]
    # Fetch has_batch_no flags in bulk
    batch_records = frappe.get_all(
        "Item",
        filters={"item_code": ["in", items]},
        fields=["item_code", "has_batch_no"]
    )
    batch_map = {rec["item_code"]: rec["has_batch_no"] for rec in batch_records}

    for row in doc.items:
        _assign_batch_for_row(row, doc, log_id, batch_map)


def _assign_batch_for_row(row, doc, log_id, batch_map=None):
    """
    Create or reuse batch for a single row.
    """
    item = row.item_code or None
    if not item:
        update_log_entry(log_id, f"[{now_datetime()}] Row skipped: no item_code<br>")
        return
    if row.batch_no:
        update_log_entry(log_id, f"[{now_datetime()}] Row {item}: existing batch {row.batch_no}<br>")
        return

    # Determine if batch needed
    has_batch = batch_map.get(item) if batch_map else frappe.db.get_value("Item", item, "has_batch_no") or 0
    if has_batch != 1 or row.auto_batch_no_generation != 1:
        update_log_entry(log_id, f"[{now_datetime()}] Row {item}: batch not required or auto-gen off<br>")
        return

    ts = now_datetime().strftime("%Y%m%d%H%M%S")
    batch_id = f"{ts} {item}"

    if not frappe.db.exists("Batch", batch_id):
        batch = frappe.get_doc({
            "doctype": "Batch",
            "item": item,
            "batch_id": batch_id
        }).insert(ignore_permissions=True)
        row.batch_no = batch.name
        update_log_entry(log_id, f"[{now_datetime()}] Row {item}: created batch {batch.name}<br>")
    else:
        row.batch_no = batch_id
        update_log_entry(log_id, f"[{now_datetime()}] Row {item}: reused batch {batch_id}<br>")


def _update_quantities(doc, log_id):
    """
    Update each row's quantity based on BOM and fg_completed_qty.
    """
    bom_no = doc.bom_no
    fg_qty = doc.fg_completed_qty or 0
    if not bom_no or fg_qty <= 0:
        update_log_entry(log_id, f"[{now_datetime()}] Quantity update skipped: bom_no={bom_no}, fg_qty={fg_qty}<br>")
        return

    # Fetch BOM Item entries
    bom_items = frappe.get_all(
        "BOM Item",
        filters={"parent": bom_no},
        fields=["item_code", "qty"]
    )
    rate_map = {bi.item_code: bi.qty for bi in bom_items}

    for row in doc.items:
        code = row.item_code
        if code in rate_map:
            new_qty = rate_map[code] * fg_qty
            row.qty = new_qty
            update_log_entry(log_id, f"[{now_datetime()}] Qty set for bom item {code}: {new_qty}<br>")
        elif code == frappe.db.get_value("BOM", {"name": bom_no}, "item"):
            row.qty = fg_qty
            update_log_entry(log_id, f"[{now_datetime()}] Qty set for production item {code}: {fg_qty}<br>")
        else:
            update_log_entry(log_id, f"[{now_datetime()}] Qty unchanged for {code}: not in BOM<br>")


def _update_rates(doc, log_id):
    """
    Fetch and set basic_rate from BOM.
    """
    doc.get_stock_and_rate()
    cache = {}
    for row in doc.items:
        item = row.item_code or None
        if not item:
            update_log_entry(log_id, f"[{now_datetime()}] Rate skip: no item_code<br>")
            continue

        if item in cache:
            rate = cache[item]
        else:
            bom = frappe.db.get_value(
                "BOM",
                {"item": item, "is_default": 1, "is_active": 1},
                "name"
            )
            if not bom:
                update_log_entry(log_id, f"[{now_datetime()}] No BOM for {item}<br>")
                cache[item] = None
                rate = None
            else:
                rate = frappe.db.get_value(
                    "BOM",
                    {"name": bom, "item": item},
                    "total_cost"
                ) or frappe.throw(_(f"[{now_datetime()}] Rate missing for {item} in BOM {bom}"))
                cache[item] = rate

        if rate is not None:
            row.basic_rate = rate
            update_log_entry(log_id, f"[{now_datetime()}] Row {item}: rate set {rate}<br>")


# ——— Log Handling Utilities —————————————————

def _get_or_create_log(doc):
    """
    Retrieve existing Log Entry for this Stock Entry or create a new one.
    """
    reference = f"{doc.doctype}: {doc.name}"
    existing = frappe.get_all(
        "Log Entry",
        filters={"reference_name": reference},
        order_by="creation desc",
        limit_page_length=1,
        fields=["name"]
    )
    if existing:
        return existing[0].name
    # not found → create
    msg = f"[{now_datetime()}] {doc.doctype} {doc.name} initiated"
    return create_log_entry(msg, doc.doctype, reference)

def create_log_entry(message, category, name):
    """
    Create a new Log Entry and return its ID.
    """
    # log = frappe.get_doc({
    #     "doctype": "Log Entry",
    #     "timestamp": datetime.datetime.now(),
    #     "category": category,
    #     "message": message,
    #     "reference_name": name,
    # }).insert(ignore_permissions=True)
    # frappe.db.commit()
    # return log.name


def update_log_entry(log_id, message):
    """
    Append a message to an existing Log Entry.
    """
    # log = custom_try(frappe.get_doc, "Log Entry", log_id)
    # if not log:
    #     return
    # log.message = (log.message or "") + "\n" + (message or "")
    # custom_try(log.save, ignore_permissions=True)


def custom_try(func, *args, **kwargs):
    """
    Execute func safely, logging exceptions.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        frappe.log_error(message=str(e), title=f"Error in {func.__name__}")
        frappe.db.rollback()
        return None


########################################################################################################
########################################################################################################
########################################################################################################
########################################################################################################

@frappe.whitelist()
def check_rates_and_assign_on_submit(doc, method):
    """
    This function is called on the 'on_submit' event for Stock Entries.

    It performs two checks:
    1. If the 'value_difference' of the Stock Entry is not zero.
    2. If the 'basic_rate' of any item in the entry is more than 10% higher
       than its current valuation rate in the source warehouse.

    If both conditions are met, it assigns the document to the user who submitted it
    and creates a ToDo with a message to review the entry.
    """
    if not doc.valuation_rate_assignee:
        print("doc.valuation_rate_assignee checked. Return.")
        return
    
    # This hook runs on submit, so docstatus will be 1. This is a safeguard.
    if doc.docstatus != 1:
        return

    # --- Condition 1: Check if 'value_difference' is non-zero ---
    # If there's no value difference, no need to proceed.
    if not doc.value_difference:
        return

    rate_exceeded = False
    rate_check_details = [] # To store details for the assignment message

    # --- Condition 2: Check item rates against their valuation rate ---
    for item_detail in doc.items:

        try:
            # Get the last valuation rate for the item from its source warehouse.
            # This is the most accurate representation of the item's cost before this transaction.
            valuation_rate = frappe.db.get_value(
                "Bin",
                {"item_code": item_detail.item_code, "warehouse": item_detail.s_warehouse},
                "valuation_rate"
            )
            
            # If valuation_rate is 0, fetch the cost from the item's default BOM as a fallback.
            if not valuation_rate:
                default_bom = frappe.db.get_value("BOM", {"item": item_detail.item_code, "is_default": 1}, "name")
                if default_bom:
                    # Get the total cost from the BOM document
                    bom_cost = frappe.db.get_value("BOM", default_bom, "total_cost")
                    if bom_cost:
                        valuation_rate = bom_cost

            # If valuation_rate is 0 or None, we can't do a percentage comparison.
            # We'll skip the check for this item.
            if not valuation_rate:
                continue

            # Calculate the threshold (Valuation Rate + 10%)
            threshold_rate = valuation_rate * 1.10

            # Compare the item's rate in the Stock Entry with the threshold.
            #print(item_detail.basic_rate, threshold_rate)
            if item_detail.basic_rate > threshold_rate:
                rate_exceeded = True
                
                # Store info for a more detailed ToDo message
                rate_check_details.append(
                    f"Item: {item_detail.item_code}, "
                    f"Rate: {item_detail.basic_rate}, "
                    f"Valuation: {valuation_rate}"
                )
                
                # Optimization: If we find one item that exceeds the rate,
                # we don't need to check the rest. We can break the loop.
                break

        except Exception as e:
            # Log any potential errors during valuation rate fetching
            frappe.log_error(
                message=f"Error fetching valuation rate for {item_detail.item_code} in Stock Entry {doc.name}: {e}",
                title="Stock Entry Rate Check Failed"
            )
            continue

    # --- Action: Assign and create ToDo if both conditions are met ---
    if rate_exceeded:
        # The user who submitted the document is frappe.session.user
        assignee = "alexandre.ringwald@amf.ch"
        
        # Create a clear description for the ToDo
        description = _(
            "Please review this Stock Entry. "
            "It has a Value Difference of {0} and at least one item's rate is over 10% of its cost. Details: {1}"
        ).format(doc.get_formatted("value_difference"), "; ".join(rate_check_details))

        # Create a new ToDo document, which handles the assignment
        frappe.get_doc({
            "doctype": "ToDo",
            "owner": assignee,
            "assigned_by": frappe.session.user,
            "reference_type": doc.doctype,
            "reference_name": doc.name,
            "description": description,
            "status": "Open",
            "priority": "High",
            "color": "#ff4d4d"
        }).insert(ignore_permissions=True) # ignore_permissions to ensure it's created by the system


########################################################################################################

@frappe.whitelist()
def get_stock_and_rate_override(doc, method = None, log_id = None):
    """ 
    override of get_stock_and_rate() function for a better gestion of scraps item in stock entry

    """
    if doc.ignore_rate_calculation:
        print("get_stock_and_rate_override: ignore_rate_calculation flag set. Return.")
        return
    
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)
    if isinstance(doc, dict):
        doc = frappe.get_doc(doc)  
    
    if not log_id:
        # creating a new log entry doc
        context = _dict(doctype="Stock Entry", name = f"get_stock_and_rate_override for  {doc.name}")
        log_id = _get_or_create_log(context)
    update_log_entry(log_id, f"[{now_datetime()}] get_stock_and_rate_override started for {doc.name}<br>")

    #classic function call
    doc.set_work_order_details()
    update_log_entry(log_id, f"[{now_datetime()}] Set work order details for {doc.name}<br>")
    doc.set_transfer_qty()
    update_log_entry(log_id, f"[{now_datetime()}] Set transfer qty for {doc.name}<br>")
    doc.set_actual_qty()
    update_log_entry(log_id, f"[{now_datetime()}] Set actual qty for {doc.name}<br>")

    
    update_log_entry(log_id, f"[{now_datetime()}] Finished setting work order details for {doc.name}<br>")
    #calculate_rate_and_amount_override
    set_basic_rate_override(doc, log_id=log_id)
    #classic function call
    doc.distribute_additional_costs()
    doc.update_valuation_rate()
    doc.set_total_incoming_outgoing_value()
    doc.set_total_amount()

    if method is None:
        doc.save()


def _get_disabled_batch_numbers(items):
    batch_nos = sorted({row.batch_no for row in (items or []) if row.batch_no})
    if not batch_nos:
        return []

    disabled_batches = frappe.get_all(
        "Batch",
        filters={
            "name": ["in", batch_nos],
            "disabled": 1,
        },
        fields=["name"],
    )
    return [row.name for row in disabled_batches]


def _set_batch_disabled_state(batch_nos, disabled):
    for batch_no in batch_nos or []:
        frappe.db.set_value("Batch", batch_no, "disabled", disabled, update_modified=False)


@frappe.whitelist()
def repair_manufacture_stock_entries(stock_entry_names, dry_run=True, cancel_original=True):
    """
    Repair submitted non-serialized manufacture entries by:
      1) duplicating the original entry,
      2) recalculating the duplicate with the current rows and posting datetime,
      3) submitting the corrected duplicate,
      4) cancelling the original entry.

    The duplicate is submitted first so later stock movements keep enough stock during the
    repair window. Serialized entries must use repair_serialized_manufacture_stock_entries()
    because they cannot safely coexist twice before the original is cancelled. Automatic
    repair only proceeds when the recalculation materially changes the entry and brings
    value_difference back to zero.
    """
    return _run_repair_handler(
        stock_entry_names,
        dry_run=dry_run,
        cancel_original=cancel_original,
        repair_handler=_repair_manufacture_stock_entry,
        error_title="repair_manufacture_stock_entries",
    )


@frappe.whitelist()
def repair_serialized_manufacture_stock_entries(stock_entry_names, dry_run=True, cancel_original=True):
    """
    Repair submitted serialized manufacture entries by:
      1) recalculating a duplicate in memory,
      2) cancelling the original entry inside the same transaction,
      3) inserting and submitting the recalculated replacement.

    This path avoids a temporary duplicate presence of the same serial numbers. Live repair
    requires cancel_original=1 because the original must be reversed before the replacement
    can be submitted safely.
    """
    return _run_repair_handler(
        stock_entry_names,
        dry_run=dry_run,
        cancel_original=cancel_original,
        repair_handler=_repair_serialized_manufacture_stock_entry,
        error_title="repair_serialized_manufacture_stock_entries",
    )


@frappe.whitelist()
def repair_problematic_manufacture_stock_entries(
    from_date="2026-01-01",
    to_date="2026-12-31",
    dry_run=False,
    cancel_original=True,
    include_results=True,
):
    """
    Bulk wrapper for manufacture repairs:
      - selects submitted Manufacture stock entries on/after from_date
      - optionally limits the selection to posting_date on/before to_date
      - keeps only entries with a non-zero value_difference
      - passes the names to repair_manufacture_stock_entries()
    """
    filters = [
        ["Stock Entry", "docstatus", "=", 1],
        ["Stock Entry", "purpose", "=", "Manufacture"],
        ["Stock Entry", "posting_date", ">=", from_date],
        ["Stock Entry", "value_difference", "!=", 0],
    ]
    if to_date:
        filters.append(["Stock Entry", "posting_date", "<=", to_date])

    stock_entries = frappe.get_all(
        "Stock Entry",
        filters=filters,
        fields=["name"],
        order_by="posting_date asc, name asc",
        limit_page_length=0,
    )
    stock_entry_names = [row.name for row in stock_entries]
    results = repair_manufacture_stock_entries(
        stock_entry_names,
        dry_run=dry_run,
        cancel_original=cancel_original,
    )

    return _build_bulk_repair_response(
        stock_entry_names,
        results,
        from_date=from_date,
        to_date=to_date,
        dry_run=dry_run,
        cancel_original=cancel_original,
        include_results=include_results,
    )


@frappe.whitelist()
def repair_problematic_serialized_manufacture_stock_entries(
    from_date="2026-01-01",
    to_date="2026-12-31",
    dry_run=False,
    cancel_original=True,
    include_results=True,
):
    """
    Bulk wrapper for serialized manufacture repairs.
    """
    query = """
        select distinct se.name
        from `tabStock Entry` se
        inner join `tabStock Entry Detail` sed on sed.parent = se.name
        where se.docstatus = 1
          and se.purpose = 'Manufacture'
          and se.posting_date >= %(from_date)s
          and se.value_difference != 0
          and ifnull(sed.serial_no, '') != ''
    """
    params = {"from_date": from_date}
    if to_date:
        query += " and se.posting_date <= %(to_date)s"
        params["to_date"] = to_date
    query += " order by se.posting_date asc, se.name asc"

    stock_entries = frappe.db.sql(query, params, as_dict=True)
    stock_entry_names = [row.name for row in stock_entries]
    results = repair_serialized_manufacture_stock_entries(
        stock_entry_names,
        dry_run=dry_run,
        cancel_original=cancel_original,
    )

    return _build_bulk_repair_response(
        stock_entry_names,
        results,
        from_date=from_date,
        to_date=to_date,
        dry_run=dry_run,
        cancel_original=cancel_original,
        include_results=include_results,
    )


def _row_get(row, fieldname):
    if isinstance(row, dict):
        return row.get(fieldname)
    return getattr(row, fieldname, None)


SERIAL_NO_STATE_FIELDS = (
    "warehouse",
    "batch_no",
    "location",
    "company",
    "supplier",
    "supplier_name",
    "sales_order",
    "purchase_document_type",
    "purchase_document_no",
    "purchase_date",
    "purchase_time",
    "purchase_rate",
    "delivery_document_type",
    "delivery_document_no",
    "delivery_date",
    "delivery_time",
    "customer",
    "customer_name",
    "sales_invoice",
    "warranty_expiry_date",
    "maintenance_status",
)


def _split_serial_numbers(serial_no_value):
    serial_no_value = (serial_no_value or "").replace(",", "\n")
    return [serial_no.strip() for serial_no in serial_no_value.splitlines() if serial_no.strip()]


@frappe.whitelist()
def correct_submitted_manufacture_qty(
    stock_entry_name,
    new_fg_completed_qty=None,
    dry_run=False,
    allow_negative_stock=True,
    update_work_order_qty=True,
    reason='Manufacture Correction',
    balance_value_difference=True,
):
    """
    Correct the manufactured quantity of a submitted Manufacture Stock Entry.

    This intentionally bypasses normal submitted-document editing, then rebuilds
    the stock and accounting ledgers from the corrected rows. It is meant for a
    narrow historical repair where cancelling/amending the entry is no longer
    practical because later batch movements exist. When balance_value_difference
    is enabled, the finished-good valuation is adjusted so total incoming and
    outgoing values net to zero before ledgers are reposted.
    """
    frappe.only_for(("System Manager", "Stock Manager", "Manufacturing Manager"))

    stock_entry_name = (stock_entry_name or "").strip()
    new_fg_completed_qty = None if new_fg_completed_qty in (None, "") else flt(new_fg_completed_qty)
    dry_run = frappe.utils.cint(dry_run)
    allow_negative_stock = frappe.utils.cint(allow_negative_stock)
    update_work_order_qty = frappe.utils.cint(update_work_order_qty)
    balance_value_difference = frappe.utils.cint(balance_value_difference)

    if not stock_entry_name:
        frappe.throw(_("Stock Entry is required."))
    if not frappe.db.exists("Stock Entry", stock_entry_name):
        frappe.throw(_("Stock Entry {0} does not exist.").format(stock_entry_name))

    if not dry_run:
        frappe.db.sql("set innodb_lock_wait_timeout = 300")
        frappe.db.sql(
            "select name from `tabStock Entry` where name=%s for update",
            stock_entry_name,
        )

    stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
    if new_fg_completed_qty is None:
        new_fg_completed_qty = flt(stock_entry.fg_completed_qty)
    if new_fg_completed_qty <= 0:
        frappe.throw(_("New manufactured quantity must be greater than zero."))

    plan = _build_manufacture_qty_correction_plan(
        stock_entry,
        new_fg_completed_qty,
        update_work_order_qty=update_work_order_qty,
        balance_value_difference=balance_value_difference,
    )

    if plan["status"] in ("blocked", "noop") or dry_run:
        if plan["status"] == "ready":
            plan["status"] = "dry_run"
            plan["message"] = _("Preview ready. No changes were posted.")
        return plan

    existing_allow_negative_stock = frappe.db.get_value(
        "Stock Settings",
        None,
        "allow_negative_stock",
    )

    try:
        if allow_negative_stock:
            frappe.db.set_value(
                "Stock Settings",
                None,
                "allow_negative_stock",
                1,
                update_modified=False,
            )

        result = _apply_manufacture_qty_correction(
            stock_entry,
            plan,
            allow_negative_stock=allow_negative_stock,
            reason=reason,
        )

        if allow_negative_stock:
            frappe.db.set_value(
                "Stock Settings",
                None,
                "allow_negative_stock",
                existing_allow_negative_stock,
                update_modified=False,
            )

        frappe.db.commit()
        return result
    except Exception:
        frappe.db.rollback()
        if allow_negative_stock:
            frappe.db.set_value(
                "Stock Settings",
                None,
                "allow_negative_stock",
                existing_allow_negative_stock,
                update_modified=False,
            )
            frappe.db.commit()
        raise


def _build_manufacture_qty_correction_plan(
    stock_entry,
    new_fg_completed_qty,
    update_work_order_qty=True,
    balance_value_difference=True,
):
    current_qty = flt(stock_entry.fg_completed_qty)
    production_item = _get_manufacture_production_item(stock_entry)
    precision = _get_doc_precision(stock_entry, "fg_completed_qty")
    new_fg_completed_qty = flt(new_fg_completed_qty, precision)
    qty_changed = abs(current_qty - new_fg_completed_qty) > 0.000001
    plan = {
        "stock_entry": stock_entry.name,
        "status": "ready",
        "work_order": stock_entry.work_order,
        "posting_date": stock_entry.posting_date,
        "posting_time": stock_entry.posting_time,
        "production_item": production_item,
        "current_fg_completed_qty": current_qty,
        "new_fg_completed_qty": new_fg_completed_qty,
        "quantity_will_update": 1 if qty_changed else 0,
        "ratio": 0,
        "rows": [],
        "serial_conflicts": [],
        "update_work_order_qty": frappe.utils.cint(update_work_order_qty),
        "balance_value_difference": frappe.utils.cint(balance_value_difference),
        "total_incoming_value_before": flt(stock_entry.total_incoming_value),
        "total_outgoing_value_before": flt(stock_entry.total_outgoing_value),
        "value_difference_before": flt(stock_entry.value_difference),
        "total_incoming_value_after": None,
        "total_outgoing_value_after": None,
        "value_difference_after": None,
        "value_balance": {},
        "work_order_qty_will_update": 0,
        "work_order_qty_before": None,
        "message": None,
    }

    def block(message):
        plan["status"] = "blocked"
        plan["message"] = message
        return plan

    if stock_entry.docstatus != 1:
        return block(_("Only submitted Stock Entries can be corrected."))
    if stock_entry.purpose != "Manufacture":
        return block(_("Only Manufacture Stock Entries are supported."))
    if current_qty <= 0:
        return block(_("Current manufactured quantity must be greater than zero."))

    if not qty_changed and (
        not plan["balance_value_difference"]
        or abs(flt(stock_entry.value_difference)) <= 0.000001
    ):
        plan["status"] = "noop"
        plan["message"] = _("Stock Entry already has this manufactured quantity and value balance.")
        return plan

    ratio = plan["new_fg_completed_qty"] / current_qty
    plan["ratio"] = flt(ratio, 9)

    finished_good_rows = [
        row for row in stock_entry.items
        if _is_finished_good_row(stock_entry, row, production_item)
    ]
    if not finished_good_rows:
        return block(_("Could not identify the finished good row to correct."))

    single_finished_good_row = finished_good_rows[0] if len(finished_good_rows) == 1 else None
    if plan["balance_value_difference"] and (
        not single_finished_good_row or single_finished_good_row.s_warehouse
    ):
        return block(_(
            "Value balancing requires exactly one target-only finished good row."
        ))

    for row in stock_entry.items:
        row_precision = _get_doc_precision(row, "qty")
        transfer_precision = _get_doc_precision(row, "transfer_qty")
        old_qty = flt(row.qty)
        old_transfer_qty = flt(row.transfer_qty)

        if single_finished_good_row and row.name == single_finished_good_row.name:
            new_qty = plan["new_fg_completed_qty"]
        else:
            new_qty = flt(old_qty * ratio, row_precision)

        conversion_factor = flt(row.conversion_factor) or 1
        new_transfer_qty = flt(new_qty * conversion_factor, transfer_precision)
        serial_numbers = _split_serial_numbers(row.serial_no)
        is_finished_good = row in finished_good_rows
        is_scrap = _is_scrap_row(stock_entry, row)

        row_plan = {
            "name": row.name,
            "idx": row.idx,
            "item_code": row.item_code,
            "s_warehouse": row.s_warehouse,
            "t_warehouse": row.t_warehouse,
            "batch_no": row.batch_no,
            "serial_count": len(serial_numbers),
            "is_finished_good": 1 if is_finished_good else 0,
            "is_scrap": 1 if is_scrap else 0,
            "old_qty": old_qty,
            "new_qty": new_qty,
            "old_transfer_qty": old_transfer_qty,
            "new_transfer_qty": new_transfer_qty,
        }
        plan["rows"].append(row_plan)

        if serial_numbers and abs(abs(new_transfer_qty) - len(serial_numbers)) > 0.000001:
            plan["serial_conflicts"].append({
                "row": row.idx,
                "item_code": row.item_code,
                "new_transfer_qty": new_transfer_qty,
                "serial_count": len(serial_numbers),
            })

    if plan["serial_conflicts"]:
        return block(_(
            "This Stock Entry has serialized rows whose serial count would not match the corrected quantity."
        ))

    if qty_changed and stock_entry.work_order and update_work_order_qty:
        work_order_qty = flt(frappe.db.get_value("Work Order", stock_entry.work_order, "qty"))
        plan["work_order_qty_before"] = work_order_qty
        if abs(work_order_qty - current_qty) <= 0.000001:
            plan["work_order_qty_will_update"] = 1

    _prepare_manufacture_qty_correction_value_preview(stock_entry, plan)
    return plan


def _apply_manufacture_qty_correction(stock_entry, plan, allow_negative_stock=True, reason=None):
    _apply_planned_quantities_to_stock_entry(stock_entry, plan)
    balance_result = _recalculate_stock_entry_amounts_from_existing_rates(
        stock_entry,
        balance_value_difference=plan.get("balance_value_difference"),
    )
    _set_plan_value_totals_from_stock_entry(plan, stock_entry, balance_result)
    if balance_result.get("status") == "blocked":
        frappe.throw(balance_result.get("message"))
    _append_qty_correction_note(stock_entry, plan, reason)

    stock_entry.modified = frappe.utils.now()
    stock_entry.modified_by = frappe.session.user
    stock_entry.db_update()
    for row in stock_entry.items:
        row.db_update()

    ledger_result = _rebuild_stock_entry_ledgers(
        stock_entry,
        allow_negative_stock=allow_negative_stock,
    )
    work_order_result = _sync_work_order_after_manufacture_qty_correction(stock_entry, plan)
    _add_qty_correction_comment(stock_entry, plan, reason, work_order_result)

    frappe.clear_document_cache("Stock Entry", stock_entry.name)
    if stock_entry.work_order:
        frappe.clear_document_cache("Work Order", stock_entry.work_order)

    result = dict(plan)
    result.update(ledger_result)
    result["work_order_result"] = work_order_result
    result["status"] = "updated"
    result["message"] = _("Manufacture correction posted and ledgers reposted.")
    return result


def _apply_planned_quantities_to_stock_entry(stock_entry, plan):
    rows_by_name = {row.name: row for row in stock_entry.items}
    stock_entry.fg_completed_qty = plan["new_fg_completed_qty"]

    for row_plan in plan["rows"]:
        row = rows_by_name[row_plan["name"]]
        row.qty = row_plan["new_qty"]
        row.transfer_qty = row_plan["new_transfer_qty"]


def _prepare_manufacture_qty_correction_value_preview(stock_entry, plan):
    _apply_planned_quantities_to_stock_entry(stock_entry, plan)
    balance_result = _recalculate_stock_entry_amounts_from_existing_rates(
        stock_entry,
        balance_value_difference=plan.get("balance_value_difference"),
    )
    _set_plan_value_totals_from_stock_entry(plan, stock_entry, balance_result)

    if balance_result.get("status") == "blocked":
        plan["status"] = "blocked"
        plan["message"] = balance_result.get("message")


def _set_plan_value_totals_from_stock_entry(plan, stock_entry, balance_result=None):
    plan["total_incoming_value_after"] = flt(stock_entry.total_incoming_value)
    plan["total_outgoing_value_after"] = flt(stock_entry.total_outgoing_value)
    plan["value_difference_after"] = flt(stock_entry.value_difference)
    plan["value_balance"] = balance_result or {}


def _recalculate_stock_entry_amounts_from_existing_rates(stock_entry, balance_value_difference=False):
    raw_material_cost = 0.0
    scrap_material_cost = 0.0
    finished_good_rows = []
    balance_result = {
        "requested": frappe.utils.cint(balance_value_difference),
        "status": "not_requested",
    }

    for row in stock_entry.items:
        row.basic_amount = flt(
            flt(row.transfer_qty) * flt(row.basic_rate),
            _get_doc_precision(row, "basic_amount"),
        )

        if row.s_warehouse and not row.t_warehouse:
            raw_material_cost += flt(row.basic_amount)
        elif row.t_warehouse and _is_scrap_row(stock_entry, row):
            scrap_material_cost += flt(row.basic_amount)
        elif row.t_warehouse:
            finished_good_rows.append(row)

    if len(finished_good_rows) == 1 and flt(finished_good_rows[0].transfer_qty):
        finished_good = finished_good_rows[0]
        finished_good_basic_amount = raw_material_cost - scrap_material_cost
        if balance_value_difference:
            finished_good_basic_amount -= _get_total_additional_costs(stock_entry)

        if balance_value_difference and finished_good_basic_amount < -0.000001:
            return {
                "requested": 1,
                "status": "blocked",
                "message": _(
                    "Cannot balance values because the finished good amount would become negative."
                ),
                "calculated_basic_amount": flt(finished_good_basic_amount),
            }

        _set_row_basic_amount_and_rate(
            finished_good,
            max(finished_good_basic_amount, 0.0)
            if balance_value_difference else finished_good_basic_amount,
        )

    stock_entry.distribute_additional_costs()
    stock_entry.update_valuation_rate()
    stock_entry.set_total_incoming_outgoing_value()
    stock_entry.set_total_amount()
    if balance_value_difference:
        balance_result = _balance_stock_entry_value_difference(
            stock_entry,
            finished_good_rows,
        )

    return balance_result


def _get_total_additional_costs(stock_entry):
    if hasattr(stock_entry, "get"):
        additional_costs = stock_entry.get("additional_costs") or []
    else:
        additional_costs = getattr(stock_entry, "additional_costs", []) or []

    return sum(flt(row.amount) for row in additional_costs)


def _set_row_basic_amount_and_rate(row, basic_amount):
    row.basic_amount = flt(
        basic_amount,
        _get_doc_precision(row, "basic_amount"),
    )
    if flt(row.transfer_qty):
        row.basic_rate = flt(
            flt(row.basic_amount) / flt(row.transfer_qty),
            _get_doc_precision(row, "basic_rate"),
        )


def _set_row_amount_and_rates(row, amount):
    amount = flt(amount, _get_doc_precision(row, "amount"))
    additional_cost = flt(row.additional_cost)
    row.amount = amount
    row.basic_amount = flt(
        amount - additional_cost,
        _get_doc_precision(row, "basic_amount"),
    )

    if flt(row.transfer_qty):
        row.basic_rate = flt(
            flt(row.basic_amount) / flt(row.transfer_qty),
            _get_doc_precision(row, "basic_rate"),
        )
        row.valuation_rate = flt(
            amount / flt(row.transfer_qty),
            _get_doc_precision(row, "valuation_rate"),
        )


def _balance_stock_entry_value_difference(stock_entry, finished_good_rows):
    if len(finished_good_rows) != 1:
        return {
            "requested": 1,
            "status": "blocked",
            "message": _("Value balancing requires exactly one finished good row."),
        }

    finished_good = finished_good_rows[0]
    if finished_good.s_warehouse or not finished_good.t_warehouse:
        return {
            "requested": 1,
            "status": "blocked",
            "message": _("Value balancing requires a target-only finished good row."),
        }

    if not flt(finished_good.transfer_qty):
        return {
            "requested": 1,
            "status": "blocked",
            "message": _("Cannot balance values for a zero-quantity finished good row."),
        }

    value_precision = _get_doc_precision(stock_entry, "value_difference", default=2)
    amount_precision = _get_doc_precision(finished_good, "amount", default=value_precision)
    difference_before = flt(stock_entry.value_difference)
    amount_before = flt(finished_good.amount)
    rounded_difference = flt(difference_before, amount_precision)

    if rounded_difference:
        balanced_amount = flt(amount_before - rounded_difference, amount_precision)
        if balanced_amount < -0.000001:
            return {
                "requested": 1,
                "status": "blocked",
                "message": _(
                    "Cannot balance values because the finished good amount would become negative."
                ),
                "amount_before": amount_before,
                "calculated_amount": balanced_amount,
                "value_difference_before": difference_before,
            }

        _set_row_amount_and_rates(finished_good, max(balanced_amount, 0.0))
        stock_entry.set_total_incoming_outgoing_value()

    final_difference = flt(stock_entry.value_difference, value_precision)
    if final_difference:
        balanced_amount = flt(flt(finished_good.amount) - final_difference, amount_precision)
        if balanced_amount < -0.000001:
            return {
                "requested": 1,
                "status": "blocked",
                "message": _(
                    "Cannot balance values because the finished good amount would become negative."
                ),
                "amount_before": amount_before,
                "calculated_amount": balanced_amount,
                "value_difference_before": difference_before,
            }

        _set_row_amount_and_rates(finished_good, max(balanced_amount, 0.0))
        stock_entry.set_total_incoming_outgoing_value()

    final_difference = flt(stock_entry.value_difference, value_precision)
    if final_difference:
        return {
            "requested": 1,
            "status": "blocked",
            "message": _("Could not fully balance the value difference."),
            "row": finished_good.idx,
            "item_code": finished_good.item_code,
            "amount_before": amount_before,
            "amount_after": flt(finished_good.amount),
            "adjustment": flt(flt(finished_good.amount) - amount_before),
            "value_difference_before": difference_before,
            "value_difference_after": flt(stock_entry.value_difference),
        }

    stock_entry.value_difference = 0.0
    return {
        "requested": 1,
        "status": "balanced",
        "row": finished_good.idx,
        "item_code": finished_good.item_code,
        "amount_before": amount_before,
        "amount_after": flt(finished_good.amount),
        "adjustment": flt(flt(finished_good.amount) - amount_before),
        "value_difference_before": difference_before,
        "value_difference_after": 0.0,
    }


def _rebuild_stock_entry_ledgers(stock_entry, allow_negative_stock=True):
    from erpnext.accounts.general_ledger import delete_gl_entries

    deleted_sle_count = frappe.db.count(
        "Stock Ledger Entry",
        {"voucher_type": stock_entry.doctype, "voucher_no": stock_entry.name},
    )
    deleted_gl_count = frappe.db.count(
        "GL Entry",
        {"voucher_type": stock_entry.doctype, "voucher_no": stock_entry.name},
    )

    delete_gl_entries(voucher_type=stock_entry.doctype, voucher_no=stock_entry.name)
    frappe.db.sql(
        "delete from `tabStock Ledger Entry` where voucher_type=%s and voucher_no=%s",
        (stock_entry.doctype, stock_entry.name),
    )

    if allow_negative_stock:
        stock_entry.make_sl_entries = (
            lambda sl_entries, is_amended=None, allow_negative_stock=False, via_landed_cost_voucher=False:
            stock_entry.__class__.make_sl_entries(
                stock_entry,
                sl_entries,
                is_amended=is_amended,
                allow_negative_stock=True,
                via_landed_cost_voucher=via_landed_cost_voucher,
            )
        )

    stock_entry.update_stock_ledger()
    stock_entry.make_gl_entries()

    return {
        "deleted_stock_ledger_entries": deleted_sle_count,
        "deleted_gl_entries": deleted_gl_count,
        "new_stock_ledger_entries": frappe.db.count(
            "Stock Ledger Entry",
            {"voucher_type": stock_entry.doctype, "voucher_no": stock_entry.name},
        ),
        "new_gl_entries": frappe.db.count(
            "GL Entry",
            {"voucher_type": stock_entry.doctype, "voucher_no": stock_entry.name},
        ),
    }


def _sync_work_order_after_manufacture_qty_correction(stock_entry, plan):
    if not stock_entry.work_order:
        return {}

    work_order = frappe.get_doc("Work Order", stock_entry.work_order)
    result = {
        "work_order": work_order.name,
        "qty_before": flt(work_order.qty),
        "qty_updated": 0,
        "status_before": work_order.status,
    }

    if plan.get("update_work_order_qty") and plan.get("work_order_qty_will_update"):
        work_order.qty = plan["new_fg_completed_qty"]
        if work_order.bom_no:
            work_order.set_required_items(reset_only_qty=True)

        work_order.db_update()
        for row in work_order.get("required_items"):
            row.db_update()

        result["qty_updated"] = 1

    work_order.update_work_order_qty()
    result["status_after"] = work_order.update_status()

    if result["qty_updated"]:
        work_order.update_work_order_qty_in_so()
        work_order.update_completed_qty_in_material_request()
        work_order.update_planned_qty()
        work_order.update_ordered_qty()

    result["qty_after"] = flt(frappe.db.get_value("Work Order", work_order.name, "qty"))
    result["produced_qty_after"] = flt(frappe.db.get_value("Work Order", work_order.name, "produced_qty"))
    return result


def _append_qty_correction_note(stock_entry, plan, reason=None):
    if plan.get("quantity_will_update"):
        note = "Manufacture quantity corrected by {0} on {1}: {2} -> {3}".format(
            frappe.session.user,
            frappe.utils.now(),
            plan["current_fg_completed_qty"],
            plan["new_fg_completed_qty"],
        )
    else:
        note = "Manufacture values balanced by {0} on {1}".format(
            frappe.session.user,
            frappe.utils.now(),
        )

    value_balance = plan.get("value_balance") or {}
    if value_balance.get("status") == "balanced":
        note += ". Value difference: {0} -> {1}".format(
            plan.get("value_difference_before"),
            plan.get("value_difference_after"),
        )
    if reason:
        note += ". Reason: {0}".format(reason)

    stock_entry.remarks = (stock_entry.remarks or "").strip()
    stock_entry.remarks = (stock_entry.remarks + "\n" if stock_entry.remarks else "") + note


def _add_qty_correction_comment(stock_entry, plan, reason=None, work_order_result=None):
    try:
        if plan.get("quantity_will_update"):
            content = _(
                "Manufacture quantity corrected from {0} to {1}. Stock and accounting ledgers were rebuilt."
            ).format(plan["current_fg_completed_qty"], plan["new_fg_completed_qty"])
        else:
            content = _("Manufacture values balanced. Stock and accounting ledgers were rebuilt.")

        value_balance = plan.get("value_balance") or {}
        if value_balance.get("status") == "balanced":
            content += " " + _("Value difference: {0} to {1}.").format(
                plan.get("value_difference_before"),
                plan.get("value_difference_after"),
            )
        if reason:
            content += " " + _("Reason: {0}").format(reason)

        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "Stock Entry",
            "reference_name": stock_entry.name,
            "content": content,
        }).insert(ignore_permissions=True)

        if stock_entry.work_order:
            work_order_content = content
            if work_order_result and work_order_result.get("qty_updated"):
                work_order_content += " " + _("Work Order quantity was also corrected.")

            frappe.get_doc({
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "Work Order",
                "reference_name": stock_entry.work_order,
                "content": work_order_content,
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Manufacture quantity correction comment failed")


def _get_manufacture_production_item(stock_entry):
    if stock_entry.work_order:
        return frappe.db.get_value("Work Order", stock_entry.work_order, "production_item")
    if stock_entry.bom_no:
        return frappe.db.get_value("BOM", stock_entry.bom_no, "item")
    return None


def _is_finished_good_row(stock_entry, row, production_item=None):
    production_item = production_item or _get_manufacture_production_item(stock_entry)
    if not row.t_warehouse:
        return False
    if production_item and row.item_code == production_item:
        return True
    return bool(stock_entry.bom_no and row.bom_no == stock_entry.bom_no and not _is_scrap_row(stock_entry, row))


def _is_scrap_row(stock_entry, row):
    if not stock_entry.bom_no or not row.t_warehouse:
        return False
    return bool(frappe.db.exists(
        "BOM Scrap Item",
        {"parent": stock_entry.bom_no, "item_code": row.item_code},
    ))


def _get_doc_precision(doc, fieldname, default=6):
    try:
        return doc.precision(fieldname)
    except Exception:
        return frappe.utils.cint(frappe.db.get_default("float_precision")) or default


def _stock_entry_has_serial_numbers(stock_entry):
    return any((_row_get(row, "serial_no") or "").strip() for row in (stock_entry.items or []))


def _get_stock_entry_serial_numbers(stock_entry):
    serial_numbers = []
    for row in stock_entry.items or []:
        serial_numbers.extend(_split_serial_numbers(_row_get(row, "serial_no")))
    return sorted(set(serial_numbers))


def _capture_serial_no_state(serial_numbers):
    if not serial_numbers:
        return {}

    serial_docs = frappe.get_all(
        "Serial No",
        filters={"name": ["in", serial_numbers]},
        fields=["name"] + list(SERIAL_NO_STATE_FIELDS),
        limit_page_length=0,
    )
    serial_state = {}
    for serial_doc in serial_docs:
        serial_state[_row_get(serial_doc, "name")] = {
            fieldname: _row_get(serial_doc, fieldname)
            for fieldname in SERIAL_NO_STATE_FIELDS
        }
    return serial_state


def _restore_serial_no_state(serial_state):
    for serial_no, values in (serial_state or {}).items():
        frappe.db.set_value("Serial No", serial_no, values, update_modified=False)


def _align_serial_no_warehouses_for_cancel(stock_entry):
    warehouse_by_serial = {}
    for row in stock_entry.items or []:
        target_warehouse = _row_get(row, "t_warehouse")
        if not target_warehouse:
            continue

        for serial_no in _split_serial_numbers(_row_get(row, "serial_no")):
            warehouse_by_serial[serial_no] = target_warehouse
            frappe.db.set_value(
                "Serial No",
                serial_no,
                "warehouse",
                target_warehouse,
                update_modified=False,
            )

    return warehouse_by_serial


def _build_bulk_repair_response(
    stock_entry_names,
    results,
    from_date,
    to_date,
    dry_run,
    cancel_original,
    include_results,
):
    summary = {}
    for result in results:
        status = result.get("status") or "unknown"
        summary[status] = summary.get(status, 0) + 1

    return {
        "from_date": from_date,
        "to_date": to_date,
        "dry_run": frappe.utils.cint(dry_run),
        "cancel_original": frappe.utils.cint(cancel_original),
        "stock_entry_count": len(stock_entry_names),
        "status_summary": summary,
        "results": results if frappe.utils.cint(include_results) else [],
    }


def _run_repair_handler(stock_entry_names, dry_run=True, cancel_original=True, repair_handler=None, error_title=None):
    if isinstance(stock_entry_names, str):
        stock_entry_names = frappe.parse_json(stock_entry_names)

    results = []
    dry_run = frappe.utils.cint(dry_run)
    cancel_original = frappe.utils.cint(cancel_original)

    for stock_entry_name in stock_entry_names or []:
        try:
            result = repair_handler(
                stock_entry_name,
                dry_run=dry_run,
                cancel_original=cancel_original,
            )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "{0} {1}".format(error_title or "repair_stock_entries", stock_entry_name),
            )
            result = {
                "stock_entry": stock_entry_name,
                "status": "error",
                "reason": frappe.get_traceback(),
            }
        results.append(result)

    return results


def _build_skipped_repair_result(stock_entry_name, reason):
    return {
        "stock_entry": stock_entry_name,
        "status": "skipped",
        "reason": reason,
    }


def _validate_repairable_manufacture_entry(original, stock_entry_name, require_serialized=None):
    if original.docstatus != 1:
        return _build_skipped_repair_result(
            stock_entry_name,
            "Only submitted stock entries can be repaired.",
        )

    if original.purpose != "Manufacture":
        return _build_skipped_repair_result(
            stock_entry_name,
            "Only Manufacture stock entries are supported.",
        )

    has_serial_numbers = _stock_entry_has_serial_numbers(original)

    if require_serialized is False and has_serial_numbers:
        return _build_skipped_repair_result(
            stock_entry_name,
            "Serialized manufacture entries must be repaired with repair_serialized_manufacture_stock_entries().",
        )

    if require_serialized is True and not has_serial_numbers:
        return _build_skipped_repair_result(
            stock_entry_name,
            "Only serialized Manufacture stock entries are supported.",
        )

    return None


def _prepare_repair_duplicate(original):
    duplicate = frappe.copy_doc(original)
    duplicate.naming_series = original.naming_series
    duplicate.posting_date = original.posting_date
    duplicate.posting_time = original.posting_time
    duplicate.set_posting_time = 1
    duplicate.handle_manufacture_batch_method = 1
    duplicate.assign_batch_method = 1
    duplicate.remarks = (original.remarks or "")
    duplicate.remarks = (
        (duplicate.remarks + "\n" if duplicate.remarks else "")
        + "Repair duplicate for {0}".format(original.name)
    )

    item_codes = sorted({row.item_code for row in duplicate.items if row.item_code})
    batch_map = {}
    if item_codes:
        batch_records = frappe.get_all(
            "Item",
            filters={"item_code": ["in", item_codes]},
            fields=["item_code", "has_batch_no"],
        )
        batch_map = {
            _row_get(row, "item_code"): _row_get(row, "has_batch_no")
            for row in batch_records
        }

    for row in duplicate.items:
        if row.t_warehouse and not row.batch_no and batch_map.get(row.item_code):
            row.auto_batch_no_generation = 1

    get_stock_and_rate_override(duplicate, method="repair")
    return duplicate


def _build_repair_result(stock_entry_name, original, duplicate, dry_run, repair_strategy):
    original_value_difference = flt(original.value_difference)
    repaired_value_difference = flt(duplicate.value_difference)
    value_difference_delta = flt(repaired_value_difference - original_value_difference)

    return {
        "stock_entry": stock_entry_name,
        "status": "dry_run" if dry_run else "ready",
        "repair_strategy": repair_strategy,
        "original_value_difference": original_value_difference,
        "repaired_value_difference": repaired_value_difference,
        "value_difference_delta": value_difference_delta,
        "duplicate_name": getattr(duplicate, "name", None),
    }


def _get_terminal_repair_result(result, dry_run=True, cancel_original=True):
    if abs(result["value_difference_delta"]) <= 0.01:
        result["status"] = "needs_review"
        result["reason"] = "Recalculation did not change value_difference."
        return result

    if abs(result["repaired_value_difference"]) > 0.01:
        result["status"] = "needs_review"
        result["reason"] = "Recalculation still leaves a non-zero value_difference."
        return result

    if not dry_run and not cancel_original:
        result["status"] = "needs_review"
        result["reason"] = "Live repair requires cancel_original=1 to keep Work Order quantities consistent."
        return result

    if dry_run:
        return result

    return None


def _prepare_live_repair_environment(duplicate, result):
    disabled_batches = _get_disabled_batch_numbers(duplicate.items)
    existing_allow_negative_stock = frappe.db.get_value("Stock Settings", None, "allow_negative_stock")

    if disabled_batches:
        result["reenabled_batches"] = disabled_batches
        _set_batch_disabled_state(disabled_batches, 0)

    frappe.db.sql("set innodb_lock_wait_timeout = 300")
    frappe.db.set_value("Stock Settings", None, "allow_negative_stock", 1, update_modified=False)
    return disabled_batches, existing_allow_negative_stock


def _restore_live_repair_environment(disabled_batches, existing_allow_negative_stock):
    if disabled_batches:
        _set_batch_disabled_state(disabled_batches, 1)

    frappe.db.set_value(
        "Stock Settings",
        None,
        "allow_negative_stock",
        existing_allow_negative_stock,
        update_modified=False,
    )


def _reset_duplicate_flags(duplicate):
    if getattr(duplicate, "flags", None) is not None:
        duplicate.flags.ignore_validate = False


def _submit_repair_duplicate(duplicate, bypass_work_order_update=True):
    # Insert without stock-entry validate so the copied source batches can be reused
    # inside the same repair transaction.
    duplicate.flags.ignore_validate = True
    duplicate.insert(ignore_permissions=True, ignore_links=True)
    duplicate.flags.ignore_validate = False
    duplicate.validate_bom = lambda: None
    duplicate.validate_work_order = lambda: None
    if bypass_work_order_update:
        duplicate.update_work_order = lambda: None
    duplicate.make_sl_entries = (
        lambda sl_entries, is_amended=None, allow_negative_stock=False, via_landed_cost_voucher=False:
            duplicate.__class__.make_sl_entries(
                duplicate,
                sl_entries,
                is_amended=is_amended,
                allow_negative_stock=True,
                via_landed_cost_voucher=via_landed_cost_voucher,
            )
    )
    duplicate.submit()


def _run_live_repair_duplicate_first(original, duplicate, result, cancel_original=True):
    disabled_batches, existing_allow_negative_stock = _prepare_live_repair_environment(duplicate, result)

    try:
        _submit_repair_duplicate(duplicate, bypass_work_order_update=True)
        result["duplicate_name"] = duplicate.name
        result["status"] = "duplicated"

        if cancel_original:
            original.cancel()
            result["status"] = "cancelled_original"

        _restore_live_repair_environment(disabled_batches, existing_allow_negative_stock)
        frappe.db.commit()
        return result
    except Exception:
        frappe.db.rollback()
        _reset_duplicate_flags(duplicate)
        _restore_live_repair_environment(disabled_batches, existing_allow_negative_stock)
        frappe.db.commit()
        raise


def _run_live_repair_cancel_first(original, duplicate, result):
    disabled_batches, existing_allow_negative_stock = _prepare_live_repair_environment(duplicate, result)
    serial_no_state = _capture_serial_no_state(_get_stock_entry_serial_numbers(original))

    try:
        aligned_serials = _align_serial_no_warehouses_for_cancel(original)
        if aligned_serials:
            result["temporarily_aligned_serial_count"] = len(aligned_serials)

        original.cancel()
        _submit_repair_duplicate(duplicate, bypass_work_order_update=False)
        _restore_serial_no_state(serial_no_state)
        result["duplicate_name"] = duplicate.name
        result["status"] = "cancelled_original"

        _restore_live_repair_environment(disabled_batches, existing_allow_negative_stock)
        frappe.db.commit()
        return result
    except Exception:
        frappe.db.rollback()
        _reset_duplicate_flags(duplicate)
        _restore_live_repair_environment(disabled_batches, existing_allow_negative_stock)
        frappe.db.commit()
        raise


def _repair_manufacture_stock_entry(stock_entry_name, dry_run=True, cancel_original=True):
    original = frappe.get_doc("Stock Entry", stock_entry_name)
    guardrail_result = _validate_repairable_manufacture_entry(
        original,
        stock_entry_name,
        require_serialized=False,
    )
    if guardrail_result:
        return guardrail_result

    duplicate = _prepare_repair_duplicate(original)
    result = _build_repair_result(
        stock_entry_name,
        original,
        duplicate,
        dry_run=dry_run,
        repair_strategy="duplicate_first",
    )
    terminal_result = _get_terminal_repair_result(
        result,
        dry_run=dry_run,
        cancel_original=cancel_original,
    )
    if terminal_result:
        return terminal_result

    return _run_live_repair_duplicate_first(
        original,
        duplicate,
        result,
        cancel_original=cancel_original,
    )


def _repair_serialized_manufacture_stock_entry(stock_entry_name, dry_run=True, cancel_original=True):
    original = frappe.get_doc("Stock Entry", stock_entry_name)
    guardrail_result = _validate_repairable_manufacture_entry(
        original,
        stock_entry_name,
        require_serialized=True,
    )
    if guardrail_result:
        return guardrail_result

    duplicate = _prepare_repair_duplicate(original)
    result = _build_repair_result(
        stock_entry_name,
        original,
        duplicate,
        dry_run=dry_run,
        repair_strategy="serialized_cancel_first",
    )
    terminal_result = _get_terminal_repair_result(
        result,
        dry_run=dry_run,
        cancel_original=cancel_original,
    )
    if terminal_result:
        return terminal_result

    return _run_live_repair_cancel_first(original, duplicate, result)

def set_basic_rate_override(doc, force=False, update_finished_item_rate=True, raise_error_if_no_rate=True, log_id=None):
    """
    Corrected version of ERPNext set_basic_rate()
    Fixes scrap valuation: scrap items no longer inherit FG rate,
    and always use BOM Scrap Item rate.
    """
    if not log_id:
        # creating a new log entry doc
        context = _dict(doctype="Stock Entry", name = f"set_basic_rate_override for  {doc.name}")
        log_id = _get_or_create_log(context)
    update_log_entry(
        log_id, f"[{now_datetime()}] set_basic_rate_override started for {doc.name}<br>")

    raw_material_cost = 0.0
    scrap_material_cost = 0.0
    fg_basic_rate = 0.0

    for d in doc.get("items"):

        # Detect scrap item from BOM Scrap table
        is_scrap = frappe.db.exists(
            "BOM Scrap Item",
            {"parent": doc.bom_no, "item_code": d.item_code}
        )# or d.t_warehouse in ["Scrap - AMF21","Rework - AMF21"] :

        # DO NOT propagate FG rate to scrap
        if d.t_warehouse and not is_scrap:
            fg_basic_rate = flt(d.basic_rate)

        args = doc.get_args_for_incoming_rate(d)

        # NORMAL MATERIALS (outgoing raw materials)
        if not d.bom_no and not is_scrap:
            if (not flt(d.basic_rate) and not d.allow_zero_valuation_rate) or d.s_warehouse or force:
                basic_rate = flt(get_incoming_rate(args, raise_error_if_no_rate),
                                 doc.precision("basic_rate", d))
                if basic_rate > 0:
                    d.basic_rate = basic_rate

            d.basic_amount = flt(flt(d.transfer_qty) * flt(d.basic_rate), d.precision("basic_amount"))
            update_log_entry(
                log_id, f"[{now_datetime()}] Item {d.item_code}: basic_rate set to {d.basic_rate}, basic_amount set to {d.basic_amount}<br>")
            if not d.t_warehouse:
                raw_material_cost += flt(d.basic_amount)

        # SCRAP ITEMS (patched)
        if is_scrap: 
            scrap_rate = flt(
                frappe.db.get_value(
                    "BOM Scrap Item",
                    {"parent": doc.bom_no, "item_code": d.item_code},
                    "rate",
                ) or 0,
                doc.precision("basic_rate", d),
            )
            if not scrap_rate:
                scrap_rate = flt(
                    get_incoming_rate(args, raise_error_if_no_rate),
                    doc.precision("basic_rate", d),
                )

            # d.allow_zero_valuation_rate = 1
            d.basic_rate = scrap_rate
            d.valuation_rate = scrap_rate
            
            d.basic_amount = flt(
                d.transfer_qty * scrap_rate,
                doc.precision("basic_amount", d),
            )
            update_log_entry(
                log_id, f"[{now_datetime()}] Scrap Item {d.item_code}: basic_rate set to {d.basic_rate}, basic_amount set to {d.basic_amount}<br>")   
            scrap_material_cost += d.basic_amount

    # FINISHED GOOD RATE CALCULATION
    number_of_fg_items = len([t.t_warehouse for t in doc.get("items") if t.t_warehouse])
    if (fg_basic_rate == 0.0 and number_of_fg_items == 1) or update_finished_item_rate:
        if doc.purpose in ["Manufacture", "Repack"]:
            for d in doc.get("items"):
                 # Detect scrap item from BOM Scrap table
                is_scrap = frappe.db.exists(
                    "BOM Scrap Item",
                    {"parent": doc.bom_no, "item_code": d.item_code}
                )
                
                if d.transfer_qty and (d.bom_no or d.t_warehouse) and not is_scrap:
                    d.basic_rate = flt((raw_material_cost - scrap_material_cost) / flt(d.transfer_qty), d.precision("basic_rate"))
                    d.basic_amount = flt((raw_material_cost - scrap_material_cost), d.precision("basic_amount"))
                    update_log_entry(
                        log_id, f"[{now_datetime()}] FG Item {d.item_code}: basic_rate set to {d.basic_rate}, basic_amount set to {d.basic_amount}<br>")
