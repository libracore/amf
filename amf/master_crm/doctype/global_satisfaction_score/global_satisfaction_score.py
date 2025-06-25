# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
# import frappe
from frappe.model.document import Document

class GlobalSatisfactionScore(Document):
	pass

import frappe
from frappe import _
from frappe.utils import nowdate

def calculate_global_scores():
    """
    Scheduled weekly:
      - Compute average customer_satisfaction_survey (CSAT)
        and referral_satisfaction_survey (NPS) across all Contacts
      - Create a NEW Global Satisfaction Score record with those averages
    """
    # 1) Fetch all contacts' scores
    contacts = frappe.get_all(
        "Contact",
        fields=["customer_satisfaction_survey", "referral_satisfaction_survey"],
    )

    csat_values = []
    nps_values = []

    for c in contacts:
        csat = c.get("customer_satisfaction_survey")
        if csat not in (None, ""):
            try:
                csat_values.append(float(csat))
            except ValueError:
                frappe.log_error(
                    message=_("Invalid CSAT value '{0}'").format(csat),
                    title="Global Satisfaction Score"
                )

        nps = c.get("referral_satisfaction_survey")
        if nps not in (None, ""):
            try:
                nps_values.append(float(nps))
            except ValueError:
                frappe.log_error(
                    message=_("Invalid NPS value '{0}'").format(nps),
                    title="Global Satisfaction Score"
                )

    # 2) Compute averages
    avg_csat = ((sum(csat_values) / len(csat_values)) / 5) if csat_values else 0.0
    avg_nps  = (sum(nps_values)  / len(nps_values))  if nps_values  else 0.0

    # 3) Create a new Global Satisfaction Score doc
    #    (assumes your Doctype is **not** single; each run makes one record)
    gs = frappe.get_doc({
        "doctype": "Global Satisfaction Score",
        "global_csat_score": avg_csat,
        "global_nps_score": avg_nps,
        # Optional: if you added a Date field, e.g. calculation_date
        # "calculation_date": nowdate()
    })
    gs.insert(ignore_permissions=True)

    # 4) Persist in the database
    frappe.db.commit()
