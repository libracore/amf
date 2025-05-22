import frappe
from frappe import _, _dict
from frappe import ValidationError
from frappe.utils import flt, now_datetime, add_days

from amf.amf.utils.stock_entry import (
    _get_or_create_log,
    update_log_entry,
    custom_try
)

# Constants
DEFAULT_WAREHOUSE = "Main Stock - AMF21"
LOG_CATEGORY = "BOM Sync"

@frappe.whitelist()
def execute_db_update_enqueue():
    frappe.enqueue("amf.amf.utils.bom_mgt.refactor_boms", queue='long', timeout=15000)
    return None

def execute_db_update():
    # 1. Remove BOM Operation rows for all BOMs, or filter as needed
    frappe.db.sql("""
        DELETE FROM `tabBOM Operation`
        WHERE parent IN (SELECT name FROM `tabBOM`)
    """)

    # 2. Reset operating cost field (if it's just a numeric or currency field in the BOM)
    frappe.db.sql("""
        UPDATE `tabBOM`
        SET operating_cost = 0
    """)
    
    # 2. Reset operating cost field (if it's just a numeric or currency field in the BOM)
    frappe.db.sql("""
        UPDATE `tabBOM`
        SET with_operations = 0
    """)

    # 3. Commit the changes
    frappe.db.commit()
    
def refactor_boms():
    """
    Refactor all submitted BOMs by:
      1. Copying each submitted BOM (docstatus=1).
      2. Removing operations and setting operating_cost=0 (if present).
      3. Submitting the new BOM.
      4. Canceling and deleting the old BOM.

    Uses savepoints so that each BOM is processed in its own transaction scope.
    """
    # Retrieve all BOMs, regardless of docstatus
    all_boms = frappe.get_all(
        "BOM",
        fields=["name", "is_active", "is_default", "docstatus"]
    )

    for bom_info in all_boms:
        # Only proceed if BOM is in a Submitted state
        if bom_info["docstatus"] != 1:
            continue

        # Start a transaction savepoint for each BOM
        #frappe.db.savepoint("before_bom_refactor")

        try:
            old_bom_doc = frappe.get_doc("BOM", bom_info["name"])

            # -------------------------
            # 1. Copy the old BOM
            # -------------------------
            new_bom_doc = frappe.copy_doc(old_bom_doc)

            # -------------------------
            # 2. Adjust New BOM
            # -------------------------
            # Remove all operations
            new_bom_doc.operations = []
            new_bom_doc.with_operations = 0

            # Zero-out operating cost if field exists
            if hasattr(new_bom_doc, "operating_cost"):
                new_bom_doc.operating_cost = 0.0

            # Example: Set raw-material cost valuation method
            new_bom_doc.rm_cost_as_per = "Valuation Rate"

            # Preserve is_active/is_default
            new_bom_doc.is_active = old_bom_doc.is_active
            if old_bom_doc.is_default:
                new_bom_doc.is_default = old_bom_doc.is_default

            # -------------------------
            # 3. Insert & Submit New BOM
            # -------------------------
            new_bom_doc.insert()
            new_bom_doc.submit()

            # -------------------------
            # 4. Cancel and Delete Old BOM
            # -------------------------
            # Only do this after the new BOM is safely submitted.
            old_bom_doc.cancel()
            old_bom_doc.delete()

            # If all steps succeed, commit this transaction
            frappe.db.commit()

            # Optional: Print or log success info
            print(f"Successfully copied BOM {old_bom_doc.name} to {new_bom_doc.name}")

        except ValidationError:
            # If any step failed, roll back to the savepoint
            #frappe.db.rollback(save_point="before_bom_refactor")
            frappe.log_error(
                title="BOM Refactor Error",
                message=frappe.get_traceback()
            )
            # Move to the next BOM
            continue
    
    # Last Checkpoint: Delete Inactive BOMs
    delete_inactive_boms()
    return None
        
def delete_inactive_boms():
    """
    Delete all inactive BOMs (is_active=0).
    If a BOM is not already canceled, cancel it before deleting.
    """
    inactive_boms = frappe.get_all(
        "BOM",
        fields=["name", "is_active", "is_default", "docstatus"],
        filters={'is_active': 0},
    )

    for bom_info in inactive_boms:
        # Start a transaction savepoint for each BOM
        #frappe.db.savepoint("before_bom_delete")

        try:
            bom_doc = frappe.get_doc("BOM", bom_info["name"])

            # Cancel if not already canceled
            if bom_doc.docstatus != 2:
                bom_doc.cancel()

            # Now delete the BOM
            bom_doc.delete()

            frappe.db.commit()

        except ValidationError:
            #frappe.db.rollback(save_point="before_bom_delete")
            frappe.log_error(
                title="Could Not Delete Inactive BOM",
                message=frappe.get_traceback()
            )
            continue

    return None

"""
##################################################################
CLEAN AUTO ITEM DOCTYPE. UPDATE DEFAULT_BOM, BOM TABLE, BOM COSTS.
##################################################################
"""
@frappe.whitelist()
def execute_db_enqueue():
    """
    This can be called manually to enqueue the full update of all items.
    """
    frappe.enqueue("amf.amf.utils.bom_mgt.execute_all_items", queue='long', timeout=15000)
    return

def execute_all_items():
    """
    Run the full update for every enabled Item, clearing BOM fields
    and then pulling data from the default BOM.
    """
    items = frappe.get_all("Item", filters={"disabled": 0}, fields=["name"])
    for item_data in items:
        item_name = item_data["name"]
        update_item_from_default_bom_old(item_name)

@frappe.whitelist()
def execute_scheduled_old():
    """
    This is called by the daily scheduler event to update only Items
    whose default BOMs have changed in the last 24 hours.
    """
    # 1) Get the cutoff date/time (24h ago).
    cutoff = add_days(now_datetime(), -1)
    # 2) Identify default BOMs that were modified after the cutoff.
    #    You might adjust the timeframe or add further logic if needed.
    #    docstatus=1 => only submitted BOMs
    active_boms_modified = frappe.get_all(
        "BOM",
        filters={
            "is_active": 1,
            "docstatus": 1,
            "modified": [">=", cutoff],
        },
        fields=["name", "item"]
    )

    # 3) For each such BOM, update its associated Item if not disabled
    for row in active_boms_modified:
        bom_name = row["name"]
        item_name = row["item"]

        # Skip if Item is disabled
        if frappe.db.get_value("Item", item_name, "disabled") == 1:
            continue

        update_item_from_default_bom_old(item_name)


def update_item_from_default_bom_old(item_name):
    """
    Core logic:
      1. Clears the item_default_bom, bom_table, and bom_cost fields.
      2. Fetches the default BOM for the given Item (if any).
      3. Copies BOM details and cost back into the Item.
      4. Saves the Item.
    """

    # Fetch the Item doc
    try:
        item_doc = frappe.get_doc("Item", item_name)
    except frappe.DoesNotExistError:
        frappe.log_error(
            title="Item Not Found",
            message=f"Unable to find Item {item_name}"
        )
        return

    # Clear fields
    item_doc.item_default_bom = None
    item_doc.bom_table = []
    item_doc.bom_cost = 0.0  # or None, if your field type allows

    # Find the default BOM for this item
    # (Make sure docstatus=1 and is_default=1 in your BOM if that’s your definition of “default BOM”.)
    bom_name = frappe.db.get_value(
        "BOM",
        {
            "item": item_name,
            "is_default": 1,
            "docstatus": 1
        },
        "name"
    )
    if not bom_name:
        # No default BOM => just save cleared fields
        try:
            item_doc.save()
            frappe.db.commit()
        except frappe.ValidationError as e:
            frappe.log_error(
                title="Item Not Saved",
                message=f"Unable to save Item {item_name}: {e}"
            )
        return

    # Load the BOM document
    try:
        bom_doc = frappe.get_doc("BOM", bom_name)
    except frappe.DoesNotExistError:
        frappe.log_error(
            title="BOM Not Found",
            message=f"Unable to find BOM {bom_name} for Item {item_name}"
        )
        try:
            item_doc.save()
            frappe.db.commit()
        except frappe.ValidationError as e:
            frappe.log_error(
                title="Item Not Saved",
                message=f"Unable to save Item {item_name}: {e}"
            )
        return

    # Assign default BOM link
    item_doc.item_default_bom = bom_doc.name

    # For each BOM item, copy relevant fields to the item’s bom_table
    for bom_item in bom_doc.items:
        if frappe.db.get_value("Item", bom_item.item_code, "disabled"):  
                # Option A: Skip adding this disabled item
                # Could also log something, e.g.:
                print(f"Skipping disabled item '{bom_item.item_code}' in BOM '{bom_doc.name}'")
                continue
        # Example: fetch the Bin qty in a specific warehouse
        bin_qty = frappe.db.get_value(
            "Bin",
            {"item_code": bom_item.item_code, "warehouse": "Main Stock - AMF21"},
            "actual_qty"
        ) or 0
        bom_default = frappe.db.get_value(
            "BOM",
            {"item": bom_item.item_code, "is_default": 1},
            "name"
        ) or ""

        child_row = item_doc.append("bom_table", {})
        child_row.item_code       = bom_item.item_code
        child_row.item_name       = bom_item.item_name
        child_row.source_warehouse= "Main Stock - AMF21"
        child_row.qty             = bom_item.qty
        child_row.uom             = bom_item.uom
        child_row.description     = bom_item.description
        child_row.rate            = bom_item.rate
        child_row.stock_qty       = bin_qty
        child_row.bom_no          = bom_default
        # ... copy any other fields relevant for your process ...

    # Set the cost
    item_doc.bom_cost = flt(bom_doc.total_cost) or ""

    # Save
    try:
        item_doc.save()
        frappe.db.commit()
    except frappe.ValidationError as e:
        frappe.log_error(
            title="BOM Not Saved",
            message=f"Unable to save BOM {bom_name} for Item {item_name}: {e}"
        )
        return
    
@frappe.whitelist()
def execute_db_update_enqueue():
    frappe.enqueue("amf.amf.utils.bom_mgt.duplicate_default_bom_for_47xxxx_items", queue='long', timeout=15000)
    return None

def duplicate_default_bom_for_47xxxx_items():
    """
    1) Finds all items with item_code matching the pattern ^47\\d{4}$ (6 digits total).
    2) Gets the default BOM for each item, if any.
    3) Duplicates that BOM, adds two references C100 and C101 with qty=1 each.
    4) Submits the newly created BOM.
    """

    # Step 1: Get all item codes that match regex ^47\d{4}$ (i.e. 47 + 4 digits = 6 total digits).
    items = frappe.get_all(
        "Item",
        filters={
            "item_code": ["like", "47%"],
            "disabled": 0
        },
        fields=["name"]
    )

    for item_code in items:
        # Step 2: Get the default BOM for this item
        default_bom = frappe.db.get_value(
            "BOM",
            {
                "item": item_code['name'],
                "is_default": 1,
                "docstatus": 1
            },
            "name"
        )
        if not default_bom:
            continue  # Skip if there's no default BOM set

        # Retrieve the existing BOM document
        old_bom = frappe.get_doc("BOM", default_bom)
        
        # Step 4: Add the two new references as BOM Items
        # Gather item codes that already exist in the old BOM
        existing_item_codes = [row.item_code for row in old_bom.items]
        # If *both* C100 AND C101 are already present, skip this item
        if "C100" in existing_item_codes and "C101" in existing_item_codes:
            continue

        # Step 3: Duplicate the BOM using frappe.copy_doc
        new_bom = frappe.copy_doc(old_bom)

        # Clear out fields that should not be carried over
        new_bom.name = None
        new_bom.amended_from = None
        # We want a clean, draft (docstatus=0) copy
        new_bom.docstatus = 0  
        new_bom.is_default = 1
        
        # Only add C100 if not already in the old BOM
        if "C100" not in existing_item_codes:
            new_bom.append("items", {
                "item_code": "C100",
                "qty": 1
            })

        # Only add C101 if not already in the old BOM
        if "C101" not in existing_item_codes:
            new_bom.append("items", {
                "item_code": "C101",
                "qty": 1
            })
        
        for item_row in new_bom.items:
            default_bom = frappe.db.get_value(
                "BOM",
                {
                    "item": item_row.item_code,
                    "is_default": 1,
                    "docstatus": 1
                },
                "name"
            )
            if default_bom:
                item_row.bom_no = default_bom

        # Step 5: Insert and Submit
        new_bom.insert()
        new_bom.submit()

    frappe.db.commit()  # Ensure changes are committed to the database


@frappe.whitelist()
def execute_scheduled():
    """
    Daily scheduler: update Items whose default BOM changed in the last 24h.
    """
    # 1) Initialize log
    context = _dict(doctype="BOM", name="Scheduled BOM Update")
    log_id = _get_or_create_log(context)  # assume doc context not needed here
    update_log_entry(log_id, f"[{now_datetime()}] Starting execute_scheduled")

    # 2) Compute cutoff
    cutoff = add_days(now_datetime(), -1)
    update_log_entry(log_id, f"[{now_datetime()}] Cutoff timestamp: {cutoff}")

    # 3) Fetch active, submitted BOMs modified since cutoff
    boms = frappe.get_all(
        "BOM",
        filters={
            "is_active": 1,
            "docstatus": 1,
            "modified": [">=", cutoff],
        },
        fields=["name", "item"],
    )
    count = len(boms)
    update_log_entry(log_id, f"[{now_datetime()}] Found {count} modified BOM(s) since cutoff")

    if not boms:
        update_log_entry(log_id, f"[{now_datetime()}] No BOMs to process. Exiting.")
        return

    # 4) Preload disabled Items
    items = list({r["item"] for r in boms})
    disabled_map = frappe.get_all(
        "Item",
        filters={"name": ["in", items]},
        fields=["name", "disabled"],
        as_list=False,
    )
    disabled_items = {row.name for row in disabled_map if row.disabled}

    # 5) Process each BOM → Item
    for idx, row in enumerate(boms, start=1):
        bom_name = row["name"]
        item_name = row["item"]
        update_log_entry(log_id, f"[{now_datetime()}] [{idx}/{count}] BOM: {bom_name}, Item: {item_name}")

        if item_name in disabled_items:
            update_log_entry(log_id, f"[{now_datetime()}] Skipping disabled Item: {item_name}")
            continue

        # Delegate to updater
        _update_item_from_default_bom(item_name, bom_name, log_id)

    update_log_entry(log_id, f"[{now_datetime()}] execute_scheduled complete\n")
    frappe.db.commit()


def _update_item_from_default_bom(item_name, triggered_bom, log_id):
    """
    Applies default BOM to the Item record.
    Accepts the name of the BOM that triggered the update
    so it can be logged (even if not actually the default).
    """
    ts = now_datetime()
    update_log_entry(log_id, f"[{now_datetime()}] {ts} → Processing Item '{item_name}' (triggered by BOM '{triggered_bom}')")

    # 1. Load Item
    item = custom_try(frappe.get_doc, "Item", item_name)
    if not item:
        update_log_entry(log_id, f"[{now_datetime()}] ❌ Item '{item_name}' not found, skipping.")
        return

    # 2. Clear old BOM fields
    item.set("item_default_bom", None)
    item.set("bom_table", [])
    item.set("bom_cost", 0.0)
    update_log_entry(log_id, f"[{now_datetime()}] Cleared item_default_bom, bom_table & bom_cost")

    # 3. Find true default BOM
    default_bom = frappe.db.get_value(
        "BOM",
        {"item": item_name, "is_default": 1, "docstatus": 1},
        "name"
    )
    if not default_bom:
        update_log_entry(log_id, f"[{now_datetime()}] No default BOM for Item '{item_name}'. Saving cleared state.")
        _safe_save(item, item_name, log_id, "Item cleared")
        return

    update_log_entry(log_id, f"[{now_datetime()}] Default BOM identified: '{default_bom}'")

    # 4. Load BOM document
    bom = custom_try(frappe.get_doc, "BOM", default_bom)
    if not bom:
        update_log_entry(log_id, f"[{now_datetime()}] ❌ Default BOM '{default_bom}' not found. Saving cleared Item.")
        _safe_save(item, item_name, log_id, "Item after missing BOM")
        return

    # 5. Assign and copy table
    item.item_default_bom = bom.name
    update_log_entry(log_id, f"[{now_datetime()}] Linked Item to BOM '{bom.name}'")

    # Preload bin quantities for all codes in one go
    codes = [d.item_code for d in bom.items]
    bins = frappe.get_all(
        "Bin",
        filters={"item_code": ["in", codes], "warehouse": DEFAULT_WAREHOUSE},
        fields=["item_code", "actual_qty"],
        as_list=False,
    )
    bin_map = {b.item_code: flt(b.actual_qty) for b in bins}

    for bi in bom.items:
        code = bi.item_code
        if frappe.db.get_value("Item", code, "disabled"):
            update_log_entry(log_id, f"[{now_datetime()}] Skipping disabled BOM line item '{code}'")
            continue

        row = item.append("bom_table", {})
        row.update({
            "item_code": code,
            "item_name": bi.item_name,
            "source_warehouse": DEFAULT_WAREHOUSE,
            "qty": bi.qty,
            "uom": bi.uom,
            "description": bi.description,
            "rate": flt(bi.rate),
            "stock_qty": bin_map.get(code, 0.0),
            "bom_no": frappe.db.get_value(
                "BOM", {"item": code, "is_default": 1}, "name"
            ) or ""
        })
        update_log_entry(log_id, f"[{now_datetime()}] → Added line for '{code}': qty={bi.qty}, stock={row.stock_qty}")

    # 6. Set cost and save
    item.bom_cost = flt(bom.total_cost) or 0.0
    update_log_entry(log_id, f"[{now_datetime()}] Set bom_cost to {item.bom_cost}")

    _safe_save(item, item_name, log_id, f"Item updated with BOM '{bom.name}'")


def _safe_save(doc, name, log_id, context):
    """
    Attempt to save + commit a doc; on error, log and rollback.
    """
    try:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        update_log_entry(log_id, f"[{now_datetime()}] ✔ {context} for '{name}' saved successfully")
    except Exception as e:
        frappe.log_error(message=str(e), title=f"Error saving {doc.doctype} '{name}'")
        frappe.db.rollback()
        update_log_entry(log_id, f"[{now_datetime()}] ❌ Failed saving '{name}': {e}")