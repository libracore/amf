# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password
import requests
import json
from frappe.utils.background_jobs import enqueue
from frappe.utils import cint

API_HOST = "https://api.brevo.com/v3/"

class Brevo(Document):
    def get_api_key(self):
        return get_decrypted_password("Brevo", "Brevo", "api_key", False)

    def enqueue_sync_contacts(self):
        # enqueue pulling contacts


        enqueue("amf.master_crm.doctype.brevo.brevo.sync_contacts",
            queue='long',
            timeout=15000)
        return
    
    def get_all_contacts(self, sync=False):
        contacts = []
        limit = 50
        offset = 0
        _contact = self.get_contacts(limit, offset)
        while _contact:
            for c in _contact:
                contacts.append(c)
                if sync:
                    self.sync_contact(c)
                    
            offset += limit
            _contact = self.get_contacts(limit, offset)
        
        return "Received {0} contacts".format(len(contacts))
        
    def sync_contact(self, brevo_contact):
        contact_matches = frappe.get_all("Contact", filters={'email_id': brevo_contact.get("email")}, fields=['name'])
        attributes = brevo_contact.get("attributes")
        if len(contact_matches) == 0:
            # create new
            contact = frappe.get_doc({
                'doctype': 'Contact',
            })
            contact.append('email_ids', {
                'email_id': brevo_contact.get("email"),
                'is_primary': 1
            })
        else:
            # update
            contact = frappe.get_doc("Contact", contact_matches[0]['name'])
        
        contact.update({
            'first_name': attributes.get("PRENOM"),
            'last_name': attributes.get("NOM"),
            'deliverability': attributes.get("DELIVRABILITE"),
            'source': attributes.get("FROM"),
            'event_source': attributes.get("SOURCE") if frappe.db.exists("Event Source", attributes.get("SOURCE")) else None
        })
        contact.flags.ignore_mandatory = True
        contact.flags.ignore_validate = True
        contact.save()
        frappe.db.commit()
        return
            
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

    def get_all_lists(self, with_folders=False):
        lists = []
        limit = 50
        offset = 0
        _list = self.get_lists(limit, offset)
        while _list:
            for l in _list:
                lists.append(l)
                    
            offset += limit
            _list = self.get_lists(limit, offset)
        
        if cint(with_folders):
            folders = self.get_all_folders()
            for l in lists:
                l['folder_name'] = folders.get(l.get('folderId'))
                
        return lists
    
    def get_lists(self, limit, offset):
        parameters = {
            # 'modifiedSince': 'YYYY-MM-DDTHH:mm:ss.SSSZ',
            'limit': '{0}'.format(limit),
            'offset': '{0}'.format(offset),
            #'sort': 'desc',
        }
        endpoint = "{0}contacts/lists".format(API_HOST)

        response = requests.get(endpoint, headers=self.get_headers(), params=parameters)
        
        lists = response.json().get('lists')      # list of contacts
        
        """
        Structure
            {
                'folderId': 13
    ​​            'id': 42
                'name': "Test List"
                'totalBlacklisted': 0
                'totalSubscribers': 0
                'uniqueSubscribers': 76
            }
        """
        
        return lists
        
    def create_list(self, list_name):
        parameters = {
            'name': list_name
        }
            
        endpoint = "{0}contacts/lists".format(API_HOST)

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
    
    def get_all_folders(self):
        folders = []
        limit = 50
        offset = 0
        _folder = self.get_folders(limit, offset)
        while _folder:
            for f in _folder:
                folders.append(f)
                    
            offset += limit
            _folder = self.get_folders(limit, offset)
        
                
        # restructure so a simple dict
        folder_map = {}
        if folders:
            for f in folders:
                folder_map[f['id']] = f['name']
                
        return folder_map
        
    def get_folders(self, limit, offset):
        parameters = {
            # 'modifiedSince': 'YYYY-MM-DDTHH:mm:ss.SSSZ',
            'limit': '{0}'.format(limit),
            'offset': '{0}'.format(offset),
            #'sort': 'desc',
        }
        endpoint = "{0}contacts/folders".format(API_HOST)

        response = requests.get(endpoint, headers=self.get_headers(), params=parameters)
        
        folders = response.json().get('folders')      # list of contacts
        
        """
        Structure
            {
                'id': 1,
                'name': 'Your first folder',
                'uniqueSubscribers': 0,
                'totalSubscribers': 0,
                'totalBlacklisted': 0}]
            }
        """
            
        return folders
        
    def create_update_contact(self, contact, list_ids=[]):
        contact_doc = frappe.get_doc("Contact", contact)
        if not contact_doc.email_id:
            return
        
        address = None
        if contact_doc.address:
            address = frappe.get_doc("Address", contact_doc.address)
        
        customer = None
        if contact_doc.links and len(contact_doc.links) > 0:
            for c in contact_doc.links:
                if c.link_doctype == "Customer":
                    customer = frappe.get_doc("Customer", c.link_name)
                    break
        
        parameters = {
            'email': contact_doc.email_id,
            'ext_id': contact_doc.name,
            'updateEnabled': True,
            'attributes': {
                'PRENOM': contact_doc.first_name or "", 
                'NOM': contact_doc.last_name or "",
                'EMAIL': contact_doc.email_id or "",
                'COMPANY_NAME': customer.customer_name if customer else "",
                'COMPANY_PHONE': (address.phone or "") if address else "",
                'CITY': address.city if address else "",
                'COUNTRY': address.country if address else "",
                #'TAG': ,
                'STATUS': contact_doc.get("status") or "",
                'DELIVRABILITE': contact_doc.get("deliverability") or "",
                'FROM': contact_doc.get("source") or "",
                'SOURCE': contact_doc.get("event_source") or "",
                'LAST_MODIFIED': contact_doc.modified.strftime("%Y-%m-%d %H:%M:%S")
            }
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
    
def sync_contacts():
    brevo = frappe.get_doc("Brevo", "Brevo")
    brevo.get_all_contacts(sync=True)
    return
    
@frappe.whitelist()
def fetch_lists(with_folders=False):
    brevo = frappe.get_doc("Brevo", "Brevo")
    return brevo.get_all_lists(with_folders)

@frappe.whitelist()
def create_update_contact(contact, list_ids=[]):
    if type(list_ids) == str:
        list_ids = json.loads(list_ids)
    brevo = frappe.get_doc("Brevo", "Brevo")
    return brevo.create_update_contact(contact, list_ids)
