# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe 
from frappe.utils import get_url_to_form
from frappe.model.mapper import get_mapped_doc

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
