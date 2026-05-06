from __future__ import unicode_literals
from frappe import _


def get_data():
	return {
		"fieldname": "loan_order",
		"transactions": [
			{
				"label": _("Stock"),
				"items": ["Stock Entry", "Delivery Note"]
			},
			{
				"label": _("Support"),
				"items": ["Issue"]
			}
		]
	}
