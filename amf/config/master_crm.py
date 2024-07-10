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
                    }        
            ]
        }
]
