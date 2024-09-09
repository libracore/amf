# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password
import requests
import json

API_HOST = "https://api.brevo.com/v3/"

class Brevo(Document):
    def get_api_key(self):
        return get_decrypted_password("Brevo", "Brevo", "api_key", False)

    def get_all_contacts(self):
        contacts = []
        limit = 50
        offset = 0
        _contact = self.get_contacts(limit, offset)
        while _contact:
            for c in _contact:
                contacts.append(c)
            offset += limit
            _contact = self.get_contacts(limit, offset)
        
        return "Received {0} contacts".format(len(contacts))
        
        
    def get_contacts(self, limit, offset):
        parameters = {
            # 'modifiedSince': 'YYYY-MM-DDTHH:mm:ss.SSSZ',
            'limit': '{0}'.format(limit),
            'offset': '{0}'.format(offset),
            #'sort': 'desc',
        }
        endpoint = "{0}contacts".format(API_HOST)

        response = requests.get(endpoint, headers=self.get_headers(), params=parameters)
        
        contacts = response.json().get('contacts')      # list of contacts
        
        """ contacts structure:
        {
            'email': 'example@domain.com', 
            'id': 1234, 
            'emailBlacklisted': False, 
            'smsBlacklisted': False, 
            'createdAt': '2024-08-26T16:52:51.853+02:00', 
            'modifiedAt': '2024-08-27T07:30:28.035+02:00', 
            'listIds': [40], 
            'listUnsubscribed': None, 
            'attributes': {
                'TAG': 'Industry', 
                'STATUS': 'Client', 
                'DELIVRABILITE': 'OK', 
                'SOURCE': 'My List', 
                'COMPANY_NAME': 'Example Corp'
            }
        }
        """
        
        return contacts

    def get_all_lists(self):
        endpoint = "{0}contacts/lists".format(API_HOST)

        response = requests.get(endpoint, headers=self.get_headers())
        
        lists = response.json().get('lists')      # list of contacts
                
        return lists
    
    def create_update_contact(self, contact, list_ids=[]):
        contact_doc = frappe.get_doc("Contact", contact)
        if not contact_doc.email_id:
            return
            
        parameters = {
            'email': contact_doc.email_id,
            'ext_id': contact_doc.name,
            'updateEnabled': True
        }
        if list_ids and len(list_ids) > 0:
            parameters['listIds'] = list_ids
            
        endpoint = "{0}contacts".format(API_HOST)

        headers = self.get_headers()
        headers['content-type'] = 'application/json'
        
        response = requests.post(endpoint, headers=headers, json=parameters)
        
        if response.status_code == 201:
            return {'status': 'Created', 'text': response.text}
        elif response.status_code == 204:
            return {'status': 'Updated', 'text': response.text}
        elif response.status_code == 400:
            return {'status': 'Bad Request', 'text': response.text}
        elif response.status_code == 425:
            return {'status': 'Too Early', 'text': response.text}
        else:
            return {'status': 'Unknown Error', 'text': response.text}

    def get_headers(self):
        headers = {
            'api-key': self.get_api_key(),
            'accept': 'application/json'
        }
        
        return headers
        
    def delete_contact(self, contact):
        contact_doc = frappe.get_doc("Contact", contact)
        if not contact_doc.email_id:
            return
            
        endpoint = "{0}contacts/{1}".format(API_HOST, contact_doc.email_id)
        
        response = requests.delete(endpoint, headers=self.get_headers())
        
        if  response.status_code == 204:
            return {'status': 'Deleted', 'text': response.text}
        elif response.status_code == 400:
            return {'status': 'Bad Request', 'text': response.text}
        elif response.status_code == 404:
            return {'status': 'Contact Not Found', 'text': response.text}
        elif response.status_code == 425:
            return {'status': 'Too Early', 'text': response.text}
        else:
            return {'status': 'Unknown Error', 'text': response.text}
            
@frappe.whitelist()
def fetch_contacts():
    brevo = frappe.get_doc("Brevo", "Brevo")
    return brevo.get_all_contacts()
    
    
@frappe.whitelist()
def fetch_lists():
    brevo = frappe.get_doc("Brevo", "Brevo")
    return brevo.get_all_lists()

@frappe.whitelist()
def create_update_contact(contact, list_ids=[]):
    if type(list_ids) == str:
        list_ids = json.loads(list_ids)
    brevo = frappe.get_doc("Brevo", "Brevo")
    return brevo.create_update_contact(contact, list_ids)
