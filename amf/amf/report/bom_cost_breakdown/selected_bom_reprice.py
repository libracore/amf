"""Plan material repricing only for selected finished Items and made children.

The selected roots come from the reviewed one-column Item-code file. A child
BOM is in scope only when the approved costing route makes that component;
a qualifying Purchase Receipt makes it a purchased leaf instead.
"""

import csv
import io
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal

import frappe

from . import material_reprice
from amf.amf.utils import data_artifact as artifacts


REFS_NAME = artifacts.SELECTED_REFS
REVIEWED_PROPOSAL_NAME = artifacts.SELECTED_PROPOSAL


def selected_refs(name=REFS_NAME):
    with io.StringIO(artifacts.get_bytes(name).decode("utf-8-sig"), newline="") as source:
        rows = list(csv.reader(source))
    if any(len(row) != 1 or not row[0].strip() for row in rows):
        raise ValueError("Selected Item file must have one Item code per row")
    refs = [row[0].strip() for row in rows]
    if len(refs) != 61 or len(set(refs)) != len(refs):
        raise ValueError("Expected exactly 61 distinct selected Item codes")
    if any("+" in ref for ref in refs):
        raise ValueError("Selected Item code still appears in spreadsheet scientific notation")
    return refs


def scoped_plan(refs=None):
    """Return child-before-parent proposal entries for the selected route."""
    refs = selected_refs() if refs is None else list(refs)
    if len(refs) != 61 or len(set(refs)) != len(refs):
        raise ValueError("Expected exactly 61 distinct selected Item codes")
    full = material_reprice.build_plan()
    by_item = {entry["finished_item"]: entry for entry in full}
    by_bom = {entry["bom"]: entry for entry in full}
    missing = sorted(set(refs) - set(by_item))
    if missing:
        raise ValueError("Selected Items without a valid enabled current default BOM: {}".format(missing))
    scope = set()

    def visit(bom_name, active=()):
        if bom_name in active:
            raise ValueError("Made-child BOM cycle: {}".format(active + (bom_name,)))
        if bom_name in scope:
            return
        entry = by_bom.get(bom_name)
        if not entry:
            raise ValueError("Made child has no valid current default BOM: {}".format(bom_name))
        for row in entry["rows"]:
            if row.get("method") == "child_default_raw_material_less_stored_scrap_per_finished_unit":
                child = row.get("linked_bom")
                if not child or row.get("source") != child:
                    raise ValueError("Made-child source and link disagree: {}".format(row["row"]))
                visit(child, active + (bom_name,))
        scope.add(bom_name)

    for ref in refs:
        visit(by_item[ref]["bom"])
    entries = [entry for entry in full if entry["bom"] in scope]
    if len(entries) != len(scope):
        raise ValueError("Scoped BOM plan is incomplete")
    return refs, entries


def _payload(refs, entries, outside):
    return {"selected_finished_items": refs, "boms": entries,
            "outside_current_parents": outside}


def _payload_bytes(refs, entries, outside):
    return (json.dumps(material_reprice.serial(_payload(refs, entries, outside)),
                       sort_keys=True, indent=2) + "\n").encode("utf-8")


def _outside_current_parents(entries):
    """Report other default BOMs whose current production links use changed children."""
    changed_children = [entry["bom"] for entry in entries if entry["status"] == "ready_changed"]
    if not changed_children:
        return []
    placeholders = ",".join(["%s"] * len(changed_children))
    current = frappe.db.sql("""
        SELECT parent.name AS parent_bom,parent.item AS parent_item,
            child.name AS bom_item_row,child.item_code AS component_item,
            child.bom_no AS changed_child_bom
        FROM `tabBOM Item` child
        JOIN tabBOM parent ON parent.name=child.parent
        JOIN tabItem item ON item.default_bom=parent.name
        WHERE child.bom_no IN ({}) AND item.disabled=0
            AND parent.item=item.name AND parent.docstatus=1 AND parent.is_active=1
        ORDER BY parent.item,parent.name,child.idx
    """.format(placeholders), tuple(changed_children), as_dict=True)
    scoped_names = {entry["bom"] for entry in entries}
    return [row for row in current if row.parent_bom not in scoped_names]


def write_scoped_proposal(output_prefix=None):
    """Save a database preview without changing BOMs. Use a new name for each review."""
    refs, entries = scoped_plan()
    prefix = output_prefix or artifacts.new_name("bom-selected-proposal", "json")[:-5]
    artifacts.validate_name(prefix + ".json")
    outside = _outside_current_parents(entries)
    payload = _payload_bytes(refs, entries, outside)
    proposal_path = artifacts.put(prefix + ".json", payload)
    summary_path = prefix + ".csv"
    with artifacts.csv_output(summary_path) as target:
        fields = ("bom", "finished_item", "selected_root", "status", "reasons",
                  "old_raw_material_cost", "new_raw_material_cost", "old_total_cost", "new_total_cost")
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow({field: (int(entry["finished_item"] in refs) if field == "selected_root" else
                                    "; ".join(entry["reasons"]) if field == "reasons" else
                                    entry.get(field)) for field in fields})
    outside_path = prefix + "_outside_parents.csv"
    with artifacts.csv_output(outside_path) as target:
        fields = ("parent_item", "parent_bom", "bom_item_row", "component_item", "changed_child_bom")
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(outside)
    statuses = Counter(entry["status"] for entry in entries)
    roots = {entry["finished_item"] for entry in entries if entry["finished_item"] in refs}
    if roots != set(refs):
        raise ValueError("Not every selected root is present in the scoped plan")
    return {"selected_roots": len(refs), "reachable_boms": len(entries),
            "reachable_children": len(entries) - len(refs), "statuses": dict(statuses),
            "changed_selected_roots": sum(entry["status"] == "ready_changed"
                                          for entry in entries if entry["finished_item"] in refs),
            "changed_child_boms": sum(entry["status"] == "ready_changed"
                                       for entry in entries if entry["finished_item"] not in refs),
            "outside_parent_rows_using_changed_children": len(outside),
            "outside_parent_boms_using_changed_children": len({row.parent_bom for row in outside}),
            "proposal_sha256": hashlib.sha256(payload).hexdigest(),
            "proposal_json": str(proposal_path), "summary_csv": str(summary_path),
            "outside_parents_csv": str(outside_path)}


def apply_scoped_proposal(proposal_name=REVIEWED_PROPOSAL_NAME, commit=True):
    """Apply only a fresh reviewed proposal; let patch runner commit if requested."""
    saved = artifacts.get_bytes(proposal_name)
    refs, entries = scoped_plan()
    if _payload_bytes(refs, entries, _outside_current_parents(entries)) != saved:
        raise ValueError("Selected BOM proposal differs from current Items, BOMs, or receipts; regenerate")
    if any(entry["status"] == "blocked" for entry in entries):
        raise ValueError("Selected BOM route contains an unavailable material branch")
    if frappe.db.get_single_value("Manufacturing Settings", "update_bom_costs_automatically"):
        raise ValueError("ERPNext automatic BOM cost refresh is not paused")
    if not frappe.conf.get("pause_amf_cost_writers"):
        raise ValueError("AMF automatic BOM cost writers are not paused")
    changed = [entry for entry in entries if entry["status"] == "ready_changed"]
    try:
        for entry in changed:
            material_reprice._apply_entry(entry)
        material_reprice._verify_applied(changed)
        _verify_updated_explosions(entries)
        if commit:
            frappe.db.commit()
    except Exception:
        if commit:
            frappe.db.rollback()
        raise
    return {"updated_boms": len(changed),
            "updated_selected_roots": sum(entry["finished_item"] in refs for entry in changed),
            "updated_child_boms": sum(entry["finished_item"] not in refs for entry in changed),
            "cleared_child_links": sum(bool(row.get("clear_child_link"))
                                       for entry in changed for row in entry["rows"])}


def _verify_updated_explosions(entries):
    """Compare rebuilt flat BOM quantities with current made-child links."""
    by_bom = {entry["bom"]: entry for entry in entries}
    changed = [entry for entry in entries if entry["status"] == "ready_changed"]
    if not changed:
        return 0
    names = tuple(by_bom)
    placeholders = ",".join(["%s"] * len(names))
    actual_rows = frappe.db.sql("""
        SELECT parent,item_code,stock_qty,bom_no FROM `tabBOM Item`
        WHERE parent IN ({}) ORDER BY parent,idx
    """.format(placeholders), names, as_dict=True)
    rows_by_bom = defaultdict(list)
    for row in actual_rows:
        rows_by_bom[row.parent].append(row)
    memo = {}

    def flatten(bom_name, active=()):
        if bom_name in memo:
            return memo[bom_name]
        if bom_name in active:
            raise ValueError("Cycle in updated production links: {}".format(bom_name))
        result = defaultdict(Decimal)
        for row in rows_by_bom[bom_name]:
            if row.bom_no:
                child = by_bom.get(row.bom_no)
                if not child:
                    raise ValueError("Updated BOM links outside selected route: {}".format(row.bom_no))
                factor = material_reprice.dec(row.stock_qty) / material_reprice.dec(child["quantity"])
                for item, qty in flatten(row.bom_no, active + (bom_name,)).items():
                    result[item] += qty * factor
            else:
                result[row.item_code] += material_reprice.dec(row.stock_qty)
        memo[bom_name] = result
        return result

    changed_names = tuple(entry["bom"] for entry in changed)
    placeholders = ",".join(["%s"] * len(changed_names))
    exploded = defaultdict(dict)
    for row in frappe.db.sql("""
        SELECT parent,item_code,SUM(stock_qty) AS stock_qty
        FROM `tabBOM Explosion Item` WHERE parent IN ({})
        GROUP BY parent,item_code
    """.format(placeholders), changed_names, as_dict=True):
        exploded[row.parent][row.item_code] = material_reprice.dec(row.stock_qty)
    for entry in changed:
        expected = flatten(entry["bom"])
        stored = exploded[entry["bom"]]
        for item in set(expected) | set(stored):
            if abs(expected.get(item, Decimal(0)) - stored.get(item, Decimal(0))) > Decimal("0.001"):
                raise ValueError("Updated explosion quantity differs: {} {}".format(entry["bom"], item))
    return len(changed)


def preflight_scoped_proposal(proposal_name=REVIEWED_PROPOSAL_NAME):
    """Exercise every selected write and flat BOM rebuild, then roll back."""
    refs, entries = scoped_plan()
    if _payload_bytes(refs, entries, _outside_current_parents(entries)) != artifacts.get_bytes(proposal_name):
        raise ValueError("Selected BOM proposal changed; regenerate before preflight")
    changed = [entry for entry in entries if entry["status"] == "ready_changed"]
    try:
        for entry in changed:
            material_reprice._apply_entry(entry)
        material_reprice._verify_applied(changed)
        verified_explosions = _verify_updated_explosions(entries)
        return {"tested_boms": len(changed), "tested_explosions": verified_explosions,
                "representative_458040_new_total_chf": str(next(entry["new_total_cost"]
                    for entry in changed if entry["finished_item"] == "458040"))}
    finally:
        frappe.db.rollback()
