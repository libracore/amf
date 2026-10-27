"""Immutable execution links and the request-only cancellation/amendment policy."""
import json

import frappe
from frappe import _
from frappe.utils import cint, escape_html, now_datetime


RESULT_FIELDS = ("item_code", "item_action", "bom", "bom_action", "replaced_bom", "completed_at")


def store_results(source, result):
    """Write searchable links in the owning transaction, preserving the JSON record."""
    from amf.amf.utils.item_creation_workflow import workflow_write

    if source.get("execution_results"):
        frappe.throw(_("Execution links already exist for this request."))
    records = result.get("records")
    if not isinstance(records, list):
        frappe.throw(_("The recorded execution result has no valid records table."))
    with workflow_write():
        for record in records:
            if (not isinstance(record, dict) or not record.get("item_code")
                    or record.get("item_action") not in ("create", "reuse")
                    or record.get("bom_action") not in ("create", "replace", "reuse", "none")):
                frappe.throw(_("The recorded execution result contains an invalid action."))
            values = {field: record.get(field) for field in RESULT_FIELDS}
            values["completed_at"] = result.get("completed_at")
            row = source.append("execution_results", values)
            row.docstatus = source.docstatus
            row.db_insert()


def backfill_result_links():
    """Index only recorded results; never reconstruct historical engineering decisions."""
    names = frappe.db.sql("""SELECT source.name FROM `tabItem Creation` source
        WHERE COALESCE(source.creation_result, '') != ''
        AND NOT EXISTS (SELECT 1 FROM `tabItem Creation Result` result
            WHERE result.parent = source.name AND result.parenttype = 'Item Creation'
            AND result.parentfield = 'execution_results') ORDER BY source.name""")
    for (name,) in names:
        source = frappe.get_doc("Item Creation", name)
        store_results(source, json.loads(source.creation_result))


def _amendment_source(doc):
    # Serialize sibling amendments before taking the family's allocation lock.
    frappe.db.sql("SELECT name FROM `tabItem Creation` WHERE name = %s FOR UPDATE", doc.amended_from)
    source = frappe.get_doc("Item Creation", doc.amended_from)
    source.check_permission("read")
    source.check_permission("amend")
    if source.docstatus != 2:
        frappe.throw(_("Only a cancelled Item Creation request can be amended."))
    other = frappe.db.sql("""SELECT name FROM `tabItem Creation`
        WHERE amended_from = %s AND name != %s AND docstatus < 2 LIMIT 1 FOR UPDATE""",
        (source.name, doc.name or ""))
    if other:
        frappe.throw(_("An active amendment already exists: {0}.").format(other[0][0]))
    return source


def prepare_amendment(doc):
    if not doc.get("amended_from"):
        return
    from amf.amf.doctype.item_creation.item_creation import populate_fields_from_existing_item

    source = _amendment_source(doc)
    selected_head = doc.get("head_item") if doc.get("head_check") == "No" else doc.get("head_code")
    if selected_head and selected_head != source.head_code:
        frappe.throw(_("An amendment must reuse its original head family. Use a new request for another head."))
    values = populate_fields_from_existing_item(source.head_code)
    doc.update(values)
    doc.head_check, doc.head_item = "No", source.head_code
    for group in ("plug", "seat"):
        doc.set(group + "_check", "No")
        doc.set(group + "_item", values[group + "_code"])
    # An amendment starts with a new approval, even when supplied by an API client.
    doc.review_status = "Draft"
    for field in ("approved_plan_hash", "approved_input_hash", "reviewed_by", "reviewed_at",
                  "creation_result", "cancellation_reason", "cancelled_by", "cancelled_at"):
        doc.set(field, None)
    doc.set("review_history", [])
    doc.set("execution_results", [])


def validate_amendment(doc):
    previous = doc.get_doc_before_save()
    if previous and (doc.get("amended_from") or "") != (previous.get("amended_from") or ""):
        frappe.throw(_("The amended request link cannot be changed after saving."))
    if doc.get("amended_from"):
        source = _amendment_source(doc)
        if not (doc.get("amendment_reason") or "").strip():
            frappe.throw(_("Enter the reason for this amendment."))
        if doc.head_check != "No" or doc.head_item != source.head_code:
            frappe.throw(_("An amendment must reuse its original head family. Use a new request for another head."))
    if any(doc.get(field) for field in ("cancellation_reason", "cancelled_by", "cancelled_at")):
        frappe.throw(_("Cancellation details can only be recorded when cancelling a submitted request."))


def before_cancel(doc):
    from amf.amf.utils.item_creation_plan import input_hash
    from amf.amf.utils.item_creation_workflow import protect_review_fields

    state = frappe.db.sql("SELECT docstatus FROM `tabItem Creation` WHERE name = %s FOR UPDATE", doc.name)
    if not state or cint(state[0][0]) != 1:
        frappe.throw(_("Only a currently submitted Item Creation request can be cancelled."))
    previous = doc.get_doc_before_save()
    protect_review_fields(doc)
    if (not previous or input_hash(doc) != input_hash(previous)
            or doc.get("amended_from") != previous.get("amended_from")):
        frappe.throw(_("The request definition cannot be changed while cancelling."))
    if not (doc.get("cancellation_reason") or "").strip():
        frappe.throw(_("Enter a cancellation reason. Generated Items and BOMs will be retained."))
    doc.cancellation_reason = doc.cancellation_reason.strip()
    doc.cancelled_by, doc.cancelled_at = frappe.session.user, now_datetime()
    doc.review_status = "Cancelled"


def on_cancel(doc):
    doc.add_comment("Comment", _("Request cancelled; generated Items, BOM revisions and suffix reservations retained. Reason: {0}").format(escape_html(doc.cancellation_reason)))


@frappe.whitelist(methods=["POST"])
def make_amendment(name, reason):
    source = frappe.get_doc("Item Creation", name)
    source.check_permission("read")
    source.check_permission("amend")
    amendment = frappe.copy_doc(source, ignore_no_copy=False)
    amendment.docstatus = 0
    amendment.amended_from = source.name
    amendment.amendment_reason = (reason or "").strip()
    amendment.insert()
    return amendment.name


def result_history(filters=None):
    """Return searchable result rows using the parent request's read permissions."""
    filters = frappe._dict(filters or {})
    for doctype in ("Item Creation", "Item", "BOM"):
        if not frappe.has_permission(doctype, "read"):
            frappe.throw(_("Read permission is required for {0}.").format(doctype), frappe.PermissionError)
    row_filters = dict(parenttype="Item Creation", parentfield="execution_results")
    if filters.item_code:
        frappe.get_doc("Item", filters.item_code).check_permission("read")
        row_filters["item_code"] = filters.item_code
    if filters.request:
        row_filters["parent"] = filters.request
    or_filters = None
    if filters.bom:
        frappe.get_doc("BOM", filters.bom).check_permission("read")
        or_filters = {"bom": filters.bom, "replaced_bom": filters.bom}
    rows = frappe.get_all("Item Creation Result", filters=row_filters, or_filters=or_filters,
        fields=["parent", "idx"] + list(RESULT_FIELDS), order_by="completed_at desc, parent desc, idx", limit_page_length=0)
    if not rows:
        return []
    parent_filters = {"name": ["in", sorted({row.parent for row in rows})]}
    if filters.status not in (None, "", "All"):
        states = {"Draft": 0, "Submitted": 1, "Cancelled": 2}
        if filters.status not in states:
            frappe.throw(_("Select a valid request status."))
        parent_filters["docstatus"] = states[filters.status]
    parents = {row.name: row for row in frappe.get_list("Item Creation", filters=parent_filters,
        fields=["name", "docstatus", "amended_from", "head_code", "reviewed_by", "reviewed_at"], limit_page_length=0)}
    result = []
    for row in rows:
        parent = parents.get(row.parent)
        if parent:
            result.append(dict(row, request=row.parent, status=("Draft", "Submitted", "Cancelled")[cint(parent.docstatus)],
                amended_from=parent.amended_from, head_code=parent.head_code,
                reviewed_by=parent.reviewed_by, reviewed_at=parent.reviewed_at))
    return result
