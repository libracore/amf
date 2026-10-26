"""Export active BOM relationships involving disabled Items without changing records."""

import csv

import frappe
from amf.amf.utils import data_artifact as artifacts


def write_disabled_dependency_audit(namespace, company):
    artifacts.validate_name(namespace + ".csv")
    saved = []
    producing = frappe.db.sql("""
        SELECT b.company, b.name AS bom, b.item AS finished_item,
            i.item_name AS finished_item_name, b.is_default,
            i.default_bom AS item_default_bom
        FROM `tabBOM` b JOIN `tabItem` i ON i.name = b.item
        WHERE b.company = %s AND b.docstatus = 1 AND b.is_active = 1
            AND i.disabled = 1
        ORDER BY b.name
    """, company, as_dict=True)
    consuming = frappe.db.sql("""
        SELECT b.company, b.name AS parent_bom, b.item AS parent_item,
            parent_item.disabled AS parent_item_disabled,
            parent_item.default_bom AS parent_default_bom,
            bi.name AS bom_item_row, bi.idx AS row_index,
            bi.item_code AS disabled_component, bi.bom_no AS linked_child_bom
        FROM `tabBOM Item` bi
        JOIN `tabBOM` b ON b.name = bi.parent
        JOIN `tabItem` parent_item ON parent_item.name = b.item
        JOIN `tabItem` child_item ON child_item.name = bi.item_code
        WHERE b.company = %s AND b.docstatus = 1 AND b.is_active = 1
            AND child_item.disabled = 1
        ORDER BY b.name, bi.idx
    """, company, as_dict=True)
    exports = (
        ("bom_cost_disabled_finished_boms_2026-10-09.csv", producing,
            ("company", "bom", "finished_item", "finished_item_name",
             "is_default", "item_default_bom")),
        ("bom_cost_disabled_component_rows_2026-10-09.csv", consuming,
            ("company", "parent_bom", "parent_item", "parent_item_disabled",
             "parent_default_bom",
             "bom_item_row", "row_index", "disabled_component",
             "linked_child_bom")),
        ("bom_cost_enabled_parent_disabled_components_2026-10-09.csv",
            [row for row in consuming if not row.parent_item_disabled],
            ("company", "parent_bom", "parent_item", "parent_item_disabled",
             "parent_default_bom",
             "bom_item_row", "row_index", "disabled_component",
             "linked_child_bom")),
        ("bom_cost_default_parent_disabled_components_2026-10-09.csv",
            [row for row in consuming if not row.parent_item_disabled
                and row.parent_bom == row.parent_default_bom],
            ("company", "parent_bom", "parent_item", "parent_item_disabled",
             "parent_default_bom",
             "bom_item_row", "row_index", "disabled_component",
             "linked_child_bom")),
    )
    for filename, rows, fields in exports:
        name = namespace + "_" + filename
        with artifacts.csv_output(name) as target:
            writer = csv.DictWriter(target, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        saved.append(name)
    return {"artifacts": saved, "active_boms_for_disabled_items": len(producing),
            "disabled_component_rows": len(consuming),
            "enabled_parent_rows_with_disabled_component": sum(
                not row.parent_item_disabled for row in consuming),
            "default_parent_rows_with_disabled_component": sum(
                not row.parent_item_disabled
                and row.parent_bom == row.parent_default_bom
                for row in consuming)}
