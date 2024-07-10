# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe import _

def get_data():
    return [
        {
            "module_name": "AMF",
            "color": "#2b47d9",
            "icon": "octicon octicon-file-directory",
            "type": "module",
            "label": _("AMF")
        },
        {
            "module_name": "Master CRM",
            "color": "#EF4DB6",
            "icon": "icon crm-blue",
            "type": "module",
            "label": _("Master CRM")
        }
    ]
