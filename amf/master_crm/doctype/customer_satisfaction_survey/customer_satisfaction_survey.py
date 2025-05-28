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
        frappe.db.set_value("Contact", doc.contact_person,
                            "customer_satisfaction_survey", csat_value)
        frappe.db.set_value("Contact", doc.contact_person,
                            "referral_satisfaction_survey", int(nps_value))
        # Optionally, if you need triggers or validations from the Contact doctype to run,
        # you could load and save:
        #
        # contact = frappe.get_doc("Contact", doc.contact_person)
        # contact.csat = doc.csat
        # contact.nps = doc.nps
        # contact.save(ignore_permissions=True)
    return None

# my_app/my_app/utils/migrate_amf.py


@frappe.whitelist()
def migrate_amf_overall_to_contact():
    """
    One-time migration:
      - Loop through all Customer Satisfaction Survey records
      - For each, read 'amf_overall' (1–5)
      - Convert to a 0–100 scale
      - Write it into the linked Contact's 'amf_overall' field
    """
    surveys = frappe.get_all(
        "Customer Satisfaction Survey",
        filters=[
            ["Customer Satisfaction Survey", "docstatus", "=", 1],
            ["Customer Satisfaction Survey",
            	"amf_overall", "!=", ""],  # not NULL/empty
        ],
        fields=["name", "amf_overall", "contact_person"],
        limit_page_length=None  # fetch all records
    )
    print(surveys)
    updated = 0
    for s in surveys:
        print(s)
        contact_name = s.contact_person
        rating = s.amf_overall

        # skip if no contact or no rating
        if not contact_name or rating is None:
            continue

        # ensure we have a float
        try:
            rating = float(rating)
        except ValueError:
            frappe.log_error(
                title="AMF Migration: invalid rating",
                message=f"Survey {s.name} has non-numeric amf_overall: {s.amf_overall}"
            )
            continue

        # convert to 0–100
        percent_score = int(round(rating * 20))

        # write back to Contact
        frappe.db.set_value(
            "Contact",
            contact_name,
            "customer_satisfaction_survey",
            percent_score
        )
        updated += 1

    # persist all changes
    frappe.db.commit()
    print(
    	f"[AMF Migration] Updated {updated} contacts with amf_overall on a 0–100 scale.")
