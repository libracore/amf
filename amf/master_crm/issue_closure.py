"""Offer an editable external email after an Issue is saved as Closed."""
import json

import frappe
from frappe import _
from frappe.contacts.doctype.contact.contact import get_default_contact
from frappe.utils import validate_email_address

from amf.master_crm import feedback
from amf.master_crm.email_templates import ISSUE_CLOSURE_TEMPLATE

LEGACY_ISSUE_CLOSURE_TEMPLATE = "Issue Closure"
ISSUE_CLOSURE_TEMPLATES = (ISSUE_CLOSURE_TEMPLATE, LEGACY_ISSUE_CLOSURE_TEMPLATE)
DEFAULT_SUBJECT = (
    "[AMF] Issue {{ issue }} {% if is_supplier %}closed{% else %}resolved{% endif %}"
    "{% if stars %} – Please rate your experience{% endif %}"
)


def install_closure_email_template():
    """Install the original closure template for legacy users and references."""
    if frappe.db.exists("Email Template", LEGACY_ISSUE_CLOSURE_TEMPLATE):
        return
    with open(frappe.get_app_path("amf", "templates", "emails", "issue_feedback.html"), encoding="utf-8") as body:
        frappe.get_doc({
            "doctype": "Email Template",
            "name": LEGACY_ISSUE_CLOSURE_TEMPLATE,
            "owner": frappe.session.user,
            "subject": DEFAULT_SUBJECT,
            "response": body.read(),
        }).insert(ignore_permissions=True)


def render_closure_email(issue, recipient_name, stars=None, is_supplier=False,
                         template_name=ISSUE_CLOSURE_TEMPLATE):
    from frappe.email.doctype.email_template.email_template import get_email_template

    context = dict(issue, issue=issue["name"], recipient_name=recipient_name,
                   stars=stars, is_supplier=is_supplier)
    return get_email_template(template_name, context)


def issue_party(doc):
    selection = doc.get("input_selection")
    if selection in ("Supplier", "Supplier Issue"):
        return "Supplier", doc.get("supplier")
    if not selection or selection in ("Customer", "Customer Issue"):
        return "Customer", doc.get("customer_issue") or doc.get("customer")
    return None, None


def closure_email_party(doc):
    party_type, party = issue_party(doc)
    if doc.status == "Closed" and party and doc.has_permission("email"):
        return party_type


def set_closure_email_offer(doc, method=None):
    # The form save endpoint runs onload on the same saved Document instance.
    # A normal form load has no prior document and therefore shows no prompt.
    previous = doc.get_doc_before_save()
    if previous and previous.status != "Closed":
        party_type = closure_email_party(doc)
        if party_type:
            doc.set_onload("closure_email_party", party_type)


def _default_party_contact(party_type, party):
    contact = get_default_contact(party_type, party)
    if contact:
        return frappe.db.get_value("Contact", contact, ["email_id", "full_name"], as_dict=True) or {}
    return {}


@frappe.whitelist(methods=["POST"])
def get_closure_email(name, template_name=ISSUE_CLOSURE_TEMPLATE):
    if template_name not in ISSUE_CLOSURE_TEMPLATES:
        frappe.throw(_("Select an Issue closure email template."))
    doc = frappe.get_doc("Issue", name)
    doc.check_permission("email")
    feedback._lock_source("Issue", name)
    doc.reload()
    party_type, party = issue_party(doc)

    recipient = None
    recipient_name = None
    stars = None
    if party_type == "Customer" and party:
        context = feedback.source_context(doc)
        if context and not (context.get("contact_person") or doc.get("contact_email")):
            # ERPNext defaults Raised By to the current employee on Desk Issues.
            if frappe.db.exists("User", {"email": context["recipient"], "user_type": "System User"}):
                context = None
        if not context:
            contact = _default_party_contact(party_type, party)
            if validate_email_address(contact.get("email_id")):
                context = feedback.source_context(doc, fallback_recipient=contact["email_id"])
        recipient = context["recipient"] if context else None
        if context and context.get("contact_person"):
            recipient_name = frappe.db.get_value("Contact", context["contact_person"], "full_name")
        if context and doc.status == "Closed":
            request = feedback._get_or_create_request(doc, context)
            if feedback.can_send_issue_feedback(request):
                stars = feedback.stars_html(request)
    elif party_type == "Supplier" and party:
        recipient = next((email for email in feedback._addresses(doc.get("raised_by_supplier_email"))
                          if validate_email_address(email)), None)
        if not recipient:
            contact = _default_party_contact(party_type, party)
            recipient = validate_email_address(contact.get("email_id")) or None
            recipient_name = contact.get("full_name")

    if party and not recipient_name:
        recipient_name = frappe.db.get_value(party_type, party, party_type.lower() + "_name")
    draft = render_closure_email(doc.as_dict(), recipient_name or party or _("team"), stars,
                                 party_type == "Supplier", template_name)
    draft.update(recipient=recipient, email_template=template_name)
    return draft


@frappe.whitelist(methods=["POST"])
def close_from_list(names):
    """Keep ERPNext's save behavior and tell Desk which closures offer email."""
    offers = []
    for name in json.loads(names) if isinstance(names, str) else names:
        doc = frappe.get_doc("Issue", name)
        was_closed = doc.status == "Closed"
        doc.status = "Closed"
        doc.save()
        party_type = closure_email_party(doc)
        if not was_closed and party_type:
            offers.append({"name": doc.name, "party_type": party_type})
    return offers


def disable_automatic_closure_notification():
    name = "Issue Closed"
    filters = {"name": name, "document_type": "Issue", "channel": "Email", "enabled": 1}
    if frappe.db.exists("Notification", filters):
        frappe.db.set_value("Notification", name, "enabled", 0)
    frappe.cache().hdel("notifications", "Issue")
