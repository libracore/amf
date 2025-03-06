import frappe
from frappe.utils import flt

def update_bin_draft_qtys_with_warehouse():
    """
    For each Bin (item_code + warehouse), do the following:
      1) Sum all draft Sales Order qty for (item_code, warehouse)
         => write to Bin.ordered_draft_qty
      2) Sum all draft Work Order qty for (item_code, fg_warehouse)
         => write to Bin.planned_draft_qty
    """

    # -------------------------------------------------------------------------
    # 1) SUM draft Sales Order qty per (item_code, warehouse)
    #    docstatus = 0 => Sales Order not yet submitted
    #    Summation = SUM(soi.qty - soi.delivered_qty)
    # -------------------------------------------------------------------------
    so_draft_qtys = frappe.db.sql(
        """
        SELECT
            soi.item_code AS item_code,
            soi.warehouse AS warehouse,
            SUM(soi.qty - soi.delivered_qty) AS total_qty
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 0
        GROUP BY soi.item_code, soi.warehouse
        """,
        as_dict=True
    )

    # Convert to map: { (item_code, warehouse): total_draft_so_qty }
    so_draft_map = {}
    for row in so_draft_qtys:
        key = (row.item_code, row.warehouse)
        so_draft_map[key] = flt(row.total_qty)

    # -------------------------------------------------------------------------
    # 2) SUM draft Work Order qty per (production_item, fg_warehouse)
    #    docstatus = 0 => Work Order not yet submitted
    #    Summation = SUM(qty - produced_qty)
    # -------------------------------------------------------------------------
    wo_draft_qtys = frappe.db.sql(
        """
        SELECT
            production_item AS item_code,
            fg_warehouse AS warehouse,
            SUM(qty - produced_qty) AS total_qty
        FROM `tabWork Order`
        WHERE docstatus = 0
        GROUP BY production_item, fg_warehouse
        """,
        as_dict=True
    )

    # Convert to map: { (item_code, warehouse): total_draft_wo_qty }
    wo_draft_map = {}
    for row in wo_draft_qtys:
        key = (row.item_code, row.warehouse)
        wo_draft_map[key] = flt(row.total_qty)

    # -------------------------------------------------------------------------
    # 3) For each Bin record, update its ordered_draft_qty + planned_draft_qty
    #    matching on (bin.item_code, bin.warehouse).
    # -------------------------------------------------------------------------
    bins = frappe.get_all(
        "Bin",
        fields=["name", "item_code", "warehouse"]
    )

    for b in bins:
        item_code = b.item_code
        warehouse = b.warehouse
        bin_name = b.name

        # Fetch the sums from the two maps (default to 0 if missing)
        ordered_qty = so_draft_map.get((item_code, warehouse), 0)
        planned_qty = wo_draft_map.get((item_code, warehouse), 0)

        # Update the Bin doc
        try:
            bin_doc = frappe.get_doc("Bin", bin_name)
            bin_doc.ordered_draft_qty = ordered_qty
            bin_doc.planned_draft_qty = planned_qty
            bin_doc.projected_draft_qty = planned_qty - ordered_qty
            bin_doc.save()
        except Exception:
            frappe.log_error(
                title="Failed to update Bin draft quantities",
                message=frappe.get_traceback()
            )

    # Optionally commit after updating all bins
    frappe.db.commit()
