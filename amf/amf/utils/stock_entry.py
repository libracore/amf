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
    if not doc.update_rate_items_method:
        update_log_entry(log_id, f"[{now_datetime()}] Before Save: update rate flag not set<br>")
    else:
        _update_rates(doc, log_id)
        update_log_entry(log_id, f"[{now_datetime()}] Before Save: rates set for {doc.name}<br>")
    
    if doc.update_quantity_items_method or doc.update_rate_items_method:
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
      2) Manufacture batch
      3) Batch assignment
    """
    log_id = _get_or_create_log(doc)
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
    log = frappe.get_doc({
        "doctype": "Log Entry",
        "timestamp": datetime.datetime.now(),
        "category": category,
        "message": message,
        "reference_name": name,
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    return log.name


def update_log_entry(log_id, message):
    """
    Append a message to an existing Log Entry.
    """
    log = custom_try(frappe.get_doc, "Log Entry", log_id)
    if not log:
        return
    log.message = (log.message or "") + "\n" + (message or "")
    custom_try(log.save, ignore_permissions=True)


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
    print("Entering get_stock_and_rate_override.")
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
        )

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
            scrap_rate = flt(get_incoming_rate(args, raise_error_if_no_rate), ...)

            if not scrap_rate:
                scrap_rate = frappe.db.get_value("BOM Scrap Item", {...}, "rate") or 0

            # d.allow_zero_valuation_rate = 1
            d.basic_rate = scrap_rate
            d.valuation_rate = scrap_rate
            
            d.basic_amount = flt(d.transfer_qty * scrap_rate, ...)
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



