# -*- coding: utf-8 -*-
"""Idempotent setup; deliberately never sends mail or backfills requests."""
import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def sync_feedback_setup():
    # V12 previously cached this route without its misnamed controller. Refresh
    # route metadata as well as HTML when deploying the corrected controller.
    from frappe.website.utils import delete_page_cache
    delete_page_cache("satisfaction-feedback")
    meta = frappe.get_meta("Customer Satisfaction Survey")
    options = (meta.get_field("type_interaction").options or "").split("\n")
    for value in ("SO", "Issue"):
        if value not in options:
            options.append(value)
    setters = [
        ("type_interaction", "options", "\n".join(options), "Text"),
        ("comments", "label", "D-3. Are there any evolving needs or expectations you have for future interactions with AMF?", "Data"),
        ("amf_overall", "reqd", 1, "Check"),
        ("recommend", "reqd", 1, "Check"),
    ]
    for field, prop, value, kind in setters:
        if str(meta.get_field(field).get(prop) or "") != str(value):
            make_property_setter("Customer Satisfaction Survey", field, prop, value, kind)
    # Country inherits the system default in Frappe V12. The targeted browser
    # default resolver handles this without changing defaults for Address/Lead.
    if frappe.get_meta("Contact").has_field("country"):
        country = frappe.get_meta("Contact").get_field("country")
        if country.default:
            make_property_setter("Contact", "country", "default", "", "Data")
    # Replace the old onload workaround: it clears explicitly supplied values and
    # never runs for Quick Entry. The app's default resolver covers both flows.
    for script in frappe.get_all("Custom Script", filters={"dt": "Contact"}, fields=["name", "script"]):
        old = "frm.set_value('country', null);   // or '' works too"
        if old in (script.script or ""):
            doc = frappe.get_doc("Custom Script", script.name)
            doc.script = doc.script.replace(old, "// Country is left blank by the AMF default resolver.")
            doc.save(ignore_permissions=True)


def install_feedback_schema():
    frappe.reload_doc("master_crm", "doctype", "satisfaction_feedback_request", force=True)
    frappe.reload_doc("master_crm", "doctype", "customer_satisfaction_survey", force=True)
    sync_feedback_setup()
