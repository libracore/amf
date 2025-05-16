import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


def batch_to_stock_entry(doc, method=None):
    print("Entering batch_to_stock_entry...")
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

def stock_entry_onload(doc, method):
    """Set every row to auto-batch generation on load."""
    for row in doc.items:
        row.auto_batch_no_generation = 1


def stock_entry_validate(doc, method):
    """
    - Default expense account & cost center on every save/submit.
    - Default warehouses based on work_order → production_item logic.
    """
    _set_expense_and_cost_center(doc)
    _set_warehouse_defaults(doc)


def stock_entry_before_submit(doc, method):
    """
    1) Handle manufacture-batch creation if purpose is Manufacture.
    2) Then for _every_ row, create or assign a batch if needed.
    """
    _handle_manufacture_batch_creation(doc)
    for row in doc.items:
        _handle_batch_for_row(doc, row)


# ——— Helpers ————————————————

def _set_expense_and_cost_center(doc):
    for row in doc.items:
        row.expense_account = "4900 - Stock variation - AMF21"
        if doc.purpose in ("Manufacture", "Material Transfer for Manufacture"):
            row.cost_center = "Automation - AMF21"


def _set_warehouse_defaults(doc):
    if not doc.work_order:
        return

    production_item = frappe.db.get_value("Work Order", doc.work_order, "production_item") or ""
    # skip if blank or starts with 10/20
    if not production_item or production_item.startswith(("10", "20")):
        return

    TRANSFER_WH = "Work In Progress - AMF21"
    MANUFACTURE_WH = "Main Stock - AMF21"

    if doc.purpose == "Manufacture":
        doc.from_warehouse, doc.to_warehouse = MANUFACTURE_WH, TRANSFER_WH
        source, target = TRANSFER_WH, MANUFACTURE_WH
    elif doc.purpose == "Material Transfer for Manufacture":
        doc.from_warehouse, doc.to_warehouse = TRANSFER_WH, MANUFACTURE_WH
        source, target = MANUFACTURE_WH, TRANSFER_WH
    else:
        return

    for row in doc.items:
        if not row.manual_source_warehouse_selection:
            row.s_warehouse = source
        if not row.manual_target_warehouse_selection:
            row.t_warehouse = target


def _handle_batch_for_row(doc, row):
    # 1) skip if no item_code, already has batch, or batch-not-required
    if not row.item_code or row.batch_no:
        return

    has_batch = frappe.db.get_value("Item", row.item_code, "has_batch_no") or 0
    if has_batch != 1 or row.auto_batch_no_generation != 1:
        return

    # 2) build unique batch id
    timestamp = frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S")
    batch_id = f"{timestamp} {row.item_code} AMF"

    # 3) create or reuse
    if not frappe.db.exists("Batch", batch_id):
        batch = frappe.get_doc({
            "doctype": "Batch",
            "item": row.item_code,
            "batch_id": batch_id,
        }).insert(ignore_permissions=True)
        row.batch_no = batch.name
    else:
        frappe.msgprint(
            _("Batch {0} already exists, attaching existing").format(batch_id),
            indicator="orange"
        )
        row.batch_no = batch_id


def _handle_manufacture_batch_creation(doc):
    if doc.purpose != "Manufacture" or not doc.work_order or not doc.items:
        return

    wo = frappe.get_doc("Work Order", doc.work_order)
    prod_item = wo.production_item or ""
    spare_batch = wo.spare_batch_no if wo.spare_part_production else None

    # find the row matching production_item
    target = next((r for r in doc.items if r.item_code == prod_item), None)
    if not target:
        return

    # if spare-part prod, override
    if spare_batch:
        target.auto_batch_no_generation = 0
        target.batch_no = spare_batch
        return

    # else generate new batch as usual
    _handle_batch_for_row(doc, target)

def update_rate_and_availability_ste(doc, method): 
    # Call the get_stock_and_rate method
    doc.get_stock_and_rate()
    # Cache BOM rates by item_code to minimize database hits
    bom_rate_cache = {}

    for row in doc.items:
        item_code = row.item_code

        # Use cached rate if already fetched
        if item_code in bom_rate_cache:
            rate = bom_rate_cache[item_code]
        else:
            # Retrieve default-active BOM for this item
            bom_name = frappe.db.get_value(
                "BOM",
                {"item": item_code, "is_active": 1, "is_default": 1},
                "name"
            )

            if not bom_name:
                print(f"No default-active BOM for item: {item_code}, skipping rate update.")
                bom_rate_cache[item_code] = None
                rate = None
            else:
                # Fetch the item-level rate from the BOM Item child table
                rate = frappe.db.get_value(
                    "BOM",
                    {"name": bom_name, "item": item_code},
                    "total_cost"
                )
                if rate is None:
                    frappe.throw(
                        _(f"Rate not defined for item {item_code} in BOM {bom_name}")
                    )
                bom_rate_cache[item_code] = rate

        # Apply rate if available
        if rate is not None:
            row.basic_rate = rate
    return
