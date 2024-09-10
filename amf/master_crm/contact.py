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


def before_save(self, method):
    check_unique_primary_contact(self)
    return
    
def check_unique_primary_contact(contact):
    # check if there is a linked customer
    customer = None
    if contact.get('links'):
        for l in contact.get('links'):
            if l.get("link_doctype") == "Customer":
                customer = l.get('link_name')
                
    if customer:
        # check if this customer has other linked primary contacts
        other_primary_contacts = frappe.db.sql("""
            SELECT `tabContact`.`name`
            FROM `tabContact`
            JOIN `tabDynamic Link` ON `tabDynamic Link`.`parent` = `tabContact`.`name` AND `tabDynamic Link`.`link_doctype` = "Customer"
            WHERE 
                `tabContact`.`is_primary_contact` = 1
                AND `tabDynamic Link`.`link_name` = "{customer}"
                AND `tabContact`.`name` != "{contact}";
            """.format(contact=contact.name, customer=customer), as_dict=True)
            
        if len(other_primary_contacts) > 0:
            # disable other primary
            for o in other_primary_contacts:
                frappe.db.set_value("Contact", o.get('name'), 'is_primary_contact', 0)
            frappe.db.commit()
            
    return

@frappe.whitelist()
def create_update_contact(first_name=None, last_name=None, phone=None, email=None, position=None):
    existing_contact = frappe.get_all("Contact", filters={'email_id': email}, fields=['name'])
    
    if len(existing_contact) > 0:
        # update
        contact = frappe.get_doc("Contact", existing_contact[0]['name'])
        contact.update({
            'first_name': first_name or "",
            'last_name': last_name or "",
            'position': position or ""
        })
        contact.email_ids = []
        contact_phone_nos = []
        if email:
            contact.append("email_ids", {
                'email_id': email,
                'is_primary': 1
            })
        if phone:
            contact.append("phone_nos", {
                'phone': phone,
                'is_primary_phone': 1
            })
        contact.save()
        frappe.db.commit()
        return contact.name
        
    else:
        # create
        new_contact = frappe.get_doc({
            'doctype': 'Contact',
            'first_name': first_name or "",
            'last_name': last_name or "",
            'full_name': "{0} {1}".format(first_name or "", last_name or ""),
            'position': position or "",
            'status': 'Lead'
        })
        if email:
            new_contact.append("email_ids", {
                'email_id': email,
                'is_primary': 1
            })
        if phone:
            new_contact.append("phone_nos", {
                'phone': phone,
                'is_primary_phone': 1
            })
        new_contact.insert()
        frappe.db.commit()
        return new_contact.name
