"""Inspect and reverse the 2026-10-09 material repricing for selected Item Groups."""

import csv
import gzip
import hashlib
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

import frappe
from amf.amf.utils import data_artifact as artifacts


SNAPSHOT = artifacts.MATERIAL_SNAPSHOT
SNAPSHOT_SHA256 = "a8ff2abccbf67b8d67163d95cd7b75988ce074cf6c41a692415b527e053af08e"
ORIGINAL_EXPLOSION_SHA256 = "50c16d878a0b180b43e1b563827d5207a25b3aa142b69a996871b91bc13a227b"
GROUPS = ("Plug", "Valve Seat", "Valve Head")
SIX = Decimal("0.000001")


def _backup_path(setting):
    """Historical restore tools need an explicitly configured private backup."""
    frappe.only_for("System Manager")
    configured = frappe.conf.get(setting)
    if not configured:
        raise ValueError("Configure {} with the verified private SQL backup path".format(setting))
    path = Path(configured).expanduser().resolve()
    public_roots = (Path(frappe.get_site_path("public")).resolve(),
                    Path(frappe.get_app_path("amf", "public")).resolve(),
                    Path(frappe.get_site_path("..", "assets")).resolve())
    if any(path == root or root in path.parents for root in public_roots):
        raise ValueError("Restore backups must not be stored in public files or assets")
    if not path.is_file():
        raise ValueError("Verified private database backup is missing: {}".format(setting))
    return path


def money(value):
    return Decimal(str(value or 0)).quantize(SIX)


def source():
    saved = artifacts.get_json(SNAPSHOT, SNAPSHOT_SHA256)
    group_tree = frappe.db.sql("""
        SELECT child.name FROM `tabItem Group` root
        JOIN `tabItem Group` child ON child.lft >= root.lft AND child.rgt <= root.rgt
        WHERE root.name = 'Valve Head' ORDER BY child.lft
    """,as_dict=True)
    if {r.name for r in group_tree} != set(GROUPS):
        raise ValueError("Valve Head Item Group descendants changed")
    current = {r.item:r for r in frappe.db.sql("""
        SELECT i.name AS item,i.item_group,b.name AS bom,b.raw_material_cost,
            b.base_raw_material_cost,b.total_cost,b.base_total_cost
        FROM tabItem i JOIN tabBOM b ON b.name=i.default_bom
        WHERE i.disabled=0 AND i.item_group IN ('Plug','Valve Seat','Valve Head')
            AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    selected = [entry for entry in saved if entry["finished_item"] in current]
    if len(selected) != len(current):
        raise ValueError("Group default BOMs differ from pre-repricing snapshot")
    for entry in selected:
        if entry["bom"] != current[entry["finished_item"]].bom:
            raise ValueError("Default BOM changed: {}".format(entry["finished_item"]))
    return selected,current


def inspect():
    selected,current = source()
    changed = [entry for entry in selected if entry["status"] == "ready_changed"]
    by_group_status = Counter((current[e["finished_item"]].item_group,e["status"])
        for e in selected)
    expected_drift = []
    for entry in selected:
        now = current[entry["finished_item"]]
        for field in ("raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"):
            target = entry[("new_" if entry["status"] == "ready_changed" else "old_") + field]
            if money(now[field]) != money(target):
                expected_drift.append((entry["finished_item"],field))
    changed_names = [entry["bom"] for entry in changed]
    outside_parents = []
    for offset in range(0,len(changed_names),300):
        batch = changed_names[offset:offset + 300]
        if not batch:
            continue
        outside_parents.extend(frappe.db.sql("""
            SELECT DISTINCT b.name AS bom,b.item AS finished_item,i.item_group,
                bi.bom_no AS changed_child_bom
            FROM `tabBOM Item` bi JOIN tabBOM b ON b.name=bi.parent
            JOIN tabItem i ON i.default_bom=b.name
            WHERE bi.bom_no IN ({}) AND i.disabled=0
                AND b.docstatus=1 AND b.is_active=1
                AND i.item_group NOT IN ('Plug','Valve Seat','Valve Head')
        """.format(",".join(["%s"]*len(batch))),tuple(batch),as_dict=True))
    return {"groups":list(GROUPS),"current_default_boms":len(selected),
            "group_status_counts":{"{}: {}".format(group,status):n
                for (group,status),n in sorted(by_group_status.items())},
            "repriced_boms_to_restore":len(changed),
            "cleared_child_links_to_restore":sum(bool(row.get("clear_child_link"))
                for entry in changed for row in entry["rows"]),
            "header_drift_count":len(expected_drift),
            "header_drift_examples":expected_drift[:10],
            "outside_group_direct_parent_rows":len(outside_parents),
            "outside_group_direct_parent_examples":[dict(r) for r in outside_parents[:10]],
            "examples":[{"item_ref":e["finished_item"],
                "group":current[e["finished_item"]].item_group,"bom":e["bom"],
                "old_total":e["old_total_cost"],"current_total":current[e["finished_item"]].total_cost}
                for e in changed[:12]]}


def verify_current_against_snapshot(selected=None,current=None):
    """Refuse rollback if any selected BOM was edited after the 2026-10-09 write."""
    if selected is None or current is None:
        selected,current = source()
    rows = {r.name:r for r in frappe.db.sql("""
        SELECT bi.name,bi.parent,bi.item_code,bi.rate,bi.base_rate,
            bi.amount,bi.base_amount,bi.bom_no
        FROM `tabBOM Item` bi JOIN tabBOM b ON b.name=bi.parent
        JOIN tabItem i ON i.default_bom=b.name
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    if not all(row["row"] in rows for entry in selected for row in entry["rows"]):
        raise ValueError("Selected BOM Item row missing")
    for entry in selected:
        bom = current[entry["finished_item"]]
        expected_prefix = "new_" if entry["status"] == "ready_changed" else "old_"
        for field in ("raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"):
            if money(bom[field]) != money(entry[expected_prefix + field]):
                raise ValueError("Group BOM header drift: {} {}".format(entry["bom"],field))
        for row in entry["rows"]:
            found = rows.get(row["row"])
            if not found or found.parent != entry["bom"] or found.item_code != row["item"]:
                raise ValueError("Group BOM material row changed: {}".format(row["row"]))
            for field in ("rate","base_rate","amount","base_amount"):
                expected = row.get(expected_prefix + field)
                if expected is None or money(found[field]) != money(expected):
                    raise ValueError("Group BOM material amount drift: {} {}".format(row["row"],field))
            expected_link = None if entry["status"] == "ready_changed" and row.get("clear_child_link") else row["linked_bom"]
            if found.bom_no != expected_link:
                raise ValueError("Group BOM child link drift: {}".format(row["row"]))
    return {"verified_boms":len(selected),
        "verified_rows":sum(len(entry["rows"]) for entry in selected)}


def write_proposal(output_path):
    selected,current = source()
    verification = verify_current_against_snapshot(selected,current)
    path = artifacts.validate_name(output_path)
    fields = ("item_ref","item_group","bom","repricing_status",
        "old_raw_material_cost_chf","current_raw_material_cost_chf",
        "old_total_cost_chf","current_total_cost_chf","child_links_to_restore")
    with artifacts.csv_output(path) as target:
        writer = csv.DictWriter(target,fieldnames=fields)
        writer.writeheader()
        for entry in sorted(selected,key=lambda e:e["finished_item"]):
            now = current[entry["finished_item"]]
            writer.writerow({"item_ref":entry["finished_item"],
                "item_group":now.item_group,"bom":entry["bom"],
                "repricing_status":entry["status"],
                "old_raw_material_cost_chf":format(money(entry["old_raw_material_cost"]),".6f"),
                "current_raw_material_cost_chf":format(money(now.raw_material_cost),".6f"),
                "old_total_cost_chf":format(money(entry["old_total_cost"]),".6f"),
                "current_total_cost_chf":format(money(now.total_cost),".6f"),
                "child_links_to_restore":sum(bool(r.get("clear_child_link"))
                    for r in entry["rows"]) if entry["status"] == "ready_changed" else 0})
    return {"proposal":str(path),"target_boms":sum(e["status"] == "ready_changed" for e in selected),
        "target_links":sum(bool(r.get("clear_child_link")) for e in selected
            if e["status"] == "ready_changed" for r in e["rows"]),**verification}


def _sql_tuples(value_line):
    """Yield complete raw SQL tuples from one mysqldump INSERT line."""
    start = None
    quoted = False
    escaped = False
    for position,char in enumerate(value_line):
        if escaped:
            escaped = False
        elif quoted:
            if char == "\\":
                escaped = True
            elif char == "'":
                quoted = False
        elif char == "'":
            quoted = True
        elif char == "(":
            if start is not None:
                raise ValueError("Nested SQL tuple in backup")
            start = position
        elif char == ")":
            if start is None:
                raise ValueError("Unmatched SQL tuple end in backup")
            yield value_line[start:position + 1]
            start = None
    if start is not None or quoted:
        raise ValueError("Incomplete SQL tuple in backup")


def _tuple_parent(sql_tuple):
    """Parent is the seventh value in this site's BOM Explosion Item dump."""
    quoted = False
    escaped = False
    commas = 0
    start = 1
    for position,char in enumerate(sql_tuple[1:-1],1):
        if escaped:
            escaped = False
        elif quoted:
            if char == "\\":
                escaped = True
            elif char == "'":
                quoted = False
        elif char == "'":
            quoted = True
        elif char == ",":
            if commas == 6:
                field = sql_tuple[start:position]
                if not field.startswith("'") or not field.endswith("'"):
                    raise ValueError("Unexpected parent position in backup")
                return field[1:-1]
            commas += 1
            start = position + 1
    raise ValueError("No parent field in backup tuple")


def original_explosion_tuples(bom_names):
    """Read only selected pre-repricing explosion rows from the verified backup."""
    names = set(bom_names)
    result = {name:[] for name in names}
    prefix = "INSERT INTO `tabBOM Explosion Item` VALUES "
    seen = False
    with gzip.open(str(_backup_path("amf_bom_original_database_backup")),"rt",encoding="utf-8") as source_file:
        for line in source_file:
            if line.startswith(prefix):
                seen = True
                for sql_tuple in _sql_tuples(line[len(prefix):]):
                    parent = _tuple_parent(sql_tuple)
                    if parent in result:
                        result[parent].append(sql_tuple)
            elif seen and line.startswith("DROP TABLE IF EXISTS "):
                break
    if not seen:
        raise ValueError("BOM Explosion Item table absent from original backup")
    return result


def inspect_backup_explosion():
    selected,_ = source()
    names = [entry["bom"] for entry in selected if entry["status"] == "ready_changed"]
    original = original_explosion_tuples(names)
    missing = [name for name in names if not original[name]]
    current_count = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabBOM Explosion Item` bei
        JOIN tabBOM b ON b.name=bei.parent JOIN tabItem i ON i.default_bom=b.name
        WHERE i.disabled=0 AND i.item_group IN ('Plug','Valve Seat','Valve Head')
            AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """)[0][0]
    return {"original_changed_bom_explosion_rows":sum(len(v) for v in original.values()),
        "changed_boms_missing_original_explosion":missing,
        "current_all_group_explosion_rows":current_count}


def affected_product_scope():
    """Follow current made-child BOM links into repriced Product defaults."""
    selected,_ = source()
    saved = artifacts.get_json(SNAPSHOT, SNAPSHOT_SHA256)
    by_bom = {entry["bom"]:entry for entry in saved}
    item_groups = {r.name:r.item_group for r in frappe.db.sql(
        "SELECT name,item_group FROM tabItem",as_dict=True)}
    parents_by_child = {}
    for entry in saved:
        for row in entry["rows"]:
            link = None if entry["status"] == "ready_changed" and row.get("clear_child_link") else row["linked_bom"]
            if link:
                parents_by_child.setdefault(link,set()).add(entry["bom"])
    seed = {entry["bom"] for entry in selected if entry["status"] == "ready_changed"}
    reached = set(seed)
    queue = list(seed)
    product = set()
    outside = set()
    unchanged = set()
    while queue:
        child = queue.pop()
        for name in parents_by_child.get(child,()):
            if name in reached:
                continue
            entry = by_bom[name]
            group = item_groups.get(entry["finished_item"])
            if entry["status"] != "ready_changed":
                unchanged.add(name)
            elif group == "Product":
                product.add(name)
                reached.add(name)
                queue.append(name)
            elif group not in GROUPS:
                outside.add((name,group))
    result = [entry for entry in saved if entry["bom"] in product]
    return result,{"repriced_product_boms":len(result),
        "product_material_rows":sum(len(entry["rows"]) for entry in result),
        "product_cleared_links":sum(bool(row.get("clear_child_link"))
            for entry in result for row in entry["rows"]),
        "linked_parents_already_unchanged":len(unchanged),
        "other_group_repriced_parents":sorted(outside)[:20],
        "other_group_repriced_parent_count":len(outside)}


def inspect_product_scope():
    return affected_product_scope()[1]


def rollback_scope():
    group_selected,_ = source()
    product_selected,metrics = affected_product_scope()
    names = {entry["bom"] for entry in group_selected if entry["status"] == "ready_changed"}
    names.update(entry["bom"] for entry in product_selected)
    saved = artifacts.get_json(SNAPSHOT, SNAPSHOT_SHA256)
    selected = [entry for entry in saved if entry["bom"] in names]
    current = {r.item:r for r in frappe.db.sql("""
        SELECT i.name AS item,i.item_group,b.name AS bom,b.raw_material_cost,
            b.base_raw_material_cost,b.total_cost,b.base_total_cost
        FROM tabItem i JOIN tabBOM b ON b.name=i.default_bom
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    for entry in selected:
        now = current.get(entry["finished_item"])
        if not now or now.bom != entry["bom"]:
            raise ValueError("Rollback BOM is no longer the current default: {}".format(entry["bom"]))
        if now.item_group not in GROUPS and now.item_group != "Product":
            raise ValueError("Rollback BOM Item Group changed: {}".format(entry["bom"]))
    if len(selected) != len(names):
        raise ValueError("Missing rollback BOM in original snapshot")
    return selected,current,metrics


def write_full_proposal(output_path):
    selected,current,metrics = rollback_scope()
    verification = verify_current_against_snapshot(selected,current)
    path = artifacts.validate_name(output_path)
    fields = ("item_ref","item_group","bom","old_raw_material_cost_chf",
        "current_raw_material_cost_chf","old_total_cost_chf",
        "current_total_cost_chf","child_links_to_restore")
    with artifacts.csv_output(path) as target:
        writer = csv.DictWriter(target,fieldnames=fields)
        writer.writeheader()
        for entry in sorted(selected,key=lambda e:e["finished_item"]):
            now = current[entry["finished_item"]]
            writer.writerow({"item_ref":entry["finished_item"],
                "item_group":now.item_group,"bom":entry["bom"],
                "old_raw_material_cost_chf":format(money(entry["old_raw_material_cost"]),".6f"),
                "current_raw_material_cost_chf":format(money(now.raw_material_cost),".6f"),
                "old_total_cost_chf":format(money(entry["old_total_cost"]),".6f"),
                "current_total_cost_chf":format(money(now.total_cost),".6f"),
                "child_links_to_restore":sum(bool(r.get("clear_child_link"))
                    for r in entry["rows"])})
    return {"proposal":str(path),"target_boms":len(selected),
        "target_by_group":dict(Counter(current[e["finished_item"]].item_group for e in selected)),
        "target_links":sum(bool(r.get("clear_child_link")) for e in selected for r in e["rows"]),
        **verification,**metrics}


def original_explosion_schema_fields():
    fields = []
    inside = False
    with gzip.open(str(_backup_path("amf_bom_original_database_backup")),"rt",encoding="utf-8") as source_file:
        for line in source_file:
            if line.startswith("CREATE TABLE `tabBOM Explosion Item` ("):
                inside = True
            elif inside and line.startswith(") ENGINE"):
                break
            elif inside:
                match = re.match(r"\s*`([^`]+)`",line)
                if match:
                    fields.append(match.group(1))
    if not fields:
        raise ValueError("Original BOM Explosion Item schema not found")
    return fields


def _tuple_name(sql_tuple):
    field = sql_tuple[1:sql_tuple.index(",")]
    if not field.startswith("'") or not field.endswith("'"):
        raise ValueError("Unexpected explosion row name in backup")
    return field[1:-1]


def inspect_full_explosion_backup():
    selected,_,_ = rollback_scope()
    names = {entry["bom"] for entry in selected}
    original = original_explosion_tuples(names)
    missing = sorted(name for name in names if not original[name])
    old_schema = original_explosion_schema_fields()
    current_schema = [r.Field for r in frappe.db.sql(
        "SHOW COLUMNS FROM `tabBOM Explosion Item`",as_dict=True)]
    tuple_names = [_tuple_name(row) for values in original.values() for row in values]
    if len(tuple_names) != len(set(tuple_names)):
        raise ValueError("Duplicate original explosion row names")
    collisions = []
    for offset in range(0,len(tuple_names),500):
        batch = tuple_names[offset:offset + 500]
        if batch:
            found = frappe.db.sql("SELECT name,parent FROM `tabBOM Explosion Item` WHERE name IN ({})".format(
                ",".join(["%s"]*len(batch))),tuple(batch),as_dict=True)
            collisions.extend((r.name,r.parent) for r in found if r.parent not in names)
    digest = hashlib.sha256()
    for name in sorted(original):
        for row in original[name]:
            digest.update(row.encode("utf-8"))
            digest.update(b"\n")
    return {"original_explosion_rows":len(tuple_names),
        "target_boms_without_old_explosion":missing,
        "original_current_schema_match":old_schema == current_schema,
        "schema_field_count":len(old_schema),
        "old_explosion_name_collisions_outside_scope":collisions[:10],
        "old_explosion_sha256":digest.hexdigest()}


def _check_restore_sources(selected,original):
    if hashlib.sha256(artifacts.get_bytes(SNAPSHOT, SNAPSHOT_SHA256)).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError("Original repricing snapshot checksum changed")
    _backup_path("amf_bom_pre_rollback_database_backup")
    if original_explosion_schema_fields() != [r.Field for r in frappe.db.sql(
            "SHOW COLUMNS FROM `tabBOM Explosion Item`",as_dict=True)]:
        raise ValueError("Explosion table schema differs from October 9 backup")
    digest = hashlib.sha256()
    for name in sorted(original):
        for row in original[name]:
            digest.update(row.encode("utf-8"))
            digest.update(b"\n")
    if len(selected) == 242 and digest.hexdigest() != ORIGINAL_EXPLOSION_SHA256:
        raise ValueError("Original explosion checksum changed")
    original_names = [_tuple_name(row) for values in original.values() for row in values]
    if len(selected) == 242 and len(original_names) != 5071:
        raise ValueError("Original explosion row count changed")
    target_names = {entry["bom"] for entry in selected}
    for offset in range(0,len(original_names),500):
        batch = original_names[offset:offset + 500]
        if batch:
            found = frappe.db.sql("SELECT name,parent FROM `tabBOM Explosion Item` WHERE name IN ({})".format(
                ",".join(["%s"]*len(batch))),tuple(batch),as_dict=True)
            if any(row.parent not in target_names for row in found):
                raise ValueError("Original explosion row name now belongs to another BOM")
    missing = [entry["bom"] for entry in selected if not original[entry["bom"]]]
    if missing:
        raise ValueError("Original explosion missing for: {}".format(missing[:5]))
    if frappe.db.get_single_value("Manufacturing Settings","update_bom_costs_automatically"):
        raise ValueError("ERPNext automatic BOM cost refresh is not paused")
    if not frappe.conf.get("pause_amf_cost_writers"):
        raise ValueError("AMF automatic BOM cost writers are not paused")


def _restore_one(entry,old_explosion):
    for row in entry["rows"]:
        frappe.db.sql("""UPDATE `tabBOM Item`
            SET rate=%s,base_rate=%s,amount=%s,base_amount=%s,bom_no=%s
            WHERE name=%s AND parent=%s""",(
            row["old_rate"],row["old_base_rate"],row["old_amount"],
            row["old_base_amount"],row["linked_bom"],row["row"],entry["bom"]))
    frappe.db.sql("""UPDATE tabBOM SET raw_material_cost=%s,
        base_raw_material_cost=%s,total_cost=%s,base_total_cost=%s
        WHERE name=%s""",(
        entry["old_raw_material_cost"],entry["old_base_raw_material_cost"],
        entry["old_total_cost"],entry["old_base_total_cost"],entry["bom"]))
    frappe.db.sql("DELETE FROM `tabBOM Explosion Item` WHERE parent=%s",entry["bom"])
    for offset in range(0,len(old_explosion),100):
        batch = old_explosion[offset:offset + 100]
        frappe.db.sql("INSERT INTO `tabBOM Explosion Item` VALUES " + ",".join(batch))


def _verify_restored(selected,original):
    for entry in selected:
        name = entry["bom"]
        found = frappe.db.get_value("BOM",name,
            ["raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"],
            as_dict=True)
        for field in ("raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"):
            if money(found[field]) != money(entry["old_" + field]):
                raise ValueError("Restored BOM header mismatch: {} {}".format(name,field))
        for row in entry["rows"]:
            found = frappe.db.get_value("BOM Item",row["row"],
                ["rate","base_rate","amount","base_amount","bom_no"],as_dict=True)
            for field in ("rate","base_rate","amount","base_amount"):
                if money(found[field]) != money(row["old_" + field]):
                    raise ValueError("Restored material amount mismatch: {} {}".format(row["row"],field))
            if found.bom_no != row["linked_bom"]:
                raise ValueError("Restored child link mismatch: {}".format(row["row"]))
        names = {r.name for r in frappe.db.sql(
            "SELECT name FROM `tabBOM Explosion Item` WHERE parent=%s",name,as_dict=True)}
        expected = {_tuple_name(sql_tuple) for sql_tuple in original[name]}
        if names != expected:
            raise ValueError("Restored explosion row names mismatch: {}".format(name))


def preflight_one(item_ref):
    selected,current,_ = rollback_scope()
    entry = next((e for e in selected if e["finished_item"] == item_ref),None)
    if not entry:
        raise ValueError("Choose one of the target Item refs")
    verify_current_against_snapshot([entry],current)
    original = original_explosion_tuples([entry["bom"]])
    _check_restore_sources([entry],original)
    try:
        _restore_one(entry,original[entry["bom"]])
        _verify_restored([entry],original)
        result = {"item_ref":item_ref,"bom":entry["bom"],
            "restored_material_rows_during_test":len(entry["rows"]),
            "restored_explosion_rows_during_test":len(original[entry["bom"]])}
    finally:
        frappe.db.rollback()
    return result


def apply_rollback():
    selected,current,metrics = rollback_scope()
    if len(selected) != 242 or metrics["repriced_product_boms"] != 133:
        raise ValueError("Rollback scope differs from reviewed 242 BOMs")
    verify_current_against_snapshot(selected,current)
    original = original_explosion_tuples([entry["bom"] for entry in selected])
    _check_restore_sources(selected,original)
    try:
        for entry in selected:
            _restore_one(entry,original[entry["bom"]])
        _verify_restored(selected,original)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise
    return {"restored_boms":len(selected),
        "restored_by_group":dict(Counter(current[e["finished_item"]].item_group for e in selected)),
        "restored_material_rows":sum(len(entry["rows"]) for entry in selected),
        "restored_child_links":sum(bool(row.get("clear_child_link"))
            for entry in selected for row in entry["rows"]),
        "restored_exact_original_explosion_rows":sum(len(v) for v in original.values())}


def _sql_fields(sql_tuple):
    fields = []
    start = 1
    quoted = False
    escaped = False
    for position,char in enumerate(sql_tuple[1:-1],1):
        if escaped:
            escaped = False
        elif quoted:
            if char == "\\":
                escaped = True
            elif char == "'":
                quoted = False
        elif char == "'":
            quoted = True
        elif char == ",":
            fields.append(sql_tuple[start:position])
            start = position + 1
    fields.append(sql_tuple[start:-1])
    return fields


def verify_after_rollback(comparison_csv_path):
    """Read back every original default BOM plus exact old explosion costs."""
    selected,_,_ = rollback_scope()
    targets = {entry["bom"] for entry in selected}
    saved = artifacts.get_json(SNAPSHOT, SNAPSHOT_SHA256)
    current = {r.name:r for r in frappe.db.sql("""
        SELECT b.name,b.item,b.raw_material_cost,b.base_raw_material_cost,
            b.total_cost,b.base_total_cost
        FROM tabItem i JOIN tabBOM b ON b.name=i.default_bom
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    if set(current) != {entry["bom"] for entry in saved}:
        raise ValueError("Current default BOM set differs from original snapshot")
    material = {r.name:r for r in frappe.db.sql("""
        SELECT bi.name,bi.parent,bi.item_code,bi.rate,bi.base_rate,
            bi.amount,bi.base_amount,bi.bom_no
        FROM `tabBOM Item` bi JOIN tabBOM b ON b.name=bi.parent
        JOIN tabItem i ON i.default_bom=b.name
        WHERE i.disabled=0 AND b.item=i.name AND b.docstatus=1 AND b.is_active=1
    """,as_dict=True)}
    if len(material) != sum(len(entry["rows"]) for entry in saved):
        raise ValueError("Current default BOM Item count differs from original snapshot")
    for entry in saved:
        restored = entry["bom"] in targets
        prefix = "old_" if restored or entry["status"] != "ready_changed" else "new_"
        bom = current[entry["bom"]]
        if bom.item != entry["finished_item"]:
            raise ValueError("BOM finished Item changed: {}".format(entry["bom"]))
        for field in ("raw_material_cost","base_raw_material_cost","total_cost","base_total_cost"):
            if money(bom[field]) != money(entry[prefix + field]):
                raise ValueError("Post-rollback BOM header differs: {} {}".format(entry["bom"],field))
        for row in entry["rows"]:
            found = material[row["row"]]
            if found.parent != entry["bom"] or found.item_code != row["item"]:
                raise ValueError("Post-rollback material relationship differs: {}".format(row["row"]))
            for field in ("rate","base_rate","amount","base_amount"):
                if money(found[field]) != money(row[prefix + field]):
                    raise ValueError("Post-rollback material cost differs: {} {}".format(row["row"],field))
            expected_link = None if (not restored and entry["status"] == "ready_changed"
                and row.get("clear_child_link")) else row["linked_bom"]
            if found.bom_no != expected_link:
                raise ValueError("Post-rollback child link differs: {}".format(row["row"]))
    original = original_explosion_tuples(targets)
    columns = original_explosion_schema_fields()
    numeric_indexes = {field:columns.index(field) for field in ("stock_qty","rate","amount")}
    actual_explosion = {}
    for offset in range(0,len(targets),300):
        batch = sorted(targets)[offset:offset + 300]
        found = frappe.db.sql("""SELECT name,parent,stock_qty,rate,amount
            FROM `tabBOM Explosion Item` WHERE parent IN ({})""".format(
            ",".join(["%s"]*len(batch))),tuple(batch),as_dict=True)
        actual_explosion.update({row.name:row for row in found})
    if len(actual_explosion) != sum(len(values) for values in original.values()):
        raise ValueError("Post-rollback exploded material count differs")
    for bom,tuples in original.items():
        for sql_tuple in tuples:
            name = _tuple_name(sql_tuple)
            found = actual_explosion.get(name)
            if not found or found.parent != bom:
                raise ValueError("Post-rollback original explosion row missing: {}".format(name))
            values = _sql_fields(sql_tuple)
            if len(values) != len(columns):
                raise ValueError("Original explosion field count differs: {}".format(name))
            for field,index in numeric_indexes.items():
                if money(found[field]) != money(values[index]):
                    raise ValueError("Post-rollback explosion cost differs: {} {}".format(name,field))
    path = artifacts.validate_name(comparison_csv_path)
    with artifacts.csv_output(path) as target_file:
        writer = csv.writer(target_file)
        writer.writerow(("item_ref","old_bom_cost_chf","current_bom_cost_chf"))
        for entry in sorted(saved,key=lambda e:e["finished_item"]):
            writer.writerow((entry["finished_item"],
                format(money(entry["old_total_cost"]),".6f"),
                format(money(current[entry["bom"]].total_cost),".6f")))
    return {"verified_default_boms":len(saved),
        "verified_material_rows":len(material),"restored_boms":len(targets),
        "verified_original_explosion_rows":len(actual_explosion),
        "comparison_csv":str(path)}
