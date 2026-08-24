from __future__ import unicode_literals

import frappe

from amf.amf.utils.purchased_item_description_update_2026 import apply_purchased_item_description_updates


def execute():
	frappe.set_user("Administrator")
	apply_purchased_item_description_updates(frappe)
