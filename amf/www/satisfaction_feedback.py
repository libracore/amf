# -*- coding: utf-8 -*-
import frappe

from amf.master_crm.feedback import get_request

no_cache = 1
sitemap = 0


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = False
    context.title = "Your feedback | AMF"
    # Tokens and customer responses must never be cached or sent as Referer.
    try:
        request = get_request(frappe.form_dict.get("token"))
    except frappe.PermissionError:
        context.invalid_link = True
        return context
    context.token = frappe.form_dict.get("token")
    rating = str(frappe.form_dict.get("rating", ""))
    context.rating = int(rating) if rating in ("1", "2", "3", "4", "5") else None
    context.responded = bool(request.survey)
    return context
