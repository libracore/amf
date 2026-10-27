"""Refresh configuration guidance and editable stock-consumption defaults."""


def execute():
    import frappe

    frappe.reload_doc("amf", "doctype", "item_creation", force=True)
    frappe.clear_cache(doctype="Item Creation")
