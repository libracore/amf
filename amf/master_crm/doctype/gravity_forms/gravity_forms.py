# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import requests
from requests.auth import HTTPBasicAuth
from frappe.utils.password import get_decrypted_password
import json
from frappe.utils import cint

API_PATH = "/wp-json/gf/v2/"

class GravityForms(Document):
    def get_forms(self):
        endpoint = "{0}{1}forms".format(self.gravity_host, API_PATH)

        response = requests.get(endpoint, auth=self.get_auth())
        
        forms = []
        if response.status_code == 200:
            for k, v in response.json().items():
                forms.append(v)
                
        else:
            frappe.throw("Gravity Forms: Error {0}: {1}".format(response.status_code, response.text))
            
        return forms
    
    def get_auth(self):
        return HTTPBasicAuth(
            frappe.get_value("Gravity Forms", "Gravity Forms", "gravity_key"), 
            get_decrypted_password("Gravity Forms", "Gravity Forms", "gravity_secret", False)
        )

    def get_entry(self, entry_id):
        endpoint = "{0}{1}entries/{2}".format(self.gravity_host, API_PATH, entry_id)

        response = requests.get(endpoint, auth=self.get_auth())
        
        if response.status_code == 200:
            print(response.text)
                
        else:
            frappe.throw("Gravity Forms: Error {0}: {1}".format(response.status_code, response.text))
            
        return
    
    def get_form_fields(self, form_id):
        endpoint = "{0}{1}forms/{2}".format(self.gravity_host, API_PATH, form_id)

        response = requests.get(endpoint, auth=self.get_auth())
        
        if response.status_code == 200:
            fields = response.json().get('fields')
            return fields
                
        else:
            frappe.throw("Gravity Forms: Error {0}: {1}".format(response.status_code, response.text))
            
        return
    
    def get_form_entries(self, form_id):
        endpoint = "{0}{1}forms/{2}/entries?sorting[key]=id&sorting[direction]=ASC&sorting[is_numeric]=true&paging[page_size]=100".format(self.gravity_host, API_PATH, form_id)

        response = requests.get(endpoint, auth=self.get_auth())
        
        entries = []
        if response.status_code == 200:
            entries = response.json().get('entries')
                
        else:
            frappe.throw("Gravity Forms: Error {0}: {1}".format(response.status_code, response.text))
            
        return entries

@frappe.whitelist()
def fetch_forms():
    gravity = frappe.get_doc("Gravity Forms", "Gravity Forms")
    forms = gravity.get_forms()
    if forms:
        for f in forms:
            if not frappe.db.exists("Gravity Form", f.get('id')):
                fields = gravity.get_form_fields(f.get('id'))
                new_form = frappe.get_doc({
                    'doctype': 'Gravity Form',
                    'gravity_form_id': f.get('id'),
                    'title': f.get('title')
                })
                for i in fields:
                    new_form.append("fields", {
                        'field_id': i.get('id'),
                        'field_name': i.get('label')
                    })
                new_form.insert(ignore_permissions=True)
        frappe.db.commit()
        
    return forms

@frappe.whitelist()
def fetch_entries():
    # first, make sure all forms are available
    forms = fetch_forms()
    gravity = frappe.get_doc("Gravity Forms", "Gravity Forms")
    if forms:
        for f in forms:
            if cint(frappe.get_value("Gravity Form", f.get('id'), 'disabled')) == 0:
                frappe.log_error("Fetch {0} entries".format(f.get('id')))
                entries = fetch_form_entries(f.get('id'))
        
    return

@frappe.whitelist()
def fetch_form_entries(gravity_form):
    gravity = frappe.get_doc("Gravity Forms", "Gravity Forms")
    entries = gravity.get_form_entries(gravity_form)
    # find import table
    form_doc = frappe.get_doc("Gravity Form", gravity_form)
    import_keys = {}
    for f in form_doc.fields:
        if cint(f.get('import')) == 1:
            import_keys[f.get('field_id')] = f.get('field_name')
    if entries:
        for e in entries:
            if not frappe.db.exists("Gravity Form Entry", e.get('id')):
                new_entry = frappe.get_doc({
                    'doctype': 'Gravity Form Entry',
                    'gravity_form_entry_id': e.get('id'),
                    'content': "{0}".format(e),
                    'gravity_form': gravity_form
                })
                for k, v in import_keys.items():
                    new_entry.append('fields', {
                        'field_name': v,
                        'value': e.get(k)
                    })
                new_entry.insert(ignore_permissions=True)
        frappe.db.commit()
        
    return entries
