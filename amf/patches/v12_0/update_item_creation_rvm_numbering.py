"""Expose reviewed RVM numbering guidance without renaming existing Products."""


def execute():
    import frappe

    frappe.reload_doc("amf", "doctype", "item_creation", force=True)
    frappe.clear_cache(doctype="Item Creation")
