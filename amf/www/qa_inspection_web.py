import frappe
from frappe import _

def _ensure_logged_in():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please log in to access this resource."), frappe.PermissionError)

def _child_list(doc, fieldname):
    """Return child table rows as plain dicts including 'name' and 'idx'."""
    return [row.as_dict() for row in doc.get(fieldname) or []]

@frappe.whitelist()
def get_quality_inspection_by_dn(delivery_note):
    """
    Resolve the Global Quality Inspection linked to a Delivery Note and
    return the parent with all relevant child tables for rendering.
    """
    _ensure_logged_in()

    if not delivery_note:
        frappe.throw(_("Missing Delivery Note parameter."))

    delivery_note = get_normalized_dn_name(delivery_note)

    name = frappe.db.get_value(
        "Global Quality Inspection",
        {"reference_name": delivery_note},
        "name"
    )
    if not name:
        return None

    doc = frappe.get_doc("Global Quality Inspection", name)

    return {
        "name": doc.name,
        "customer_name": doc.get("customer_name"),
        "reference_name": doc.get("reference_name"),
        "readings": _child_list(doc, "readings"),
        "items": _child_list(doc, "items"),
        "item_specific": _child_list(doc, "item_specific"),
        "client_specific": _child_list(doc, "client_specific"),
    }

@frappe.whitelist(allow_guest=False)
def submit_quality_results(docname, data, global_status=None, verified_by=None):
    """
    Met à jour les sous-tables (readings, items, item_specific, client_specific)
    et le status global du document Global Quality Inspection.
    """
    import json
    
    if not docname:
        frappe.throw(_("Missing document name."))

    data = json.loads(data)
    doc = frappe.get_doc("Global Quality Inspection", docname)

    # update child tables
    for table_name, rows in data.items():
        if not hasattr(doc, table_name):
            continue
        for row_data in rows:
            for child in getattr(doc, table_name):
                if child.name == row_data["name"]:
                    child.status = row_data.get("status")
                    child.comment = row_data.get("comment", "")
                    break

    # update global status
    
    doc.status = global_status
    doc.verified_by = verified_by

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return f"Inspection '{docname}' saved successfully with status {global_status}."




def get_normalized_dn_name(delivery_note):
    """
    Normalize a Delivery Note identifier to the standard format.

    Args:
        delivery_note (str): The delivery note identifier. 
            Accepted formats include:
                - Numeric only (e.g., "456")
                - Prefixed with "DN-" or "DN" (e.g., "DN-456", "DN456")
                - Lowercase or mixed case (e.g., "dn_01376")
                - With suffixes (e.g., "1473-1")
            Invalid formats include non-numeric prefixes (e.g., "OF-1376").

    Returns:
        str: Normalized delivery note in the format "DN-XXXXX" or "DN-XXXXX-<suffix>" 
            where "XXXXX" is a zero-padded 5-digit number.

    Raises:
        frappe.ValidationError: If the input format is invalid or cannot be normalized.

    Normalization logic:
        - Converts input to uppercase.
        - Replaces underscores with hyphens.
        - Extracts the main numeric part and any suffix.
        - Pads the numeric part to 5 digits.
        - Throws an error for invalid formats.
    """
    import re
    # Normalize to uppercase, replace underscores with hyphens and trim whitespace
    delivery_note = delivery_note.upper().replace("_", "-").strip()

    # Match optional "DN" prefix (with or without hyphen), capture main number and optional suffix (-<digits>)
    match = re.match(r"^(?:DN-?)?(\d+)(?:-(\d+))?$", delivery_note)
    if not match:
        frappe.throw(_("Invalid Delivery Note format."))

    main_number = int(match.group(1))
    suffix = match.group(2)

    if suffix:
        normalized_dn = f"DN-{main_number:05d}-{suffix}"
    else:
        normalized_dn = f"DN-{main_number:05d}"

    print(normalized_dn)
    return normalized_dn