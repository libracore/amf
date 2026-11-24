# -*- coding: utf-8 -*-
# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class ReferralSatisfactionSurvey(Document):
	pass

def update_contact_csat_nps(doc, method):
    """Compatibility shim: recording a referral supplies no numeric ratings.

    Previously this assigned a fabricated 100/100 to the referring contact.
    Only Customer Satisfaction Survey responses should update these scores.
    """
    return None
