# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe 
from frappe.utils import get_url_to_form
from erpnextswiss.scripts.crm_tools import get_primary_customer_address

@frappe.whitelist()
def get_header(contact=None):
    contact_doc = {}
    address_display = ""
    customer_url = ""
    customer_name = ""
    status = {
        'value': 'Lead',
        'options': 'Lead'
    }
    if contact and frappe.db.exists("Contact", contact):
        contact_doc = frappe.get_doc("Contact", contact)
        status['value'] = contact_doc.status
        if contact_doc.address:
            # fetch address from contact
            address_display = get_address_display(contact_doc.address)
        elif contact_doc.links and len(contact_doc.links) > 0:
            # fetch address from company
            for l in contact_doc.links:
                if l.link_doctype == "Customer":
                    customer = l.link_name
                    customer_url = get_url_to_form("Customer", customer)
                    customer_name = frappe.get_value("Customer", customer, "customer_name")
                    address = get_primary_customer_address(l.link_name)
                    if address:
                        address_display = get_address_display(address.name)
                    break
    
    # get status
    contact_fields = frappe.get_meta("Contact").as_dict().get('fields')
    for f in contact_fields:
        if f['fieldname'] == "status":
            status['options'] = f['options']
            
    html = frappe.render_template(
        "amf/templates/includes/contact_header.html", 
        {
            'doc': contact_doc, 
            'address_display': address_display,
            'customer_url': customer_url,
            'customer_name': customer_name,
            'status': status
        }
    )
    return html
    
    
    
def get_address_display(address):
    template = frappe.get_all("Address Template", filters={'is_default': 1}, fields=['name', 'template'])
    if len(template) > 0:
        address_doc = frappe.get_doc("Address", address)
        address_display = frappe.render_template(template[0]['template'], address_doc.as_dict())
        return address_display
    else:
        return None
