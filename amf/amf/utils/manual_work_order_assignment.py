# -*- coding: utf-8 -*-
"""Assign new, manually registered machining Work Orders using Frappe V12.

See amf/docs/manual_machining_work_order_assignment.md for scope and rollback.
This is an after_insert hook, not a remotely callable or scheduled method.
"""

from __future__ import unicode_literals

import json
import re
from html import escape

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.utils import cint, cstr


MACHINING_ASSIGNEE = "martin.barraud@amf.ch"
DESK_SAVE_COMMAND = "frappe.desk.form.save.savedocs"
MANUAL_CREATION_COMMANDS = frozenset((
    "amf.amf.utils.work_order_creation.make_work_orders",
    "amf.amf.utils.work_order_creation.create_work_orders",
    "erpnext.selling.doctype.sales_order.sales_order.make_work_orders",
    "amf.www.planification.planification.start_planning",
))
DOCUMENT_METHOD_COMMANDS = frozenset((
    "runserverobj", "frappe.handler.runserverobj",
    "frappe.desk.form.run_method.runserverobj",
))


def assign_manual_machining_work_order(doc, method=None):
    """Add Martin's assignment once, after the new Work Order has been saved.

    Native assignment preserves other assignees, updates the Work Order sidebar,
    adds an assignment comment and queues the standard assignment email. It uses
    ToDo.owner (the V12 assignee field). No explicit commit or immediate email.
    """
    if not cint(frappe.conf.get("manual_machining_work_order_alerts_enabled", 1)):
        return
    if doc.doctype != "Work Order" or not re.fullmatch(
        r"(10|20)[0-9A-Z]{4}", cstr(doc.get("production_item"))
    ):
        return
    if not _is_manual_creation(doc):
        return

    # Any previous assignment, including a closed/cancelled one, prevents replay
    # from recreating a task that Martin or another user has already handled.
    if frappe.db.exists("ToDo", {
        "reference_type": "Work Order",
        "reference_name": doc.name,
        "owner": MACHINING_ASSIGNEE,
    }):
        return
    if not frappe.db.exists("User", {
        "name": MACHINING_ASSIGNEE, "enabled": 1, "user_type": "System User",
    }):
        frappe.throw(_("Cannot assign the new machining Work Order: {0} must be an enabled System User.").format(MACHINING_ASSIGNEE))

    description = _(
        "Please review and plan machining for new manual Work Order {0}. "
        "Item: {1}. Quantity: {2}. Created by: {3}."
    ).format(*(escape(cstr(value)) for value in (
        doc.name, doc.production_item, doc.qty, doc.owner or frappe.session.user,
    )))
    assign_to.add({
        "assign_to": MACHINING_ASSIGNEE,
        "doctype": "Work Order",
        "name": doc.name,
        "description": description,
        "priority": "Medium",
        "notify": 1,
    })
    # Native ToDo writes _assign directly in the database. Reload so the first
    # Desk-save response also shows Martin, without another Work Order save.
    doc.reload()


def _is_manual_creation(doc):
    """Recognize actual manual UI entry points, rather than guessing from owner.

    Both schedulers run as Administrator and some legacy automatic WOs lack an
    auto_gen marker. Conversely, duplicating a planner draft in Desk can retain
    that marker. The request's creation action distinguishes those cases.
    Unknown API/integration commands are deliberately excluded.
    """
    if any(frappe.flags.get(flag) or doc.flags.get(flag) for flag in (
        "in_import", "in_patch", "in_install", "in_migrate",
    )):
        return False
    if frappe.session.user in (None, "", "Guest"):
        return False

    command = frappe.form_dict.get("cmd")
    if command in MANUAL_CREATION_COMMANDS:
        return True
    if command in DOCUMENT_METHOD_COMMANDS and frappe.form_dict.get("method") == "make_work_order":
        return _request_document("docs").get("doctype") == "Production Plan"
    if command != DESK_SAVE_COMMAND:
        return False

    requested_doc = _request_document("doc")
    return (
        requested_doc.get("doctype") == "Work Order"
        and requested_doc.get("production_item") == doc.production_item
    )


def _request_document(fieldname):
    requested_doc = frappe.form_dict.get(fieldname)
    if isinstance(requested_doc, str):
        try:
            requested_doc = json.loads(requested_doc)
        except (TypeError, ValueError):
            return {}
    return requested_doc if isinstance(requested_doc, dict) else {}
