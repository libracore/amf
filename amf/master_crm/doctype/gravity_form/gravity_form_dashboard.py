# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

from frappe import _

def get_data():
    return {
        'fieldname': 'gravity_form',
        'transactions': [
            {
                'label': _("Entries"),
                'items': ['Gravity Form Entry']
            }
        ]
    }
