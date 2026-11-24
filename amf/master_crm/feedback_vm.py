"""Opt-in localhost tools for exercising the real feedback form in a VM."""
from urllib.parse import urlsplit

import frappe
from frappe.utils import cint

from amf.master_crm import feedback

VM_CUSTOMER = "AMF VM Satisfaction Test (LOCAL ONLY)"
VM_EMAIL = "vm-feedback@example.invalid"


def vm_request_allowed():
    request = getattr(frappe.local, "request", None)
    if not cint(frappe.conf.get("satisfaction_feedback_vm_enabled")) or not request:
        return False
    host = urlsplit("http://" + request.host).hostname
    return host in ("localhost", "127.0.0.1", "::1")


def get_vm_previews():
    """Read only the two explicitly configured test requests, never real tokens."""
    if not vm_request_allowed():
        raise frappe.DoesNotExistError
    configuration = frappe.conf.get("satisfaction_feedback_vm") or {}
    customer = configuration.get("customer")
    if not customer or frappe.db.get_value("Customer", customer, "customer_name") != VM_CUSTOMER:
        raise frappe.DoesNotExistError
    previews = []
    for source in ("SO", "Issue"):
        name = (configuration.get("requests") or {}).get(source)
        if not name or not frappe.db.exists(feedback.REQUEST_DOCTYPE, name):
            continue
        request = frappe.get_doc(feedback.REQUEST_DOCTYPE, name)
        expected_type = "Sales Order" if source == "SO" else "Issue"
        if request.customer != customer or request.source_doctype != expected_type:
            raise frappe.DoesNotExistError
        stars = feedback.stars_html(request)
        if source == "SO":
            doc = frappe.get_doc("Sales Order", request.source_name)
            template = frappe.get_doc("Email Template", "Sales Order")
            subject = frappe.render_template(template.subject, doc.as_dict())
            message = feedback._add_feedback(frappe.render_template(template.response, doc.as_dict()), request)
        else:
            subject = "[AMF] Your issue has been resolved – Please rate your experience"
            message = frappe.render_template("amf/templates/emails/issue_feedback.html", {
                "recipient_name": "VM Feedback Tester", "issue": request.source_name, "stars": stars,
            })
        previews.append({
            "kind": source, "source_doctype": expected_type, "source_name": request.source_name,
            "status": request.status, "survey": request.survey,
            "stars": stars, "subject": subject, "message": message,
        })
    return previews
