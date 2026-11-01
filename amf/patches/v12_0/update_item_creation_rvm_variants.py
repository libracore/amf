"""Expose RVM body/interface guidance without creating historical interface BOMs."""


def execute():
    import frappe

    frappe.reload_doc("amf", "doctype", "item_creation", force=True)
    frappe.clear_cache(doctype="Item Creation")
