from __future__ import unicode_literals

import frappe

from amf.amf.utils.client_description_metadata_cleanup_2026 import apply_client_description_metadata_cleanup


def execute():
	frappe.set_user("Administrator")
	apply_client_description_metadata_cleanup(frappe)
