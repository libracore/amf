from __future__ import unicode_literals

import frappe

from amf.amf.utils.product_description_update_2026 import apply_product_description_updates


def execute():
	frappe.set_user("Administrator")
	summary = apply_product_description_updates(frappe)
	frappe.logger("amf.patches").info(
		"Updated Product descriptions: {applied_count} changed, {product_count} verified".format(**summary)
	)
