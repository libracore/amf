# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import requests
from requests.auth import HTTPBasicAuth
from frappe.utils.password import get_decrypted_password

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
        endpoint = "{0}{1}forms/{2}/entries".format(self.gravity_host, API_PATH, form_id)

        response = requests.get(endpoint, auth=self.get_auth())
        
        entries = []
        if response.status_code == 200:
            entries = response.json().get('entries')
                
        else:
            frappe.throw("Gravity Forms: Error {0}: {1}".format(response.status_code, response.text))
            
        return entries
