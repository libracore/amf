"""Expose product-only creation and read-only Product-code suggestions."""


def execute():
    import frappe

    for doctype in ("item_creation_variant", "item_creation"):
        frappe.reload_doc("amf", "doctype", doctype, force=True)
    frappe.clear_cache(doctype="Item Creation Variant")
    frappe.clear_cache(doctype="Item Creation")
