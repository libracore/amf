from __future__ import unicode_literals

import frappe

from amf.amf.utils.issue_classification import sync_issue_classification_setup


def execute():
	"""Install smart Issue Type suggestions on AMF Issue Test."""
	frappe.set_user("Administrator")
	frappe.reload_doc("amf", "doctype", "amf_issue_process", force=True)
	sync_issue_classification_setup()
