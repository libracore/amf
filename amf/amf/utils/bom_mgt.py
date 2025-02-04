import frappe
from frappe import _
from frappe import ValidationError

@frappe.whitelist()
def execute_db_update_enqueue():
    frappe.enqueue("amf.amf.utils.bom_mgt.refactor_boms", queue='long', timeout=15000)
    frappe.enqueue("amf.amf.utils.bom_mgt.delete_inactive_boms", queue='long', timeout=15000)
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
        frappe.db.savepoint("before_bom_refactor")

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
            frappe.db.rollback(save_point="before_bom_refactor")
            frappe.log_error(
                title="BOM Refactor Error",
                message=frappe.get_traceback()
            )
            # Move to the next BOM
            continue
        
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
        frappe.db.savepoint("before_bom_delete")

        try:
            bom_doc = frappe.get_doc("BOM", bom_info["name"])

            # Cancel if not already canceled
            if bom_doc.docstatus != 2:
                bom_doc.cancel()

            # Now delete the BOM
            bom_doc.delete()

            frappe.db.commit()

        except ValidationError:
            frappe.db.rollback(save_point="before_bom_delete")
            frappe.log_error(
                title="Could Not Delete Inactive BOM",
                message=frappe.get_traceback()
            )
            continue

    return None