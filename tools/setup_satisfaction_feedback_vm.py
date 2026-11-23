#!/usr/bin/env python3
"""Prepare localhost feedback testing with dedicated VM fixtures and muted SMTP."""
import argparse
import json
import secrets
from pathlib import Path

import frappe
from frappe.installer import update_site_config
from frappe.utils import add_days, nowdate

from amf.master_crm import feedback
from amf.master_crm.feedback_vm import VM_CUSTOMER, VM_EMAIL
from amf.amf.utils.issue_classification import OTHER_ISSUE_TYPE

KEYS = ("satisfaction_feedback_base_url", "mute_emails", "satisfaction_feedback_vm_enabled", "satisfaction_feedback_vm")


def restore(configuration):
    for key in KEYS:
        update_site_config(key, configuration.get(key) if configuration.get(key) is not None else "None")


def make_party():
    customer = frappe.db.get_value("Customer", {"customer_name": VM_CUSTOMER}, "name")
    if not customer:
        groups = frappe.get_all("Customer Group", filters={"is_group": 0}, fields=["name"])
        territories = frappe.get_all("Territory", filters={"is_group": 0}, fields=["name"])
        customer = frappe.get_doc({
            "doctype": "Customer", "customer_name": VM_CUSTOMER, "customer_type": "Company", "priority": 1,
            "customer_group": "Dummy Group" if frappe.db.exists("Customer Group", "Dummy Group") else groups[0].name,
            "territory": "Switzerland" if frappe.db.exists("Territory", "Switzerland") else territories[0].name,
        }).insert(ignore_permissions=True).name
    contact = frappe.db.get_value("Contact", {"email_id": VM_EMAIL}, "name")
    if not contact:
        contact = frappe.get_doc({
            "doctype": "Contact", "first_name": "VM Feedback", "last_name": "Tester", "country": "",
            "image": "/assets/amf/images/branding/amf-logo-tagline.svg", "status": "Lead",
            "email_ids": [{"email_id": VM_EMAIL, "is_primary": 1}],
            "links": [{"link_doctype": "Customer", "link_name": customer}],
        }).insert(ignore_permissions=True).name
    return customer, contact


def make_sources(customer, contact):
    company_name = "Advanced Microfluidics SA" if frappe.db.exists("Company", "Advanced Microfluidics SA") else frappe.get_all("Company", fields=["name"])[0].name
    company = frappe.get_doc("Company", company_name)
    items = frappe.get_all("Item", filters={"disabled": 0, "is_sales_item": 1, "is_stock_item": 0}, fields=["name", "stock_uom"], limit_page_length=1)
    if not items:
        raise RuntimeError("A non-stock sales item is needed for the VM Sales Order fixture.")
    prices = frappe.get_all("Price List", filters={"enabled": 1, "selling": 1, "currency": company.default_currency}, fields=["name", "currency"], limit_page_length=1)
    if not prices:
        raise RuntimeError("A selling price list in the company currency is needed for the VM fixture.")
    item = items[0]
    round_id = secrets.token_hex(3).upper()
    order = frappe.get_doc({
        "doctype": "Sales Order", "naming_series": "SO-", "customer": customer, "contact_person": contact,
        "company": company_name, "order_type": "Sales", "sales_order_type": "SAV", "transaction_date": nowdate(),
        "delivery_date": add_days(nowdate(), 7), "currency": company.default_currency, "conversion_rate": 1,
        "selling_price_list": prices[0].name, "price_list_currency": prices[0].currency, "plc_conversion_rate": 1,
        "po_no": "VM-FEEDBACK-" + round_id, "ignore_pricing_rule": 1,
        "items": [{"item_code": item.name, "qty": 1, "uom": item.stock_uom, "conversion_factor": 1,
                   "rate": 0, "delivery_date": add_days(nowdate(), 7), "description": "VM feedback test — no physical shipment"}],
    }).insert(ignore_permissions=True)
    order.flags.ignore_permissions = True
    order.submit()
    types = frappe.get_all("Issue Type", filters={"is_active": 1, "name": ["like", "%Feedback%"]}, fields=["name"], limit_page_length=1)
    if not types:
        types = frappe.get_all("Issue Type", filters={"is_active": 1, "name": ["!=", OTHER_ISSUE_TYPE]}, fields=["name"], limit_page_length=1)
    if not types:
        raise RuntimeError("An active, predefined Issue Type is needed for the VM fixture.")
    issue = frappe.get_doc({
        "doctype": "Issue", "subject": "VM Satisfaction Feedback Test " + round_id, "status": "Open",
        "input_selection": "Customer Issue", "customer": customer, "customer_issue": customer,
        "contact_new": contact, "raised_by_email": contact, "contact_email": VM_EMAIL,
        "raised_by": VM_EMAIL, "issue_type": types[0].name, "urgency": "Low", "impact": "Low",
    }).insert(ignore_permissions=True)
    requests = {}
    for source, doc in (("SO", order), ("Issue", issue)):
        request = feedback._get_or_create_request(doc, feedback.source_context(doc))
        # Activate a locally generated test link without constructing/sending mail.
        request.db_set("status", "Queued")
        requests[source] = request.name
    return {"customer": customer, "contact": contact, "requests": requests}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--new-round", action="store_true")
    mode.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    bench = Path(__file__).resolve().parents[3]
    frappe.init(site=args.site, sites_path=str(bench / "sites"))
    frappe.connect()
    frappe.set_user("Administrator")
    backup = Path(frappe.get_site_path("private", "feedback-vm-settings-before.json"))
    try:
        if args.disable:
            if not backup.exists():
                raise RuntimeError("No saved pre-VM configuration exists.")
            restore(json.loads(backup.read_text()))
            frappe.clear_cache()
            print("VM feedback mode disabled; previous URL/mail settings restored. Test records retained.")
            return
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(json.dumps({key: frappe.conf.get(key) for key in KEYS}, indent=2))
        configuration = frappe.conf.get("satisfaction_feedback_vm") or {}
        if args.new_round or not configuration.get("requests"):
            frappe.flags.mute_emails = True
            frappe.flags.in_patch = True  # Do not dispatch fixture-created notifications.
            customer, contact = make_party()
            configuration = make_sources(customer, contact)
            frappe.db.commit()
        update_site_config("satisfaction_feedback_base_url", "http://localhost:8000")
        update_site_config("mute_emails", 1)
        update_site_config("satisfaction_feedback_vm", configuration)
        update_site_config("satisfaction_feedback_vm_enabled", 1)
        frappe.clear_cache()
        print("VM feedback testing ready: http://localhost:8000/satisfaction-feedback-vm")
        print("Feedback links use localhost:8000. SMTP delivery is muted on this VM.")
        print("Submitting the form saves real surveys linked only to the dedicated VM test party.")
    except Exception:
        frappe.db.rollback()
        raise
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    main()
