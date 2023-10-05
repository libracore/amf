frappe.query_reports["Monthly Delivery Note Summary"] = {
    "filters": [
        {
            "fieldname": "month",
            "label": __("Month"),
            "fieldtype": "Select",
            "options": "January\nFebruary\nMarch\nApril\nMay\nJune\nJuly\nAugust\nSeptember\nOctober\nNovember\nDecember",
            "default": 'August'
        },
        {
            "fieldname": "year",
            "label": __("Year"),
            "fieldtype": "Int",
            "default": new Date().getFullYear()
        }
    ]
};
