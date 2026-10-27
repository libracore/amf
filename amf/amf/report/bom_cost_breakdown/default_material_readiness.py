"""Read-only material issue screen for enabled Items' current default BOMs."""

import csv
from collections import Counter

import frappe
from amf.amf.utils import data_artifact as artifacts


def write_default_material_readiness(output_path):
    headers = {r.name: r for r in frappe.db.sql("""
        SELECT b.name, b.item, b.company, b.currency
        FROM `tabItem` i JOIN `tabBOM` b ON b.name = i.default_bom
        WHERE i.disabled = 0 AND b.item = i.name
            AND b.docstatus = 1 AND b.is_active = 1
    """, as_dict=True)}
    rows = frappe.db.sql("""
        SELECT b.name AS bom, b.item AS finished_item,
            bi.name AS bom_item_row, bi.idx AS row_index,
            bi.item_code AS component_item, bi.bom_no AS linked_bom,
            bi.stock_uom AS bom_stock_uom, bi.stock_qty,
            bi.base_amount AS stored_base_amount,
            ci.name AS existing_component, ci.disabled AS component_disabled,
            ci.stock_uom AS item_stock_uom,
            cb.item AS linked_item, cb.docstatus AS linked_docstatus,
            cb.is_active AS linked_active, cb.company AS linked_company,
            cb.currency AS linked_currency
        FROM `tabItem` pi
        JOIN `tabBOM` b ON b.name = pi.default_bom
        JOIN `tabBOM Item` bi ON bi.parent = b.name
        LEFT JOIN `tabItem` ci ON ci.name = bi.item_code
        LEFT JOIN `tabBOM` cb ON cb.name = bi.bom_no
        WHERE pi.disabled = 0 AND b.item = pi.name
            AND b.docstatus = 1 AND b.is_active = 1
        ORDER BY b.name, bi.idx
    """, as_dict=True)
    findings = []
    counts = Counter()

    def add(kind, row):
        findings.append({
            "issue_type": kind,
            "bom": row.bom,
            "finished_item": row.finished_item,
            "bom_item_row": row.bom_item_row,
            "row_index": row.row_index,
            "component_item": row.component_item,
            "linked_bom": row.linked_bom,
            "stock_qty": row.stock_qty,
            "bom_stock_uom": row.bom_stock_uom,
            "item_stock_uom": row.item_stock_uom,
            "stored_base_amount": row.stored_base_amount,
        })
        counts[kind] += 1

    for row in rows:
        if row.existing_component is None:
            add("missing_component_item", row)
        if row.component_disabled:
            add("disabled_component", row)
        if row.item_stock_uom and row.bom_stock_uom != row.item_stock_uom:
            add("stock_uom_mismatch", row)
        if row.stock_qty is not None and row.stock_qty < 0:
            add("negative_material_quantity", row)
        if (row.stock_qty is not None and row.stock_qty > 0
                and (row.stored_base_amount is None
                     or row.stored_base_amount <= 0)):
            add("positive_quantity_nonpositive_amount", row)
        if row.linked_bom:
            parent = headers[row.bom]
            if row.linked_item is None:
                add("missing_linked_bom", row)
            elif row.linked_docstatus != 1 or not row.linked_active:
                add("inactive_or_unsubmitted_linked_bom", row)
            elif row.linked_item != row.component_item:
                add("wrong_item_linked_bom", row)
            elif (row.linked_company != parent.company
                    or row.linked_currency != parent.currency):
                add("company_or_currency_mismatch_linked_bom", row)

    path = artifacts.validate_name(output_path)
    fields = ("issue_type", "bom", "finished_item", "bom_item_row",
              "row_index", "component_item", "linked_bom", "stock_qty",
              "bom_stock_uom", "item_stock_uom", "stored_base_amount")
    with artifacts.csv_output(path) as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(findings)
    return {"enabled_valid_default_boms": len(headers),
            "default_bom_item_rows": len(rows),
            "finding_rows": len(findings), "counts": dict(counts)}


def write_purchase_flag_candidates(output_path, company):
    """List enabled child-BOM Items with receipt evidence but purchase flag off."""
    candidates = frappe.db.sql("""
        SELECT DISTINCT ci.name AS item_code, ci.item_name, ci.disabled,
            ci.is_purchase_item, ci.default_bom
        FROM `tabItem` parent_item
        JOIN `tabBOM` parent_bom
            ON parent_bom.name = parent_item.default_bom
        JOIN `tabBOM Item` bi ON bi.parent = parent_bom.name
        JOIN `tabItem` ci ON ci.name = bi.item_code
        JOIN `tabBOM` child_bom ON child_bom.name = ci.default_bom
        WHERE parent_item.disabled = 0 AND parent_bom.docstatus = 1
            AND parent_bom.is_active = 1
            AND parent_bom.item = parent_item.name
            AND parent_bom.company = %s AND bi.stock_qty > 0
            AND ci.disabled = 0 AND ci.is_purchase_item = 0
            AND child_bom.item = ci.name AND child_bom.docstatus = 1
            AND child_bom.is_active = 1
            AND EXISTS (
                SELECT 1 FROM `tabPurchase Receipt Item` pri
                JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
                WHERE pri.item_code = ci.name AND pr.company = %s
                    AND pr.docstatus = 1 AND IFNULL(pr.is_return, 0) = 0
                    AND IFNULL(pri.is_free_item, 0) = 0
                    AND pri.stock_qty > 0 AND pri.base_net_amount > 0
            )
        ORDER BY ci.name
    """, (company, company), as_dict=True)
    for row in candidates:
        receipt = frappe.db.sql("""
            SELECT pr.name, pr.posting_date, pr.posting_time
            FROM `tabPurchase Receipt Item` pri
            JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE pri.item_code = %s AND pr.company = %s
                AND pr.docstatus = 1 AND IFNULL(pr.is_return, 0) = 0
                AND IFNULL(pri.is_free_item, 0) = 0
                AND pri.stock_qty > 0 AND pri.base_net_amount > 0
            ORDER BY pr.posting_date DESC, pr.posting_time DESC,
                pr.creation DESC, pr.name DESC
            LIMIT 1
        """, (row.item_code, company), as_dict=True)[0]
        row.latest_qualifying_receipt = receipt.name
        row.receipt_posting_date = receipt.posting_date
        row.receipt_posting_time = receipt.posting_time
    path = artifacts.validate_name(output_path)
    fields = ("item_code", "item_name", "disabled", "is_purchase_item",
              "default_bom", "latest_qualifying_receipt",
              "receipt_posting_date", "receipt_posting_time")
    with artifacts.csv_output(path) as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(candidates)
    return {"candidate_count": len(candidates), "output_path": str(path)}
