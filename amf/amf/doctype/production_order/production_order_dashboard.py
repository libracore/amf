from __future__ import unicode_literals
from frappe import _

def get_data():
	return {
		'fieldname': 'production_order',
		'transactions': [
			{
				'items': ['Work Order', 'Stock Entry']
			}
		]
	}