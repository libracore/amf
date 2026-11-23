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
      - Store those averages in today's Global Satisfaction Score snapshot
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
    avg_csat = ((sum(csat_values) / len(csat_values)) / 20) if csat_values else 0.0
    avg_nps  = round((sum(nps_values)  / len(nps_values)), 1)  if nps_values  else 0.0

    # Preserve AMF's existing formulas. The naming rule has one record per day;
    # rerunning the scheduled calculation must not fail with a duplicate name.
    scores = {
        "global_csat_score": avg_csat,
        "global_nps_score": avg_nps,
    }
    if frappe.db.exists("Global Satisfaction Score", nowdate()):
        frappe.db.set_value("Global Satisfaction Score", nowdate(), scores)
    else:
        frappe.get_doc(dict(doctype="Global Satisfaction Score", **scores)).insert(ignore_permissions=True)
    # The scheduler/request owns the transaction; do not commit callers' work.
