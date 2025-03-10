from __future__ import unicode_literals
import frappe
from frappe import _

def modify_dn_dashboard(data):
	return frappe._dict({
		'fieldname': 'delivery_note',
		'non_standard_fieldnames': {
			'Stock Entry': 'delivery_note_no',
			'Global Quality Inspection': 'reference_name',
			'Auto Repeat': 'reference_document',
		},
		'internal_links': {
			'Sales Order': ['items', 'against_sales_order'],
		},
		'transactions': [
			{
				'label': _('Related'),
				'items': ['Sales Invoice', 'Packing Slip', 'Delivery Trip']
			},
			{
				'label': _('Reference'),
				'items': ['Sales Order']
			},
			{
				'label': _('Returns'),
				'items': ['Stock Entry']
			},
			{
				'label': _('Subscription'),
				'items': ['Auto Repeat']
			},
            {
				'label': _('Quality'),
				'items': ['Global Quality Inspection']
			},
		]
	})