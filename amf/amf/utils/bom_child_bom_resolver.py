# amf/amf/utils/set_child_default_boms.py
import frappe

def apply_item_default_boms_to_rows(doc, method=None):
    """
    For each child item in BOM Items, set row.bom_no = Item.default_bom.
    Optionally verifies those BOMs are submitted & active.
    """

    # ---- knobs you can tweak ----
    ONLY_IF_EMPTY = False     # False = override whatever is there; True = only fill blanks
    VERIFY_STATUS = True      # True = ensure default_bom is submitted & active
    STRICT = False            # True = throw if some items lack a valid default BOM
    # -----------------------------

    if not getattr(doc, "items", None):
        return

    # Collect relevant rows (ignore parent self-reference)
    rows = [r for r in doc.items if r.item_code and r.item_code != doc.item]
    if not rows:
        return

    # Bulk fetch default_bom from Item
    item_codes = sorted({r.item_code for r in rows})
    items = frappe.get_all(
        "Item",
        filters={"name": ["in", item_codes]},
        fields=["name", "default_bom"]
    )
    default_map = {d["name"]: d["default_bom"] for d in items}

    # Optionally validate that default_bom(s) are submitted & active and match the same item
    valid_bom_map = {}
    if VERIFY_STATUS:
        # Collect BOM names to check
        bom_names = sorted({b for b in default_map.values() if b})
        if bom_names:
            bom_rows = frappe.get_all(
                "BOM",
                filters={"name": ["in", bom_names]},
                fields=["name", "item", "is_active", "docstatus"]
            )
            valid_bom_map = {
                b["name"]: (b["item"], int(b["is_active"]) == 1, int(b["docstatus"]) == 1)
                for b in bom_rows
            }

    changed, missing, invalid, status = [], [], [], []

    for r in rows:
        default_bom = default_map.get(r.item_code)

        # Fill/override policy
        if ONLY_IF_EMPTY and r.bom_no:
            continue

        if not default_bom:
            missing.append((r.idx, r.item_code))
            r.bom_no = None
            continue

        if VERIFY_STATUS:
            item_of_bom, is_active, is_submitted = valid_bom_map.get(default_bom, (None, False, False))
            # Must belong to the same item, be submitted & active
            if item_of_bom != r.item_code or not (is_active and is_submitted):
                invalid.append((r.idx, r.item_code, default_bom))
                # Do not assign an invalid default
                r.bom_no = None
                continue

        if r.bom_no != default_bom:
            r.bom_no = default_bom
            changed.append((r.idx, r.item_code, default_bom))
            status.append("<b>Default BOM modified</b>: " + (f"{r.item_code} w/ {r.bom_no}"))
    if status:
        frappe.msgprint("<br>".join(status), title="Child BOM Assignment Notices", indicator="green")
    # Stash a summary for downstream hooks or debugging
    doc.flags.set_child_default_boms_summary = {
        "changed_count": len(changed),
        "missing_default_bom_count": len(missing),
        "invalid_default_bom_count": len(invalid),
        "changed_sample": changed[:20],
        "missing_sample": missing[:20],
        "invalid_sample": invalid[:20],
    }

    # Gentle heads-up to the user
    # if missing or invalid:
    if invalid:
        lines = []
        # if missing:
            # lines.append("<b>Missing default BOM on Item</b>: " + ", ".join(f"Row {i} [{it}]" for i, it in missing))
        if invalid:
            lines.append("<b>Default BOM not submitted/active or mismatched</b>: " +
                         ", ".join(f"Row {i} [{it}] → {bn}" for i, it, bn in invalid))
        frappe.msgprint("<br>".join(lines), title="Child BOM assignment notices", indicator="orange")

    if STRICT and (missing or invalid):
        frappe.throw("Some child items have no valid default BOM. Please fix them before saving.")
