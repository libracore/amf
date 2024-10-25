# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe
from amf.master_crm.naming import get_fixed_length_string, naming_patterns
from tqdm import tqdm  # Import the tqdm library for the progress bar

"""
Run this to move contacts into naming series

 $ bench execute amf.master_crm.migration.prepare_contact_naming
 
"""
def prepare_contact_naming():
    contacts = frappe.get_all("Contact", fields=['name'])
    
    counter = 0
    
    for c in contacts:
        counter += 1
        if c.get('name').startswith(naming_patterns['Contact']['prefix']) and len(c.get('name')) == (len(naming_patterns['Contact']['prefix']) + naming_patterns['Contact']['length']):
            print("Skipping {0} (already new pattern)...".format(c.get('name')))
            continue
        number = get_fixed_length_string(counter, naming_patterns['Contact']['length'])
        new_name = "{prefix}{n}".format(prefix=naming_patterns['Contact']['prefix'], n=number)
        while frappe.db.exists("Contact", new_name):
            counter += 1
            number = get_fixed_length_string(counter, naming_patterns['Contact']['length'])
            new_name = "{prefix}{n}".format(prefix=naming_patterns['Contact']['prefix'], n=number)
        print("Rename {0} to {1}...".format(c.get('name'), new_name))
        frappe.rename_doc("Contact", c.get('name'), new_name)
        frappe.db.commit()
        
    return
    
"""
Run this to populate full_name

 $ bench execute amf.master_crm.migration.populate_full_name
 
"""
def populate_full_name():
    contacts = frappe.get_all("Contact", fields=['name', 'first_name', 'last_name', 'full_name'])
    for c in contacts:
        if not c.get('full_name'):
            print("Updating {0}...".format(c.get('name')))
            contact_doc = frappe.get_doc("Contact", c.get('name'))
            contact_doc.full_name = "{0} {1}".format((c.get('first_name') or ""), (c.get('last_name') or ""))
            if contact_doc.status not in ["Lead", "Prospect", "Customer", "Back-Office", "Passive"]:
                contact_doc.status = "Passive"
            try:
                contact_doc.save()
            except Exception as err:
                print(err)
            frappe.db.commit()
    return
    
"""
Patch to assure translation for customer
"""
def translate_customer_to_organization():
    customer_translations = frappe.get_all("Translation", filters={'language': 'en', 'source_name': 'Customer'}, fields=['name'])
    if len(customer_translations) == 0:
        frappe.get_doc({
            'doctype': 'Translation',
            'language': 'en', 
            'source_name': 'Customer',
            'target_name': 'Organization'
        }).insert()
        
    return
        

"""
Master CRM: pull company from "old" gravity entries into top-level field

Run with
    bench execute amf.master_crm.migration.pull_company_from_gravity_fields
"""
def pull_company_from_gravity_fields():
    entries = frappe.get_all("Gravity Form Entry", fields=['name'])
    for e in tqdm(entries, desc="Processing Gravity Form Entries", unit="#"):
        if not e.company:
            company = frappe.db.sql("""
                SELECT `value`
                FROM `tabGravity Form Entry Field`
                WHERE `parent` = "{e}"
                  AND `field_name` = "Company"
                  AND `parenttype` = "Gravity Form Entry";
                """.format(e=e['name']),  as_dict=True)
            if len(company) > 0:
                frappe.db.set_value("Gravity Form Entry", e['name'], 'company', company[0]['value'])
                frappe.db.commit()
    return
