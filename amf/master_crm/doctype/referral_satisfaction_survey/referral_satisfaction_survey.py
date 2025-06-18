# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class ReferralSatisfactionSurvey(Document):
	pass

def update_contact_csat_nps(doc, method):
    """
    This function is meant to be called right after a new Customer Satisfaction Survey 
    record has been inserted. It updates the 'csat' and 'nps' fields in the linked 
    Contact Doctype, if available.
    """
    amf_overall = float(5)
    recommend = float(10)
    
    csat_value = amf_overall * 100 / 5  # e.g., if amf_overall is from 1 to 5
    nps_value = recommend * 10         # e.g., if recommend is from 0 to 10
    
    if doc.doctype == 'Global Satisfaction Survey':
        frappe.db.set_value("Contact", doc.contact_person, "customer_satisfaction_survey", csat_value)
        frappe.db.set_value("Contact", doc.contact_person, "customer_satisfaction_survey", int(nps_value))
    elif doc.doctype == 'Referral Satisfaction Survey':
        frappe.db.set_value("Contact", doc.referring_contact, "customer_satisfaction_survey", csat_value)
        frappe.db.set_value("Contact", doc.referring_contact, "referral_satisfaction_survey", int(nps_value))

    return None