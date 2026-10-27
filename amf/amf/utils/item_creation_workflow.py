"""Engineering review and transaction-owned execution of Item Creation plans."""
import json
from copy import deepcopy
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import now_datetime

from amf.amf.utils import item_code_family as families
from amf.amf.utils import item_creation_compatibility as compatibility
from amf.amf.utils.item_creation_plan import INPUT_FIELDS, build_plan, encode, input_hash, recipe_rows


PROTECTED_FIELDS = ("review_status", "approved_plan_hash", "approved_input_hash", "reviewed_by",
                    "reviewed_at", "creation_result")
HISTORY_FIELDS = ("name", "idx", "reviewed_by", "reviewed_at", "plan_hash", "input_hash", "review_notes", "plan_snapshot")


@contextmanager
def workflow_write():
    previous = getattr(frappe.local, "amf_item_creation_workflow_write", False)
    frappe.local.amf_item_creation_workflow_write = True
    try:
        yield
    finally:
        frappe.local.amf_item_creation_workflow_write = previous


def protect_review_fields(doc):
    if getattr(frappe.local, "amf_item_creation_workflow_write", False):
        return
    previous = doc.get_doc_before_save()
    for field in PROTECTED_FIELDS:
        before = previous.get(field) if previous else ("Draft" if field == "review_status" else None)
        if str(doc.get(field) or "") != str(before or ""):
            frappe.throw(_("Engineering review and execution results can only be changed through their server actions."))
    history = lambda source: [{key: str(row.get(key) or "") for key in HISTORY_FIELDS}
                              for row in source.get("review_history") or []] if source else []
    if history(doc) != history(previous):
        frappe.throw(_("Engineering review history cannot be changed or deleted."))
    if doc.get("approved_input_hash") and input_hash(doc) != doc.approved_input_hash:
        doc.review_status = "Stale"
        doc.approved_plan_hash = doc.approved_input_hash = None
        doc.reviewed_by = doc.reviewed_at = None


def _source_for_preview(payload):
    data = frappe.parse_json(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict):
        frappe.throw(_("A valid Item Creation document is required."))
    if not frappe.has_permission("Item", "read") or not frappe.has_permission("BOM", "read"):
        frappe.throw(_("Item and BOM read permissions are required for engineering preview."), frappe.PermissionError)
    name = data.get("name")
    if name and not data.get("__islocal"):
        source = frappe.get_doc("Item Creation", name)
        source.check_permission("read")
        if source.docstatus != 0:
            return source
    elif not frappe.has_permission("Item Creation", "create"):
        frappe.throw(_("You cannot prepare Item Creation requests."), frappe.PermissionError)
    values = frappe._dict({field: data.get(field) for field in INPUT_FIELDS})
    values.update(dict(name=name, doctype="Item Creation", product_variants=data.get("product_variants") or []))
    if not isinstance(values.product_variants, list) or any(not isinstance(row, dict) for row in values.product_variants):
        frappe.throw(_("Product configurations must be a table of body/syringe selections."))
    if len(values.product_variants) > len(compatibility.CONFIGURATIONS):
        frappe.throw(_("The request contains too many product configurations."))
    return values


@frappe.whitelist()
def get_creation_plan(document):
    source = _source_for_preview(document)
    if source.get("docstatus") in (1, 2):
        if source.get("review_history"):
            plan = json.loads(source.review_history[-1].plan_snapshot)
            if source.creation_result:
                plan["result"] = json.loads(source.creation_result)
            return plan
        return dict(ready=False, actions=[], summary={}, errors=[], warnings=[
            _("Historical request: no engineering plan was recorded under the new workflow. Its existing records are retained.")])
    return build_plan(source)


@frappe.whitelist()
def get_compatible_variants(document):
    source = _source_for_preview(document)
    if source.get("head_check") == "No" and source.get("head_item"):
        head = frappe.get_doc("Item", source.head_item)
        head.check_permission("read")
        source.head_name = head.item_name
    allowed = compatibility.allowed_families(source.get("head_name"))
    parts = (source.get("head_name") or "").upper().split("-")
    head_type = parts[1] if len(parts) > 1 else ""
    rules = [row for row in compatibility.CONFIGURATIONS if row["family"] in allowed
             and head_type in compatibility.HEAD_TYPES[row["family"]]
             and compatibility.checked(source.get(compatibility.FAMILY_FLAGS[row["family"]]))]
    names = {row["body"] for row in rules} | {row["syringe"] for row in rules if row["syringe"]}
    available = {row.name: row for row in frappe.get_all("Item", filters={"name": ["in", sorted(names)], "disabled": 0},
                 fields=["name", "item_name", "item_group", "reference_code"])} if names else {}
    return [dict(body=row["body"], syringe=row["syringe"], family=row["family"],
                 configuration=row["body_label"] + (" / " + (available[row["syringe"]].reference_code or row["syringe"]) if row["syringe"] else ""))
            for row in rules if row["body"] in available and available[row["body"]].item_group == "Body"
            and available[row["body"]].reference_code == row["body_label"]
            and (not row["syringe"] or (row["syringe"] in available and available[row["syringe"]].item_group == "Syringe"
                 and available[row["syringe"]].reference_code == compatibility.SYRINGE_REFERENCES[row["token"]]))]


def _lock_source(name):
    frappe.db.sql("SELECT name FROM `tabItem Creation` WHERE name = %s FOR UPDATE", name)


def require_ready(plan):
    if plan["errors"]:
        frappe.throw(_("Resolve the creation plan errors before review or submission:") + "\n" +
                     "\n".join(row["message"] for row in plan["errors"]))


@frappe.whitelist(methods=["POST"])
def record_engineering_review(name, fingerprint, review_notes):
    frappe.only_for("System Manager")
    _lock_source(name)
    source = frappe.get_doc("Item Creation", name)
    source.check_permission("write")
    source.check_permission("submit")
    if source.docstatus != 0:
        frappe.throw(_("Engineering review is available only for a draft request."))
    if not (review_notes or "").strip():
        frappe.throw(_("Record the engineering review notes, including stock dimensions and any replacement decisions."))
    # Review records a read-only snapshot. Submission takes dependency locks;
    # holding them while source.save acquires the family mutex reverses lock order.
    plan = build_plan(source)
    require_ready(plan)
    if plan["fingerprint"] != fingerprint:
        frappe.throw(_("The request or its dependencies changed. Refresh the complete plan before reviewing."))
    with workflow_write():
        source.review_status = "Reviewed"
        source.approved_plan_hash, source.approved_input_hash = plan["fingerprint"], plan["input_hash"]
        source.reviewed_by, source.reviewed_at = frappe.session.user, now_datetime()
        source.append("review_history", dict(reviewed_by=source.reviewed_by, reviewed_at=source.reviewed_at,
            plan_hash=plan["fingerprint"], input_hash=plan["input_hash"], review_notes=review_notes.strip(),
            plan_snapshot=encode(plan)))
        source.save()
    return dict(fingerprint=plan["fingerprint"], reviewed_by=source.reviewed_by, reviewed_at=source.reviewed_at)


def validate_submission(source):
    _lock_source(source.name)
    if source.get("review_status") != "Reviewed" or not source.get("approved_plan_hash"):
        frappe.throw(_("Preview the complete plan and record its engineering review before submitting."))
    plan = build_plan(source, lock=True)
    require_ready(plan)
    if source.approved_plan_hash != plan["fingerprint"] or source.approved_input_hash != plan["input_hash"]:
        frappe.throw(_("Engineering review is stale: the definition or a dependency changed. Refresh and review the plan again."))
    if not any(row.plan_hash == plan["fingerprint"] and row.reviewed_by == source.reviewed_by
               for row in source.get("review_history") or []):
        frappe.throw(_("The approved engineering review record is missing."))
    source.flags.amf_reviewed_creation_plan = plan


def _new_bom(action, company, resolved):
    materials = []
    for source_row in action["materials"]:
        row = dict(source_row)
        if row["bom_no"].startswith("@new:"):
            code = row["bom_no"][5:]
            if not resolved.get(code):
                frappe.throw(_("Reviewed child BOM for {0} has not been created.").format(code))
            row["bom_no"] = resolved[code]
        materials.append(row)
    bom = frappe.get_doc(dict(doctype="BOM", item=action["item"]["item_code"], company=company,
        quantity=1, uom=action["item"].get("stock_uom", "Nos"), is_active=1, is_default=1,
        with_operations=0, rm_cost_as_per="Valuation Rate", items=materials,
        scrap_items=[dict(row) for row in action["scraps"]]))
    bom.insert(ignore_permissions=True)
    bom.submit()
    # Hooks must preserve the exact reviewed quantities, UOMs and child links.
    if (recipe_rows([row.as_dict() for row in bom.items]) != recipe_rows(materials)
            or recipe_rows([row.as_dict() for row in bom.scrap_items], scrap=True) != recipe_rows(action["scraps"], scrap=True)):
        frappe.throw(_("A BOM hook changed the reviewed recipe for {0}; the request was not completed.").format(bom.item))
    return bom.name


def execute_reviewed_plan(source):
    plan = source.flags.get("amf_reviewed_creation_plan")
    if not plan or plan["fingerprint"] != source.approved_plan_hash:
        frappe.throw(_("A freshly validated engineering plan is required for execution."))
    results, resolved = [], {}
    with families.atomic_family_creation(), families.family_creation((source.doctype, source.name), source.head_code[-3:]):
        for action in plan["actions"]:
            data = action["item"]
            code = data["item_code"]
            if action["item_action"] == "create":
                item = frappe.get_doc({"doctype": "Item", "default_material_request_type": "Manufacture",
                    "is_stock_item": 1, "has_batch_no": 1, **deepcopy(data)})
                item.insert(ignore_permissions=True)
                if item.name != code or any((item.get(field) or "") != (data.get(field) or "")
                        for field in ("item_name", "item_group", "reference_code", "stock_uom")):
                    frappe.throw(_("An Item hook changed the reviewed identity of {0}.").format(code))
            bom_name = action["existing_bom"] or ""
            if action["bom_action"] in ("create", "replace"):
                bom_name = _new_bom(action, source.company, resolved)
            resolved[code] = bom_name
            results.append(dict(item_code=code, item_action=action["item_action"], bom=bom_name,
                                bom_action=action["bom_action"], replaced_bom=action["existing_bom"] if action["bom_action"] == "replace" else ""))
    result = dict(plan_hash=plan["fingerprint"], reviewed_by=source.reviewed_by,
                  reviewed_at=str(source.reviewed_at), completed_at=str(now_datetime()), records=results)
    with workflow_write():
        source.review_status = "Created"
        source.creation_result = encode(result)
        frappe.db.set_value(source.doctype, source.name, dict(review_status="Created", creation_result=source.creation_result), update_modified=False)
    source.add_comment("Comment", _("Created/verified {0} Items using engineering review {1}.").format(len(results), plan["fingerprint"]))
    return result


def sync_item_creation_schema():
    """Targeted additive schema reload; does not run unrelated pending patches."""
    for doctype in ("item_creation_variant", "item_creation_review", "item_creation"):
        frappe.reload_doc("amf", "doctype", doctype, force=True)
    frappe.clear_cache(doctype="Item Creation")
