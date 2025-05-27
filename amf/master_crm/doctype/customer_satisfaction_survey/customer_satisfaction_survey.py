# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class CustomerSatisfactionSurvey(Document):
	pass

def update_contact_csat_nps(doc, method):
    """
    This function is meant to be called right after a new Customer Satisfaction Survey 
    record has been inserted. It updates the 'csat' and 'nps' fields in the linked 
    Contact Doctype, if available.
    """
    # Ensure that we have a valid contact person link
    if doc.contact_person:
        # Update csat and nps fields directly using set_value (bypasses full Doc validations for speed)
        # Convert doc.amf_overall and doc.recommend to floats if they might come in as strings
        amf_overall = float(doc.amf_overall) if doc.amf_overall else 0.0
        recommend = float(doc.recommend) if doc.recommend else 0.0

        # Example calculations
        csat_value = amf_overall * 100 / 5  # e.g., if amf_overall is from 1 to 5
        nps_value = recommend * 10         # e.g., if recommend is from 0 to 10

        # frappe.db.set_value("Contact", doc.contact_person, "csat", csat_value)
        # frappe.db.set_value("Contact", doc.contact_person, "nps", int(nps_value))
        frappe.db.set_value("Contact", doc.contact_person, "customer_satisfaction_survey", csat_value)
        frappe.db.set_value("Contact", doc.contact_person, "referral_satisfaction_survey", int(nps_value))
        # Optionally, if you need triggers or validations from the Contact doctype to run,
        # you could load and save:
        #
        # contact = frappe.get_doc("Contact", doc.contact_person)
        # contact.csat = doc.csat
        # contact.nps = doc.nps
        # contact.save(ignore_permissions=True)
    return None