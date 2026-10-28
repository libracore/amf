"""Add optional Product codes and selectable seat pins to Item Creation."""


def execute():
    import frappe

    for doctype in ("item_creation_variant", "item_creation"):
        frappe.reload_doc("amf", "doctype", doctype, force=True)
    # Preserve the formerly fixed pin choice in existing drafts. Submitted
    # requests keep their original inputs, approval snapshots and results.
    if frappe.db.exists("Item", "SPL.3039"):
        frappe.db.sql("""UPDATE `tabItem Creation` SET seat_pin_item = 'SPL.3039'
            WHERE docstatus = 0 AND seat_check = 'Yes'
            AND COALESCE(seat_pin_item, '') = ''""")
    # The plan format changed. Retain approval history and require fresh review.
    frappe.db.sql("""UPDATE `tabItem Creation` SET review_status = 'Stale',
        approved_plan_hash = NULL, approved_input_hash = NULL,
        reviewed_by = NULL, reviewed_at = NULL
        WHERE docstatus = 0 AND COALESCE(approved_plan_hash, '') != ''""")
    frappe.clear_cache(doctype="Item Creation Variant")
    frappe.clear_cache(doctype="Item Creation")
