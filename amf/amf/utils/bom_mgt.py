import frappe
from frappe import _
from frappe import ValidationError
from frappe.utils import flt, now_datetime, add_days

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
        update_item_from_default_bom(item_name)

@frappe.whitelist()
def execute_scheduled():
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

        update_item_from_default_bom(item_name)


def update_item_from_default_bom(item_name):
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
    print("Set up", bom_doc.name, "for item:", item_name)
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
        print("*db commit done*")
    except frappe.ValidationError as e:
        frappe.log_error(
            title="BOM Not Saved",
            message=f"Unable to save BOM {bom_name} for Item {item_name}: {e}"
        )
        return