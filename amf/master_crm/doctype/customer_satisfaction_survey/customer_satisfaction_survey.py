# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document


class CustomerSatisfactionSurvey(Document):
    def validate(self):
        if self.customer:
            self.organization_name = frappe.db.get_value("Customer", self.customer, "customer_name")
        if self.contact_person:
            self.contact_name = frappe.db.get_value("Contact", self.contact_person, "full_name")
        if self.contact_name and self.organization_name:
            self.title = "{0} for {1}".format(self.contact_name, self.organization_name)


def update_contact_csat_nps(doc, method):
    """Reflect the latest submitted response, including after a cancellation.

    Preserve the existing 0–100 conversions: recommendation * 10 is the
    historical AMF score and is intentionally not standard NPS.
    """
    if not doc.contact_person:
        return
    rows = frappe.get_all(
        "Customer Satisfaction Survey",
        filters={"contact_person": doc.contact_person, "docstatus": 1},
        fields=["amf_overall", "recommend"],
        order_by="date_interaction desc, creation desc, name desc", limit_page_length=1,
    )
    latest = rows[0] if rows else {}
    overall = latest.get("amf_overall")
    recommend = latest.get("recommend")
    frappe.db.set_value("Contact", doc.contact_person, {
        "customer_satisfaction_survey": float(overall) * 20 if overall else None,
        "referral_satisfaction_survey": int(recommend) * 10 if recommend not in (None, "") else None,
    }, update_modified=False)

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
    frappe.only_for("System Manager")
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
