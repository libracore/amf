"""Add reviewed per-configuration Product Reference overrides; preserve masters."""


def execute():
    import frappe

    frappe.reload_doc("amf", "doctype", "item_creation_variant", force=True)
    frappe.clear_cache(doctype="Item Creation Variant")
    frappe.clear_cache(doctype="Item Creation")
