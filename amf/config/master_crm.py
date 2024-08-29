from frappe import _

def get_data():
    return[
        {
            "label": _("Sales Pipeline"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "doctype",
                        "name": "Contact",
                        "label": _("Contact"),
                        "description": _("Contact")
                    },
                    {
                        "type": "doctype",
                        "name": "Customer",
                        "label": _("Customer"),
                        "description": _("Customer")
                    },
                    {
                        "type": "doctype",
                        "name": "Sales Action",
                        "label": _("Sales Action"),
                        "description": _("Sales Action")
                    },
                    {
                        "type": "report",
                        "name": "Address List",
                        "label": _("Address List"),
                        "doctype": "Contact",
                        "is_query_report": True
                    }
            ]
        },
        {
            "label": _("Activities"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "doctype",
                        "name": "Quotation",
                        "label": _("Quotation"),
                        "description": _("Quotation")
                    },
                    {
                        "type": "doctype",
                        "name": "Campaign",
                        "label": _("Campaign"),
                        "description": _("Campaign")
                    },
                    {
                        "type": "doctype",
                        "name": "Sales Activity",
                        "label": _("Sales Activity"),
                        "description": _("Sales Activity")
                    }
            ]
        },
        {
            "label": _("Complaints"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "doctype",
                        "name": "Issue",
                        "label": _("Issue"),
                        "description": _("Issue")
                    }
            ]
        },
        {
            "label": _("Maintenance"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "report",
                        "name": "Duplicate Contacts",
                        "label": _("Duplicate Contacts"),
                        "doctype": "Contact",
                        "is_query_report": True
                    }
            ]
        },
        ,
        {
            "label": _("Integration"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "doctype",
                        "name": "Brevo",
                        "label": _("Brevo"),
                        "description": _("Brevo")
                    }
            ]
        }
]
