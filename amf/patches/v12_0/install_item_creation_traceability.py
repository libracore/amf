"""Add execution links and the request-only cancellation/amendment workflow."""


def execute():
    import frappe
    from amf.amf.utils.item_creation_workflow import sync_item_creation_schema
    from amf.amf.utils.item_creation_traceability import backfill_result_links

    sync_item_creation_schema()
    frappe.reload_doc("amf", "report", "item_creation_results", force=True)
    backfill_result_links()
    frappe.clear_cache()
