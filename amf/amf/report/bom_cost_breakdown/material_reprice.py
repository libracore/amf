"""Auditable material-only repricing for enabled Items' current default BOMs.

Run ``write_proposal`` first. ``apply_proposal`` accepts only an identical fresh
calculation, then updates complete BOMs in one transaction. This intentionally
does not invoke BOM.save/update_cost: ERPNext v12 would recalculate the agreed
receipt rates from its own valuation settings.
"""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import frappe


SIX = Decimal("0.000001")


def dec(value):
    return Decimal(str(value or 0))


def six(value):
    return dec(value).quantize(SIX, rounding=ROUND_HALF_UP)


def serial(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serial(x) for x in value]
    if isinstance(value, dict):
        return {key: serial(val) for key, val in value.items()}
    return value


def load_source():
    boms = {r.name: r for r in frappe.db.sql("""
        SELECT b.name,b.item,b.company,b.currency,b.quantity,b.conversion_rate,
            b.raw_material_cost,b.base_raw_material_cost,b.operating_cost,
            b.base_operating_cost,b.scrap_material_cost,b.base_scrap_material_cost,
            b.total_cost,b.base_total_cost
        FROM tabItem i JOIN tabBOM b ON b.name=i.default_bom
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
        ORDER BY b.name
    """, as_dict=True)}
    rows = frappe.db.sql("""
        SELECT bi.name,bi.parent,bi.idx,bi.item_code,bi.bom_no,bi.qty,
            bi.stock_qty,bi.conversion_factor,bi.uom,bi.stock_uom,
            bi.rate,bi.base_rate,bi.amount,bi.base_amount,
            i.name AS found_item,i.disabled,i.is_purchase_item,i.default_bom,
            i.stock_uom AS item_stock_uom,i.valuation_rate,
            cb.item AS child_item,cb.company AS child_company,
            cb.docstatus AS child_docstatus,cb.is_active AS child_active
        FROM `tabBOM Item` bi JOIN tabBOM b ON b.name=bi.parent
        JOIN tabItem pi ON pi.default_bom=b.name
        LEFT JOIN tabItem i ON i.name=bi.item_code
        LEFT JOIN tabBOM cb ON cb.name=i.default_bom
        WHERE pi.disabled=0 AND b.item=pi.name AND b.docstatus=1 AND b.is_active=1
        ORDER BY bi.parent,bi.idx
    """, as_dict=True)
    by_bom = defaultdict(list)
    for row in rows:
        by_bom[row.parent].append(row)
    codes = sorted({row.item_code for row in rows if row.item_code})
    receipts = {}
    companies = sorted({bom.company for bom in boms.values()})
    for company in companies:
        for offset in range(0, len(codes), 500):
            batch = codes[offset:offset + 500]
            if not batch:
                continue
            found = frappe.db.sql("""
                SELECT pri.item_code,pr.name AS receipt,pr.posting_date,
                    pr.posting_time,pr.creation,
                    SUM(pri.stock_qty) AS stock_qty,
                    SUM(pri.base_net_amount) AS base_net_amount,
                    COUNT(*) AS qualifying_lines
                FROM `tabPurchase Receipt Item` pri
                JOIN `tabPurchase Receipt` pr ON pr.name=pri.parent
                WHERE pri.item_code IN ({}) AND pr.company=%s AND pr.docstatus=1
                    AND IFNULL(pr.is_return,0)=0 AND IFNULL(pri.is_free_item,0)=0
                    AND pri.stock_qty>0 AND pri.base_net_amount>0
                GROUP BY pri.item_code,pr.name,pr.posting_date,pr.posting_time,pr.creation
                ORDER BY pri.item_code,pr.posting_date DESC,pr.posting_time DESC,
                    pr.creation DESC,pr.name DESC
            """.format(",".join(["%s"] * len(batch))), tuple(batch) + (company,), as_dict=True)
            for receipt in found:
                receipts.setdefault((company, receipt.item_code), receipt)
    return boms, by_bom, receipts


def build_plan():
    boms, by_bom, receipts = load_source()
    memo = {}

    def evaluate(name, active=()):
        if name in memo:
            return memo[name]
        if name in active:
            return {"bom": name, "status": "blocked", "reasons": ["bom_cycle"], "rows": []}
        bom = boms[name]
        reasons = []
        priced = []
        for row in by_bom[name]:
            result = {"row": row.name, "idx": row.idx, "item": row.item_code,
                      "linked_bom": row.bom_no, "qty": dec(row.qty),
                      "stock_qty": dec(row.stock_qty), "old_rate": dec(row.rate),
                      "old_base_rate": dec(row.base_rate),
                      "old_amount": dec(row.amount),
                      "old_base_amount": dec(row.base_amount)}
            reason = None
            if not row.found_item:
                reason = "missing_component_item"
            elif row.disabled:
                reason = "disabled_component"
            elif row.stock_uom != row.item_stock_uom:
                reason = "stock_uom_mismatch"
            elif dec(row.stock_qty) < 0:
                # Preserve the exact negative stored credit as approved.
                result.update(source=row.name, method="stored_negative_material_credit",
                              new_rate=dec(row.rate),new_base_rate=dec(row.base_rate),
                              new_amount=dec(row.amount),new_base_amount=dec(row.base_amount),
                              flag="negative_credit")
            elif dec(row.qty) <= 0 or dec(row.stock_qty) <= 0 or dec(row.conversion_factor) <= 0:
                reason = "nonpositive_quantity_or_conversion"
            elif abs(dec(row.qty) * dec(row.conversion_factor) - dec(row.stock_qty)) > SIX:
                reason = "quantity_conversion_mismatch"
            elif dec(bom.conversion_rate) != 1 or bom.currency != "CHF":
                reason = "unsupported_bom_currency_conversion"
            else:
                receipt = receipts.get((bom.company, row.item_code))
                unit = None
                if receipt:
                    if not row.is_purchase_item:
                        reason = "receipt_but_purchase_flag_off"
                    else:
                        unit = dec(receipt.base_net_amount) / dec(receipt.stock_qty)
                        result.update(source=receipt.receipt,
                                      method="latest_receipt_weighted_base_net_per_stock_unit",
                                      clear_child_link=bool(row.bom_no),
                                      receipt_stock_qty=dec(receipt.stock_qty),
                                      receipt_base_net_amount=dec(receipt.base_net_amount),
                                      receipt_qualifying_lines=receipt.qualifying_lines,
                                      receipt_posted="{} {}".format(receipt.posting_date, receipt.posting_time))
                elif row.default_bom:
                    if (row.child_item != row.item_code or row.child_docstatus != 1
                            or not row.child_active or row.child_company != bom.company
                            or row.default_bom not in boms):
                        reason = "invalid_component_default_bom"
                    elif row.bom_no != row.default_bom:
                        reason = "stored_child_link_differs_from_default"
                    else:
                        child = evaluate(row.default_bom, active + (name,))
                        if child["status"] == "blocked":
                            reason = "child_bom_unavailable:{}".format(row.default_bom)
                        else:
                            unit = (dec(child["new_raw_material_cost"]) - dec(child["old_scrap_material_cost"])) / dec(child["quantity"])
                            result.update(source=row.default_bom,
                                          method="child_default_raw_material_less_stored_scrap_per_finished_unit")
                elif row.bom_no:
                    reason = "linked_bom_without_item_default"
                elif not row.is_purchase_item:
                    reason = "no_receipt_or_default_and_not_purchase_item"
                elif dec(row.valuation_rate) <= 0:
                    reason = "no_receipt_or_usable_item_valuation"
                else:
                    unit = dec(row.valuation_rate)
                    result.update(source=row.item_code,
                                  method="Item.valuation_rate_per_stock_unit_fallback")
                if reason is None:
                    rate = six(unit * dec(row.conversion_factor))
                    amount = six(rate * dec(row.qty))
                    result.update(unit_stock_rate=unit,new_rate=rate,new_base_rate=rate,
                                  new_amount=amount,new_base_amount=amount)
            if reason:
                reasons.append("{}:{}:{}".format(row.idx,row.item_code,reason))
                result.update(reason=reason)
            priced.append(result)
        plan = {"bom": name,"finished_item": bom.item,"company": bom.company,
                "currency": bom.currency,"quantity": dec(bom.quantity),
                "old_raw_material_cost": dec(bom.raw_material_cost),
                "old_base_raw_material_cost": dec(bom.base_raw_material_cost),
                "old_operating_cost": dec(bom.operating_cost),
                "old_base_operating_cost": dec(bom.base_operating_cost),
                "old_scrap_material_cost": dec(bom.scrap_material_cost),
                "old_base_scrap_material_cost": dec(bom.base_scrap_material_cost),
                "old_total_cost": dec(bom.total_cost),
                "old_base_total_cost": dec(bom.base_total_cost),
                "rows": priced, "reasons": reasons}
        if dec(bom.quantity) <= 0:
            reasons.append("nonpositive_finished_quantity")
        if reasons:
            plan["status"] = "blocked"
        else:
            raw = six(sum((r["new_amount"] for r in priced), Decimal(0)))
            plan["new_raw_material_cost"] = raw
            plan["new_base_raw_material_cost"] = raw
            plan["new_total_cost"] = six(dec(bom.operating_cost) + raw - dec(bom.scrap_material_cost))
            plan["new_base_total_cost"] = six(dec(bom.base_operating_cost) + raw - dec(bom.base_scrap_material_cost))
            plan["status"] = "ready_changed" if (
                raw != dec(bom.raw_material_cost) or raw != dec(bom.base_raw_material_cost)
                or plan["new_total_cost"] != dec(bom.total_cost)
                or plan["new_base_total_cost"] != dec(bom.base_total_cost)
                or any(r["new_rate"] != r["old_rate"] or r["new_amount"] != r["old_amount"]
                       or r["new_base_rate"] != r["old_base_rate"]
                       or r["new_base_amount"] != r["old_base_amount"]
                       or r.get("clear_child_link") for r in priced)
            ) else "ready_unchanged"
        memo[name] = plan
        return plan

    for name in sorted(boms):
        evaluate(name)
    # Recursive evaluation inserts completed child plans before their parents.
    return list(memo.values())


def proposal_bytes(plan):
    return json.dumps(serial(plan),sort_keys=True,indent=2,default=str).encode("utf-8") + b"\n"


def write_proposal(output_prefix):
    plan = build_plan()
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    path = prefix.with_suffix(".json")
    payload = proposal_bytes(plan)
    path.write_bytes(payload)
    with prefix.with_suffix(".csv").open("w",newline="",encoding="utf-8") as target:
        fields = ["bom","finished_item","status","reasons","old_raw_material_cost",
                  "new_raw_material_cost","old_total_cost","new_total_cost"]
        writer = csv.DictWriter(target,fieldnames=fields)
        writer.writeheader()
        for entry in plan:
            writer.writerow({key: "; ".join(entry[key]) if key == "reasons" else entry.get(key)
                             for key in fields})
    detail_path = prefix.with_name(prefix.name + "_rows").with_suffix(".csv")
    with detail_path.open("w",newline="",encoding="utf-8") as target:
        fields = ["bom","finished_item","bom_status","row","idx","item",
                  "qty","stock_qty","linked_bom","clear_child_link","method","source",
                  "receipt_posted","receipt_qualifying_lines","receipt_stock_qty",
                  "receipt_base_net_amount","unit_stock_rate","old_rate","new_rate",
                  "old_amount","new_amount","reason","flag"]
        writer = csv.DictWriter(target,fieldnames=fields)
        writer.writeheader()
        for entry in plan:
            for row in entry["rows"]:
                writer.writerow({field: entry["bom"] if field == "bom" else
                    entry["finished_item"] if field == "finished_item" else
                    entry["status"] if field == "bom_status" else row.get(field)
                    for field in fields})
    return {"json":str(path),"csv":str(prefix.with_suffix(".csv")),
            "rows_csv":str(detail_path),
            "sha256":hashlib.sha256(payload).hexdigest(),
            "statuses":dict(Counter(entry["status"] for entry in plan)),
            "clear_link_rows_in_ready_boms":sum(sum(1 for r in entry["rows"]
                if r.get("clear_child_link")) for entry in plan if entry["status"].startswith("ready")),
            "blocked_reasons":dict(Counter(r.split(":",2)[-1].split(":")[0]
                for entry in plan for r in entry["reasons"]))}


def apply_proposal(json_path):
    """Apply only if current records and source receipts reproduce the proposal."""
    path = Path(json_path)
    saved = path.read_bytes()
    current = build_plan()
    if proposal_bytes(current) != saved:
        raise ValueError("Proposal differs from current BOM, Item, or Purchase Receipt data; regenerate")
    if frappe.db.get_single_value("Manufacturing Settings", "update_bom_costs_automatically"):
        raise ValueError("ERPNext automatic BOM cost refresh is not paused")
    if not frappe.conf.get("pause_amf_cost_writers"):
        raise ValueError("AMF automatic BOM cost writers are not paused")
    changed = [entry for entry in current if entry["status"] == "ready_changed"]
    try:
        for entry in changed:
            _apply_entry(entry)
        _verify_applied(changed)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise
    return {"updated_boms":len(changed),
            "updated_material_rows":sum(sum(1 for r in x["rows"] if not r.get("flag")) for x in changed),
            "cleared_child_links":sum(sum(1 for r in x["rows"] if r.get("clear_child_link")) for x in changed)}


def _apply_entry(entry):
    for row in entry["rows"]:
        if row.get("flag") == "negative_credit":
            continue
        frappe.db.sql("""UPDATE `tabBOM Item`
            SET rate=%s,base_rate=%s,amount=%s,base_amount=%s,
                bom_no=CASE WHEN %s=1 THEN NULL ELSE bom_no END
            WHERE name=%s AND parent=%s""",(
            str(row["new_rate"]),str(row["new_base_rate"]),
            str(row["new_amount"]),str(row["new_base_amount"]),
            1 if row.get("clear_child_link") else 0,row["row"],entry["bom"]))
    frappe.db.sql("""UPDATE tabBOM SET raw_material_cost=%s,
        base_raw_material_cost=%s,total_cost=%s,base_total_cost=%s
        WHERE name=%s""",(
        str(entry["new_raw_material_cost"]),str(entry["new_base_raw_material_cost"]),
        str(entry["new_total_cost"]),str(entry["new_base_total_cost"]),entry["bom"]))
    # ERPNext's exploded rows are production inputs. Rebuild after child
    # updates so a bought component replaces its previous child expansion.
    frappe.get_doc("BOM",entry["bom"]).update_exploded_items()


def _verify_applied(changed):
    for entry in changed:
        found = frappe.db.get_value("BOM",entry["bom"],
            ["raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"],
            as_dict=True)
        for field in ("raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"):
            if six(found[field]) != entry["new_" + field]:
                raise ValueError("Post-write BOM header mismatch: {} {}".format(entry["bom"],field))
        for row in entry["rows"]:
            found = frappe.db.get_value("BOM Item",row["row"],
                ["rate","base_rate","amount","base_amount","bom_no"],as_dict=True)
            for field in ("rate","base_rate","amount","base_amount"):
                if six(found[field]) != row["new_" + field]:
                    raise ValueError("Post-write BOM Item mismatch: {} {}".format(row["row"],field))
            expected_link = None if row.get("clear_child_link") else row["linked_bom"]
            if found.bom_no != expected_link:
                raise ValueError("Post-write child link mismatch: {}".format(row["row"]))


def preflight_one(json_path, bom_name):
    """Exercise the write and ERPNext explosion rebuild, then roll it back."""
    saved = Path(json_path).read_bytes()
    current = build_plan()
    if proposal_bytes(current) != saved:
        raise ValueError("Proposal differs from current source data")
    selected = next((entry for entry in current if entry["bom"] == bom_name),None)
    if not selected or selected["status"] != "ready_changed":
        raise ValueError("Select a ready_changed BOM")
    try:
        _apply_entry(selected)
        _verify_applied([selected])
        explosion_count = frappe.db.count("BOM Explosion Item",{"parent":bom_name})
        result = {"bom":bom_name,"validated_rows":len(selected["rows"]),
                  "explosion_rows_during_test":explosion_count,
                  "planned_new_raw_material_cost":str(selected["new_raw_material_cost"])}
    finally:
        frappe.db.rollback()
    return result


def verify_proposal(json_path):
    """Independent persisted read-back, including untouched blocked BOMs."""
    plan = json.loads(Path(json_path).read_text(encoding="utf-8"))
    names = {entry["bom"] for entry in plan}
    current_defaults = {row.name for row in frappe.db.sql("""
        SELECT b.name FROM tabItem i JOIN tabBOM b ON b.name=i.default_bom
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    if current_defaults != names:
        raise ValueError("Current enabled Item.default_bom set changed")
    boms = {row.name:row for row in frappe.db.sql("""
        SELECT b.name,b.raw_material_cost,b.base_raw_material_cost,
            b.total_cost,b.base_total_cost,b.operating_cost,b.scrap_material_cost
        FROM tabItem i JOIN tabBOM b ON b.name=i.default_bom
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    rows = {row.name:row for row in frappe.db.sql("""
        SELECT bi.name,bi.parent,bi.item_code,bi.stock_qty,bi.rate,bi.base_rate,
            bi.amount,bi.base_amount,bi.bom_no
        FROM `tabBOM Item` bi JOIN tabBOM b ON b.name=bi.parent
        JOIN tabItem i ON i.default_bom=b.name
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    if len(rows) != sum(len(entry["rows"]) for entry in plan):
        raise ValueError("BOM Item row count changed")
    statuses = Counter()
    for entry in plan:
        status = entry["status"]
        statuses[status] += 1
        bom = boms[entry["bom"]]
        for field in ("raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"):
            target = entry[("new_" if status == "ready_changed" else "old_") + field]
            if six(bom[field]) != six(target):
                raise ValueError("BOM header drift: {} {}".format(entry["bom"],field))
        if status == "ready_changed" and six(bom.total_cost) != six(
                dec(bom.operating_cost) + dec(bom.raw_material_cost) - dec(bom.scrap_material_cost)):
            raise ValueError("BOM total arithmetic mismatch: {}".format(entry["bom"]))
        for row in entry["rows"]:
            current = rows[row["row"]]
            if current.parent != entry["bom"] or current.item_code != row["item"]:
                raise ValueError("BOM Item relationship changed: {}".format(row["row"]))
            for field in ("rate","base_rate","amount","base_amount"):
                target = row[("new_" if status == "ready_changed" else "old_") + field]
                if six(current[field]) != six(target):
                    raise ValueError("BOM Item amount drift: {} {}".format(row["row"],field))
            target_link = None if status == "ready_changed" and row.get("clear_child_link") else row["linked_bom"]
            if current.bom_no != target_link:
                raise ValueError("BOM Item route drift: {}".format(row["row"]))
    # Verify that every newly bought component is now an exploded production
    # input. A component can also occur elsewhere in the same BOM tree.
    bought = defaultdict(set)
    for entry in plan:
        if entry["status"] == "ready_changed":
            bought[entry["bom"]].update(row["item"] for row in entry["rows"]
                if row.get("clear_child_link"))
    exploded = defaultdict(set)
    if bought:
        found = frappe.db.sql("""
            SELECT bei.parent,bei.item_code FROM `tabBOM Explosion Item` bei
            JOIN tabBOM b ON b.name=bei.parent
            JOIN tabItem i ON i.default_bom=b.name
            WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
        """,as_dict=True)
        for row in found:
            exploded[row.parent].add(row.item_code)
    for bom,items in bought.items():
        if not items.issubset(exploded[bom]):
            raise ValueError("Bought component missing from explosion: {} {}".format(
                bom,sorted(items - exploded[bom])))
    return {"verified_boms":len(plan),"verified_material_rows":len(rows),
            "statuses":dict(statuses),
            "verified_bought_route_links_cleared":sum(len(items) for items in bought.values()),
            "representative_458040_raw_material_cost":str(boms["BOM-458040-012"].raw_material_cost)}


def verify_explosion_quantities(json_path):
    """Compare every updated flat BOM quantity with its actual material tree."""
    plan = json.loads(Path(json_path).read_text(encoding="utf-8"))
    by_bom = {entry["bom"]:entry for entry in plan}
    actual_rows = frappe.db.sql("""
        SELECT bi.parent,bi.item_code,bi.stock_qty,bi.bom_no
        FROM `tabBOM Item` bi JOIN tabBOM b ON b.name=bi.parent
        JOIN tabItem i ON i.default_bom=b.name
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
        ORDER BY bi.parent,bi.idx
    """,as_dict=True)
    by_parent = defaultdict(list)
    for row in actual_rows:
        by_parent[row.parent].append(row)
    memo = {}

    def flatten(name,active=()):
        if name in memo:
            return memo[name]
        if name in active:
            raise ValueError("Cycle in current material links: {}".format(name))
        result = defaultdict(Decimal)
        for row in by_parent[name]:
            if row.bom_no:
                if row.bom_no not in by_bom:
                    raise ValueError("Linked BOM outside current defaults: {}".format(row.bom_no))
                multiplier = dec(row.stock_qty) / dec(by_bom[row.bom_no]["quantity"])
                for item,qty in flatten(row.bom_no,active + (name,)).items():
                    result[item] += qty * multiplier
            else:
                result[row.item_code] += dec(row.stock_qty)
        memo[name] = result
        return result

    exploded = defaultdict(dict)
    for row in frappe.db.sql("""
        SELECT bei.parent,bei.item_code,SUM(bei.stock_qty) AS stock_qty
        FROM `tabBOM Explosion Item` bei JOIN tabBOM b ON b.name=bei.parent
        JOIN tabItem i ON i.default_bom=b.name
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
        GROUP BY bei.parent,bei.item_code
    """,as_dict=True):
        exploded[row.parent][row.item_code] = dec(row.stock_qty)
    updated = [entry for entry in plan if entry["status"] == "ready_changed"]
    for entry in updated:
        expected = flatten(entry["bom"])
        stored = exploded[entry["bom"]]
        for item in set(expected) | set(stored):
            if abs(expected.get(item,Decimal(0)) - stored.get(item,Decimal(0))) > Decimal("0.001"):
                raise ValueError("Explosion quantity differs: {} {} expected {} stored {}".format(
                    entry["bom"],item,expected.get(item,0),stored.get(item,0)))
    return {"verified_updated_explosions":len(updated)}
