"""Audit direct and recursive BOM Item changes for selected finished Items."""

import csv
from collections import Counter, defaultdict
from decimal import Decimal

import frappe
from amf.amf.utils import data_artifact as artifacts
from .selected_bom_reprice import selected_refs




def amount(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.000001"))


def export_changed_items():
    run_id = artifacts.new_name("bom-selected-audit")[:-4]
    refs = selected_refs()
    proposal = {entry["finished_item"]: entry
                for entry in artifacts.get_json(artifacts.MATERIAL_SNAPSHOT)}
    if any(ref not in proposal or proposal[ref]["status"] != "ready_changed" for ref in refs):
        raise ValueError("Selected ref is absent or was not repriced in the original proposal")
    placeholders = ",".join(["%s"]*len(refs))
    current = frappe.db.sql("""
        SELECT i.name AS finished_item,b.name AS bom,b.total_cost,
            bi.name AS material_row,bi.item_code,bi.rate,bi.base_rate,
            bi.amount,bi.base_amount,bi.bom_no
        FROM tabItem i JOIN tabBOM b ON b.name=i.default_bom
        JOIN `tabBOM Item` bi ON bi.parent=b.name
        WHERE i.name IN ({}) AND i.disabled=0 AND b.item=i.name
            AND b.docstatus=1 AND b.is_active=1
    """.format(placeholders),tuple(refs),as_dict=True)
    current_by_ref = defaultdict(dict)
    for row in current:
        current_by_ref[row.finished_item][row.material_row] = row
    if len(current_by_ref) != len(refs):
        raise ValueError("One or more selected current default BOMs are missing")
    detailed = []
    per_component = defaultdict(lambda:{"boms":set(),"rows":0,"receipt":0,"child":0,"cleared_links":0})
    per_bom = Counter()
    for ref in refs:
        entry = proposal[ref]
        live_rows = current_by_ref[ref]
        if len(live_rows) != len(entry["rows"]):
            raise ValueError("Current BOM Item count differs: {}".format(ref))
        for source_row in entry["rows"]:
            live = live_rows.get(source_row["row"])
            if not live or live.bom != entry["bom"] or live.item_code != source_row["item"]:
                raise ValueError("Current BOM material relationship differs: {}".format(source_row["row"]))
            if amount(live.total_cost) != amount(entry["old_total_cost"]):
                raise ValueError("Selected BOM is no longer at rolled-back cost: {}".format(ref))
            for field in ("rate","base_rate","amount","base_amount"):
                if amount(live[field]) != amount(source_row["old_" + field]):
                    raise ValueError("Selected material row no longer matches rollback: {} {}".format(
                        source_row["row"],field))
            if live.bom_no != source_row["linked_bom"]:
                raise ValueError("Selected material link no longer matches rollback: {}".format(
                    source_row["row"]))
            if "new_amount" not in source_row:
                continue
            changed = (amount(source_row["old_amount"]) != amount(source_row["new_amount"])
                or amount(source_row["old_rate"]) != amount(source_row["new_rate"])
                or bool(source_row.get("clear_child_link")))
            if not changed:
                continue
            item = source_row["item"]
            method = source_row.get("method","")
            detail = {
                "finished_item_ref":ref,"bom":entry["bom"],
                "bom_item_row":source_row["row"],"row_index":source_row["idx"],
                "component_item":item,"qty":source_row["qty"],
                "stock_qty":source_row["stock_qty"],
                "old_rate_chf":amount(source_row["old_rate"]),
                "proposed_rate_chf":amount(source_row["new_rate"]),
                "old_amount_chf":amount(source_row["old_amount"]),
                "proposed_amount_chf":amount(source_row["new_amount"]),
                "proposed_minus_old_chf":amount(Decimal(source_row["new_amount"])
                    - Decimal(source_row["old_amount"])),
                "current_amount_chf":amount(live.amount),
                "old_child_bom":source_row["linked_bom"] or "",
                "proposed_child_bom":"" if source_row.get("clear_child_link")
                    else (source_row["linked_bom"] or ""),
                "source_record":source_row.get("source", ""),
                "calculation_method":method,
                "receipt_posted":source_row.get("receipt_posted", ""),
                "receipt_stock_qty":source_row.get("receipt_stock_qty", ""),
                "receipt_base_net_amount_chf":source_row.get("receipt_base_net_amount", ""),
            }
            detailed.append(detail)
            summary = per_component[item]
            summary["boms"].add(ref)
            summary["rows"] += 1
            summary["receipt"] += method.startswith("latest_receipt")
            summary["child"] += method.startswith("child_default")
            summary["cleared_links"] += bool(source_row.get("clear_child_link"))
            per_bom[ref] += 1
    detail_path = run_id + "_bom_selected_61_changed_component_rows_2026-10-12.csv"
    detail_fields = ("finished_item_ref","bom","bom_item_row","row_index",
        "component_item","qty","stock_qty","old_rate_chf","proposed_rate_chf",
        "old_amount_chf","proposed_amount_chf","proposed_minus_old_chf",
        "current_amount_chf","old_child_bom","proposed_child_bom",
        "source_record","calculation_method","receipt_posted","receipt_stock_qty",
        "receipt_base_net_amount_chf")
    with artifacts.csv_output(detail_path) as target:
        writer = csv.DictWriter(target,fieldnames=detail_fields)
        writer.writeheader()
        writer.writerows(detailed)
    summary_path = run_id + "_bom_selected_61_changed_component_summary_2026-10-12.csv"
    summary_fields = ("component_item","affected_finished_boms","changed_rows",
        "latest_receipt_rows","recursive_child_bom_rows","child_links_cleared")
    with artifacts.csv_output(summary_path) as target:
        writer = csv.DictWriter(target,fieldnames=summary_fields)
        writer.writeheader()
        for item in sorted(per_component):
            stats = per_component[item]
            writer.writerow({"component_item":item,
                "affected_finished_boms":len(stats["boms"]),
                "changed_rows":stats["rows"],
                "latest_receipt_rows":stats["receipt"],
                "recursive_child_bom_rows":stats["child"],
                "child_links_cleared":stats["cleared_links"]})
    # Follow the proposed made-child route through every level. A receipt-backed
    # child with a cleared link is a purchased leaf in this view.
    by_bom = {entry["bom"]:entry for entry in proposal.values()}
    recursive = []

    def walk(root_ref,bom_name,path,level,root_multiplier,active):
        if bom_name in active:
            raise ValueError("BOM cycle under {}: {}".format(root_ref,bom_name))
        bom = by_bom[bom_name]
        for row in bom["rows"]:
            next_path = path + (row["item"],)
            if "new_amount" in row and (amount(row["old_amount"]) != amount(row["new_amount"])
                    or amount(row["old_rate"]) != amount(row["new_rate"])
                    or row.get("clear_child_link")):
                recursive.append({
                    "root_item_ref":root_ref,"level":level,
                    "item_path":" > ".join(next_path),"bom":bom_name,
                    "bom_item_row":row["row"],"component_item":row["item"],
                    "root_multiplier":str(root_multiplier),"qty_in_own_bom":row["qty"],
                    "old_amount_in_own_bom_chf":amount(row["old_amount"]),
                    "proposed_amount_in_own_bom_chf":amount(row["new_amount"]),
                    "old_child_bom":row["linked_bom"] or "",
                    "proposed_child_bom":"" if row.get("clear_child_link")
                        else (row["linked_bom"] or ""),
                    "source_record":row.get("source", ""),
                    "calculation_method":row.get("method", ""),
                })
            child_name = row["linked_bom"] if not row.get("clear_child_link") else None
            if child_name:
                child = by_bom.get(child_name)
                if not child or Decimal(child["quantity"]) <= 0:
                    raise ValueError("Unusable proposed child under {}: {}".format(root_ref,child_name))
                child_multiplier = root_multiplier * Decimal(row["stock_qty"]) / Decimal(child["quantity"])
                walk(root_ref,child_name,next_path,level + 1,child_multiplier,active + (bom_name,))

    for ref in refs:
        walk(ref,proposal[ref]["bom"],(ref,),0,Decimal("1"),())
    recursive_path = run_id + "_bom_selected_61_recursive_changed_component_paths_2026-10-12.csv"
    recursive_fields = ("root_item_ref","level","item_path","bom","bom_item_row",
        "component_item","root_multiplier","qty_in_own_bom",
        "old_amount_in_own_bom_chf","proposed_amount_in_own_bom_chf",
        "old_child_bom","proposed_child_bom","source_record","calculation_method")
    with artifacts.csv_output(recursive_path) as target:
        writer = csv.DictWriter(target,fieldnames=recursive_fields)
        writer.writeheader()
        writer.writerows(recursive)
    recursive_by_component = defaultdict(lambda:{"roots":set(),"paths":0,"min_level":None,
        "example_path":""})
    for row in recursive:
        stats = recursive_by_component[row["component_item"]]
        stats["roots"].add(row["root_item_ref"])
        stats["paths"] += 1
        if stats["min_level"] is None or row["level"] < stats["min_level"]:
            stats["min_level"] = row["level"]
            stats["example_path"] = row["item_path"]
    recursive_summary_path = run_id + "_bom_selected_61_recursive_changed_component_summary_2026-10-12.csv"
    with artifacts.csv_output(recursive_summary_path) as target:
        writer = csv.DictWriter(target,fieldnames=("component_item","affected_finished_boms",
            "changed_path_occurrences","shallowest_level","example_path"))
        writer.writeheader()
        for item in sorted(recursive_by_component):
            stats = recursive_by_component[item]
            writer.writerow({"component_item":item,"affected_finished_boms":len(stats["roots"]),
                "changed_path_occurrences":stats["paths"],"shallowest_level":stats["min_level"],
                "example_path":stats["example_path"]})
    return {"selected_finished_boms":len(refs),"changed_direct_rows":len(detailed),
        "distinct_changed_components":len(per_component),
        "receipt_priced_rows":sum(s["receipt"] for s in per_component.values()),
        "recursive_child_rows":sum(s["child"] for s in per_component.values()),
        "proposed_child_links_to_clear":sum(s["cleared_links"] for s in per_component.values()),
        "recursive_changed_path_rows":len(recursive),
        "recursive_distinct_components":len({row["component_item"] for row in recursive}),
        "details_csv":str(detail_path),"summary_csv":str(summary_path),
        "recursive_paths_csv":str(recursive_path),
        "recursive_summary_csv":str(recursive_summary_path)}
