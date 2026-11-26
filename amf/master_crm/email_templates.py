"""Install the editable Sales Order confirmation and Issue closure templates."""
from hashlib import sha256
from pathlib import Path

import frappe

SALES_ORDER_TEMPLATE = "AMF Sales Order Confirmation"
ISSUE_CLOSURE_TEMPLATE = "AMF Issue Closure"


def install_email_templates():
    if not frappe.db.exists("Email Template", SALES_ORDER_TEMPLATE):
        original = frappe.db.exists("Email Template", "Sales Order")
        order = frappe.copy_doc(frappe.get_doc("Email Template", original)) if original else frappe.new_doc("Email Template")
        order.update({
            "name": SALES_ORDER_TEMPLATE,
            "owner": frappe.session.user,
            "subject": "Order confirmation {{ name }}{% if po_no %} | PO {{ po_no }}{% endif %} | Advanced Microfluidics",
            "response": _body("sales_order_confirmation.html"),
        })
        order.insert(ignore_permissions=True)

    if not frappe.db.exists("Email Template", ISSUE_CLOSURE_TEMPLATE):
        frappe.get_doc({
            "doctype": "Email Template",
            "name": ISSUE_CLOSURE_TEMPLATE,
            "owner": frappe.session.user,
            "subject": "[AMF] Issue {{ issue }} {% if is_supplier %}closed{% else %}resolved{% endif %}",
            "response": _body("issue_closure.html"),
        }).insert(ignore_permissions=True)


def update_default_email_spacing():
    previous = (
        (SALES_ORDER_TEMPLATE, "sales_order_confirmation.html",
         "935106323e76bd2cd85ae94266e77afdc1d55362e0597741f619cf00eae87f00"),
        (ISSUE_CLOSURE_TEMPLATE, "issue_closure.html",
         "952c1b0e48350b3209d6c2b53ddddc7e09d5014f73823d548c096e200076ff3a"),
    )
    for name, filename, previous_hash in previous:
        if not frappe.db.exists("Email Template", name):
            continue
        template = frappe.get_doc("Email Template", name)
        if sha256((template.response or "").strip().encode()).hexdigest() == previous_hash:
            template.response = _body(filename)
            template.save(ignore_permissions=True)


def _body(filename):
    return Path(frappe.get_app_path("amf", "templates", "emails", filename)).read_text(encoding="utf-8")
