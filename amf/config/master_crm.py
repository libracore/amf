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
                        "name": "Campaign List",
                        "label": _("Campaign List"),
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
            "label": _("Reporting"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "report",
                        "name": "Sales Analytics",
                        "label": _("Sales Analytics"),
                        "doctype": "Sales Invoice",
                        "is_query_report": True
                    },
                    {
                        "type": "report",
                        "name": "Customer Satisfaction",
                        "label": _("Customer Satisfaction"),
                        "doctype": "Customer Satisfaction Survey",
                        "is_query_report": True
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
        {
            "label": _("Integration"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "doctype",
                        "name": "Brevo",
                        "label": _("Brevo"),
                        "description": _("Brevo")
                    },
                    {
                        "type": "doctype",
                        "name": "Gravity Forms",
                        "label": _("Gravity Forms"),
                        "description": _("Gravity Forms")
                    }
            ]
        },
        {
            "label": _("Customer Satisfaction"),
            "icon": "octicon octicon-git-compare",
            "items": [
                    {
                        "type": "doctype",
                        "name": "Customer Satisfaction Survey",
                        "label": _("Customer Satisfaction Survey"),
                        "description": _("Customer Satisfaction Survey")
                    },
                    {
                        "type": "doctype",
                        "name": "Referral Satisfaction Survey",
                        "label": _("Referral Satisfaction Survey"),
                        "description": _("Referral Satisfaction Survey")
                    }
            ]
        }
]
