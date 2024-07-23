# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe 
from frappe.utils import get_url_to_form

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
