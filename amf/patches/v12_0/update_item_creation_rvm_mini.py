"""Expose RVM mini in Item Creation guidance without changing catalogue records."""


def execute():
    import frappe

    frappe.reload_doc("amf", "doctype", "item_creation", force=True)
    frappe.clear_cache(doctype="Item Creation")
