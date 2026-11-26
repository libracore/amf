# -*- coding: utf-8 -*-
"""Token protected feedback, shared by order confirmations and Issue closure."""
from __future__ import unicode_literals

import hashlib
import json
import re
import secrets
from email.utils import getaddresses
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cint, escape_html, get_formatted_email, get_url, nowdate

from amf.master_crm.email_templates import SALES_ORDER_TEMPLATE

REQUEST_DOCTYPE = "Satisfaction Feedback Request"
SALES_ORDER_TEMPLATES = (SALES_ORDER_TEMPLATE, "Sales Order")
THANK_YOU = ("Thank you for your feedback! We truly appreciate your input and look "
             "forward to continually improving our services.")
MARKER = "<!-- amf-satisfaction-feedback -->"


def request_name(doctype, name):
    return hashlib.sha256((doctype + ":" + name).encode("utf-8")).hexdigest()


def _lock_source(doctype, name):
    if doctype not in ("Sales Order", "Issue"):
        frappe.throw(_("Unsupported feedback source."))
    # Serialize email creation for this source, including two simultaneous clicks.
    return frappe.db.sql("SELECT name FROM `tab{0}` WHERE name=%s FOR UPDATE".format(doctype), name)


def _addresses(value):
    values = value if isinstance(value, list) else [value or ""]
    return [email.lower() for label, email in getaddresses(values) if email]


def source_context(doc, fallback_recipient=None):
    """Use the visible, canonical Issue party fields before legacy fields."""
    if doc.doctype == "Sales Order":
        customer = doc.get("customer")
        contact = doc.get("contact_person")
    else:
        selection = doc.get("input_selection")
        if selection and selection not in ("Customer", "Customer Issue"):
            return None
        customer = doc.get("customer_issue") or doc.get("customer")
        contact = doc.get("contact_new") or doc.get("raised_by_email") or doc.get("contact")
    if not customer:
        return None
    if contact and not frappe.db.exists("Contact", contact):
        contact = None
    recipient = (frappe.db.get_value("Contact", contact, "email_id") if contact else None)
    recipient = next((email for value in (recipient, doc.get("contact_email"), fallback_recipient, doc.get("raised_by"))
                      for email in _addresses(value) if frappe.utils.validate_email_address(email)), None)
    if not recipient:
        return None
    # Only infer a missing Contact when a unique email match belongs to this customer.
    if not contact:
        matches = frappe.db.sql("""
            SELECT DISTINCT c.name FROM `tabContact` c
            JOIN `tabDynamic Link` dl ON dl.parent=c.name AND dl.parenttype='Contact'
            LEFT JOIN `tabContact Email` ce ON ce.parent=c.name
            WHERE dl.link_doctype='Customer' AND dl.link_name=%s
              AND (LOWER(c.email_id)=%s OR LOWER(ce.email_id)=%s)
        """, (customer, recipient, recipient))
        if len(matches) == 1:
            contact = matches[0][0]
    return {"customer": customer, "contact_person": contact, "recipient": recipient}


def _get_or_create_request(doc, context):
    name = request_name(doc.doctype, doc.name)
    if frappe.db.exists(REQUEST_DOCTYPE, name):
        request = frappe.get_doc(REQUEST_DOCTYPE, name)
        if request.status == "Prepared":
            request.db_set(context)
        return request
    return frappe.get_doc(dict({
        "doctype": REQUEST_DOCTYPE, "name": name,
        "source_doctype": doc.doctype, "source_name": doc.name,
        "token": secrets.token_urlsafe(32), "status": "Prepared",
    }, **context)).insert(ignore_permissions=True)


def stars_html(request):
    links = []
    for rating in range(1, 6):
        path = "/satisfaction-feedback?" + urlencode({"token": request.token, "rating": rating})
        base_url = frappe.conf.get("satisfaction_feedback_base_url")
        url = base_url.rstrip("/") + path if base_url else get_url(path)
        links.append('<a href="{0}" title="{1} {2}" aria-label="{1} {2}" '
                     'style="color:#b77900;font-size:32px;text-decoration:none;padding:0 5px">'
                     '&#9733;</a>'.format(escape_html(url), rating, _("out of 5 stars")))
    return ('<div style="margin:16px 0">' + "".join(links) +
            '<p style="font-size:13px">1 star = very dissatisfied; 5 stars = very satisfied.</p>'
            '<p>Simply click the star that best represents your satisfaction.</p></div>')


def _add_feedback(content, request):
    content = content or ""
    # The composer may have rendered the stars already. Quill strips HTML
    # comments, so detect the tokenized links rather than relying on the marker.
    if _has_feedback_links(content, request):
        return content
    block = (MARKER + '<p>We value your feedback and want to make sure your experience meets '
             'your expectations. We’d be grateful if you could take a moment to rate your '
             'experience so far with AMF:</p>' + stars_html(request))
    # Preserve the administrator's confirmation wording and signature.
    match = re.search(r"<(?:p|div)[^>]*>(?:We remain at your disposal|If you have any questions about your order)",
                      content, flags=re.I)
    return content[:match.start()] + block + content[match.start():] if match else content + block


def _has_feedback_links(content, request):
    return bool(content and "/satisfaction-feedback?" in content and "token=" + request.token in content)


def can_send_issue_feedback(request):
    if request.status == "Prepared":
        return True
    if request.status != "Queued" or request.communication or request.survey:
        return False

    # The VM activates its demo link before composing an email.
    from amf.master_crm.feedback_vm import VM_EMAIL, vm_request_allowed

    configuration = frappe.conf.get("satisfaction_feedback_vm") or {}
    return (request.name == (configuration.get("requests") or {}).get("Issue")
            and request.recipient == VM_EMAIL and vm_request_allowed())


@frappe.whitelist(methods=["POST"])
def get_email_template(template_name, doc):
    """Render feedback links when a supported template is selected in Desk."""
    from frappe.email.doctype.email_template.email_template import get_email_template as original
    from amf.master_crm.issue_closure import ISSUE_CLOSURE_TEMPLATES, get_closure_email

    data = json.loads(doc) if isinstance(doc, str) else doc
    if template_name in ISSUE_CLOSURE_TEMPLATES:
        if data.get("doctype") != "Issue" or not data.get("name") or data.get("__islocal"):
            frappe.throw(_("Use the Issue Closure email template from a saved Issue."))
        return get_closure_email(data["name"], template_name)
    result = original(template_name, data)
    if template_name not in SALES_ORDER_TEMPLATES or data.get("doctype") != "Sales Order":
        return result
    name = data.get("name")
    if not name or not frappe.db.exists("Sales Order", name):
        return result
    if not frappe.has_permission("Sales Order", "email", name):
        raise frappe.PermissionError
    _lock_source("Sales Order", name)
    source = frappe.get_doc("Sales Order", name)
    context = source_context(source)
    if source.docstatus == 1 and context:
        request = _get_or_create_request(source, context)
        result["message"] = _add_feedback(result["message"], request)
    return result


@frappe.whitelist(methods=["POST"])
def make_communication(**kwargs):
    """Keep V12's composer API; queue feedback emails atomically with their request.

    The stock make() commits before enqueueing its worker. This targeted path
    keeps the Communication, request and Email Queue in the same transaction.
    All other email operations continue through the stock implementation.
    """
    from frappe.core.doctype.communication.email import make
    from amf.master_crm.issue_closure import ISSUE_CLOSURE_TEMPLATES, issue_party

    args = frappe.get_newargs(make, kwargs)
    if not (cint(args.get("send_email")) and args.get("sent_or_received", "Sent") == "Sent"
            and args.get("communication_medium", "Email") == "Email"):
        return make(**args)
    doctype = args.get("doctype")
    name = args.get("name")
    order_confirmation = doctype == "Sales Order" and args.get("email_template") in SALES_ORDER_TEMPLATES
    issue_closure = doctype == "Issue" and args.get("email_template") in ISSUE_CLOSURE_TEMPLATES
    issue_feedback = doctype == "Issue" and "/satisfaction-feedback?" in (args.get("content") or "")
    if not name or not (order_confirmation or issue_closure or issue_feedback):
        return make(**args)
    if not frappe.has_permission(doctype, "email", name):
        raise frappe.PermissionError
    _lock_source(doctype, name)
    doc = frappe.get_doc(doctype, name)
    if issue_closure and doc.status != "Closed":
        frappe.throw(_("Close and save the Issue before sending a closure email."))

    to_addresses = _addresses(args.get("recipients"))
    if issue_feedback:
        request_id = request_name(doctype, name)
        if not frappe.db.exists(REQUEST_DOCTYPE, request_id):
            return make(**args)
        request = frappe.get_doc(REQUEST_DOCTYPE, request_id)
        if not _has_feedback_links(args["content"], request):
            return make(**args)
        if request.communication:
            return {"name": request.communication, "emails_not_sent_to": None}
        if (doc.status != "Closed" or not can_send_issue_feedback(request) or not to_addresses
                or issue_party(doc) != ("Customer", request.customer)):
            frappe.throw(_("Open a new closure email draft for this Issue before sending."))
        request.db_set("recipient", to_addresses[0])
        return _queue_feedback_communication(doc, request, args, args["content"])

    if not order_confirmation or doc.docstatus != 1 or not to_addresses:
        return make(**args)
    context = source_context(doc, fallback_recipient=to_addresses[0])
    if not context:
        return make(**args)
    # Keep the source's Contact attribution, while recording the actual addressee
    # when the user sends the confirmation to a purchasing team/alias instead.
    if context["recipient"] not in to_addresses:
        context["recipient"] = to_addresses[0]
    request = _get_or_create_request(doc, context)
    if request.communication:
        return {"name": request.communication, "emails_not_sent_to": None}
    return _queue_feedback_communication(doc, request, args, _add_feedback(args.get("content"), request))


def _queue_feedback_communication(doc, request, args, content):
    from frappe.core.doctype.communication.email import add_attachments
    from frappe.email.email_body import get_message_id

    sender = args.get("sender")
    accounts = frappe.get_all("Email Account", filters={"email_id": sender},
                             fields=["always_use_account_email_id_as_sender"]) if sender else []
    if accounts and not cint(accounts[0].always_use_account_email_id_as_sender):
        sender = None
    sender = sender or get_formatted_email(frappe.session.user)
    recipients = args.get("recipients")
    if isinstance(recipients, list):
        recipients = ", ".join(recipients)
    attachments = args.get("attachments") or []
    if isinstance(attachments, str):
        attachments = json.loads(attachments)
    comm = frappe.get_doc({
        "doctype": "Communication", "subject": args.get("subject"),
        "content": content,
        "sender": sender, "sender_full_name": args.get("sender_full_name"),
        "recipients": recipients, "cc": args.get("cc"), "bcc": args.get("bcc"),
        "communication_medium": "Email", "sent_or_received": "Sent",
        "reference_doctype": doc.doctype, "reference_name": doc.name,
        "email_template": args.get("email_template"), "message_id": get_message_id().strip(" <>"),
        "read_receipt": args.get("read_receipt"), "has_attachment": int(bool(attachments)),
    }).insert(ignore_permissions=True)
    add_attachments(comm.name, attachments)
    request.db_set({"communication": comm.name, "status": "Queued"})
    frappe.flags.print_letterhead = cint(args.get("print_letterhead", True))
    cc = _addresses(args.get("cc"))
    if cint(args.get("send_me_a_copy")):
        cc.extend(_addresses(sender))
    # Build and queue now, while retaining the composer's print/PDF attachments.
    # SMTP remains asynchronous via the ordinary Email Queue scheduler.
    comm._notify(print_html=args.get("print_html"), print_format=args.get("print_format"),
                 attachments=attachments, recipients=_addresses(recipients), cc=cc,
                 bcc=_addresses(args.get("bcc")))
    if not frappe.db.exists("Email Queue", {"communication": comm.name}):
        frappe.throw(_("The email could not be queued. Please check the recipient's email settings."))
    return {"name": comm.name, "emails_not_sent_to": None}


def get_request(token, for_update=False):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        frappe.throw(_("This feedback link is invalid or no longer available."), frappe.PermissionError)
    rows = frappe.db.sql("""SELECT name FROM `tabSatisfaction Feedback Request`
        WHERE token=%s AND status IN ('Queued', 'Responded') {0}""".format(
            "FOR UPDATE" if for_update else ""), token)
    if not rows:
        frappe.throw(_("This feedback link is invalid or no longer available."), frappe.PermissionError)
    return frappe.get_doc(REQUEST_DOCTYPE, rows[0][0])


def _rating(value, low, high, label):
    # Select values arrive as strings; reject fractions, booleans and coercion.
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,2}", str(value)):
        frappe.throw(_("Please select a valid {0}.").format(label))
    number = int(value)
    if not low <= number <= high:
        frappe.throw(_("Please select a valid {0}.").format(label))
    return number


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit_feedback(token, satisfaction=None, recommendation=None, comment=None):
    request = get_request(token, for_update=True)
    if request.survey:
        # Idempotent: do not disclose internal names, or change an earlier response.
        return {"message": THANK_YOU}
    satisfaction = _rating(satisfaction, 1, 5, _("satisfaction rating"))
    recommendation = _rating(recommendation, 0, 10, _("recommendation rating"))
    if comment is not None and not isinstance(comment, str):
        frappe.throw(_("Please enter a text comment."))
    comment = (comment or "").strip()
    if len(comment) > 10000:
        frappe.throw(_("Please limit your comment to 10,000 characters."))
    survey = frappe.get_doc({
        "doctype": "Customer Satisfaction Survey", "date_interaction": nowdate(),
        "type_interaction": "SO" if request.source_doctype == "Sales Order" else "Issue",
        "customer": request.customer, "contact_person": request.contact_person,
        "amf_overall": satisfaction, "recommend": str(recommendation),
        "comments": escape_html(comment).replace("\n", "<br>"),
        "feedback_request": request.name, "source_doctype": request.source_doctype,
        "source_name": request.source_name,
    })
    survey.flags.ignore_permissions = True
    survey.insert()
    survey.submit()
    request.db_set({"survey": survey.name, "status": "Responded"})
    return {"message": THANK_YOU}
