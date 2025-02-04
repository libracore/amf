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
    1. Retrieve all BOMs (any docstatus).
    2. If docstatus=1, try to cancel it.
       - If cancel succeeds, proceed to copy and create a new BOM.
       - If it fails, log/skip the BOM.
    3. If docstatus!=1, skip (already canceled or draft).
    4. Copy the old BOM, preserving is_active/is_default.
       Remove all operations, set operating_cost = 0.
    5. Insert and submit the new BOM.
    """

    all_boms = frappe.get_all(
        "BOM",
        fields=["name", "is_active", "is_default", "docstatus"]
    )

    for bom_info in all_boms:
        # Only proceed if BOM is submitted (docstatus=1).
        if bom_info["docstatus"] != 1:
            continue

        old_bom_doc = frappe.get_doc("BOM", bom_info["name"])

        # Make a copy of the old BOM
        try:
            new_bom_doc = frappe.copy_doc(old_bom_doc)
        except ValidationError:
            # Log or print error (useful for debugging)
            frappe.log_error(
                title="Could not copy BOM",
                message=frappe.get_traceback()
            )
            continue    
        
        # Completely remove operations
        new_bom_doc.operations = []
        new_bom_doc.with_operations = 0
        if hasattr(new_bom_doc, "operating_cost"):
            new_bom_doc.operating_cost = 0.0

        # Additional Fields
        new_bom_doc.rm_cost_as_per = "Valuation Rate"
        
        # Preserve flags: is_active, is_default
        new_bom_doc.is_active = old_bom_doc.is_active
        if old_bom_doc.is_default:
            new_bom_doc.is_default = old_bom_doc.is_default

        # Insert and submit the new BOM
        try:
            new_bom_doc.insert()
            new_bom_doc.submit()
        except ValidationError:
            # Log or print error (useful for debugging)
            frappe.log_error(
                title="Could not insert BOM",
                message=frappe.get_traceback()
            )
            continue 
        print("New BOM copied:", new_bom_doc.name)
        frappe.db.commit()
        # Attempt to cancel the old BOM
        try:
            old_bom_doc.cancel()
            old_bom_doc.delete()
        except ValidationError:
            # Log or print error (useful for debugging)
            frappe.log_error(
                title="Could not cancel BOM",
                message=frappe.get_traceback()
            )
            continue
        
def delete_inactive_boms():
    all_boms = frappe.get_all(
        "BOM",
        fields=["name", "is_active", "is_default", "docstatus"],
        filters={'is_active': 0},
    )
    
    for bom_info in all_boms:
        bom_doc = frappe.get_doc("BOM", bom_info["name"])

        try:
            if bom_doc.docstatus != 2:
                bom_doc.cancel()
            bom_doc.delete()
        except ValidationError:
            # Log or print error (useful for debugging)
            frappe.log_error(
                title="Could not cancel BOM",
                message=frappe.get_traceback()
            )
            continue
        frappe.db.commit()
    return None