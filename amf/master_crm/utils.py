# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe 
from frappe.utils import get_url_to_form
from frappe.model.mapper import get_mapped_doc
from datetime import datetime
from frappe import _

@frappe.whitelist()
def update_status(contact, status):
    if frappe.db.exists("Contact", contact):
        contact_doc = frappe.get_doc("Contact", contact)
        # catch invalid (or useless) transitions
        if status == "Lead":
            if contact_doc.status in ['Lead', 'Prospect', 'Customer']:
                # invalid transition
                return
        elif status == "Prospect":
            if contact_doc.status in ['Prospect', 'Customer']:
                # invalid transition
                return
        elif status == "Customer":
            if contact_doc.status in ['Customer']:
                # invalid transition
                return
                
        # perform transition
        frappe.db.set_value("Contact", contact, 'status', status);
        frappe.db.commit()
    return

@frappe.whitelist()
def update_last_po(contact):
    if frappe.db.exists("Contact", contact):
        contact_doc = frappe.get_doc("Contact", contact)
        contact_doc.last_po = datetime.today().date()
        contact_doc.save()
        frappe.db.commit()
    return
    
@frappe.whitelist()
def make_customer(company_name, customer_group, territory):
    if frappe.db.exists("Customer", company_name):
        customer = frappe.get_doc("Customer", company_name)
        return customer
    else:
        customer = frappe.get_doc({
            'doctype': 'Customer',
            'customer_type': "Company",
            'customer_name': company_name,
            'customer_group': customer_group,
            'territory': territory
        })
        customer.flags.ignore_mandatory = True
        customer.insert()
        frappe.db.commit()
        return customer
        
@frappe.whitelist()
def make_quotation(contact_name):
    doc = get_mapped_doc(
        "Contact", 
        contact_name, 
        {"Contact": { "doctype": "Quotation"}}
    )
    
    contact = frappe.get_doc('Contact', contact_name)
    if len(contact.links) != 1:
        frappe.log_error(f"WARNING: Contact.links has length {len(contact.links)} != 1 for Contact {contact_name} and Quotation {doc.name}. "
                         f"Took contact.links[0].link_name for Quotation.party_name but might be wrong. Please check Contact {contact_name} "
                         f"and Quotation {doc.name}.", 'microsynth.quotation.make_quotation')

    doc.party_name = contact.links[0].link_name
    doc.contact_person = contact_name
    customer = frappe.get_doc("Customer", doc.party_name)
    doc.territory = customer.territory
    doc.currency = customer.default_currency
    doc.selling_price_list = customer.default_price_list
    return doc

@frappe.whitelist()
def link_contact_to_customer(contact, customer):
    if not frappe.db.exists("Contact", contact):
        frappe.throw( _("Contact {0} not found.").format(contact))
    if not frappe.db.exists("Customer", customer):
        frappe.throw( _("Customer {0} not found.").format(customer))
        
    contact_doc = frappe.get_doc("Contact", contact)
    contact_doc.append("links", {
        'link_doctype': "Customer",
        'link_name': customer
    })
    contact_doc.save()
    frappe.db.commit()
    return

@frappe.whitelist()
def get_referring_contacts(customer):
    """
    Return a list of Contact names linked via the Dynamic Link table
    to the given Customer (customer = referring_organization).
    """
    if not customer:
        return []

    contacts = frappe.db.sql(
        """
        SELECT c.name
        FROM `tabContact` AS c
        INNER JOIN `tabDynamic Link` AS dl
          ON dl.parent       = c.name
         AND dl.parenttype   = 'Contact'
         AND dl.parentfield  = 'links'
        WHERE dl.link_doctype = 'Customer'
          AND dl.link_name    = %s
        """,
        (customer,),
        as_dict=True,
    )

    # return list of names
    return [r.name for r in contacts]

@frappe.whitelist()
def calculate_csat_average():
    """
    For each Customer, find all linked Contacts, average their 'csat' scores,
    and store the result in Customer.csat_average.
    """
    # 1. Get all customer names
    customers = frappe.get_all("Customer", fields=["name"])

    for cust in customers:
        # 2. Pull average CSAT for this customer via SQL join with Dynamic Link
        avg = frappe.db.sql("""
            SELECT
                    AVG(c.customer_satisfaction_survey) AS avg_csat            
                FROM
                    `tabDynamic Link` dl
                JOIN
                    `tabContact` c ON c.name = dl.parent
                WHERE
                    dl.parenttype = 'Contact'
                    AND dl.link_name = %s
                    AND c.customer_satisfaction_survey IS NOT NULL
                    AND c.customer_satisfaction_survey > 0
        """, (cust.name,), as_dict=1)

        # 3. Extract the computed average (or default to 0 if none)
        avg_csat = avg[0].avg_csat if avg and avg[0].avg_csat is not None else 0.0

        # 4. Update the customer record
        frappe.db.set_value(
            "Customer",
            cust.name,
            "csat_average",
            avg_csat
        )
        print("value set for",cust.name)

    # Persist all updates in one go
    frappe.db.commit()
