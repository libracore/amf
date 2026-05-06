from __future__ import unicode_literals
import frappe
from frappe import _

def _ensure_group(data, label, items):
	for group in data.setdefault('transactions', []):
		if group.get('label') == label:
			for item in items:
				if item not in group.get('items', []):
					group.setdefault('items', []).append(item)
			return

	data.transactions.append({
		'label': label,
		'items': items
	})

def _set_non_standard_fieldname(data, doctype, fieldname):
	data.setdefault('non_standard_fieldnames', {})
	data.non_standard_fieldnames[doctype] = fieldname

def modify_so_dashboard(data):
	data = frappe._dict(data or {})
	_set_non_standard_fieldname(data, 'Issue', 'sales_order')
	_ensure_group(data, _('Support'), ['Issue'])
	return data

def modify_dn_dashboard(data):
	return frappe._dict({
		'fieldname': 'delivery_note',
		'non_standard_fieldnames': {
			'Stock Entry': 'delivery_note_no',
			'Global Quality Inspection': 'reference_name',
			'Issue': 'delivery_note',
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
			{
				'label': _('Support'),
				'items': ['Issue']
			},
		]
	})

def modify_issue_dashboard(data):
	data = frappe._dict(data or {})
	_set_non_standard_fieldname(data, 'Delivery Note', 'issue')
	_set_non_standard_fieldname(data, 'Sales Order', 'issue')
	_ensure_group(data, _('Reference'), ['Sales Order', 'Delivery Note'])
	return data
