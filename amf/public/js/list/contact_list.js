// Copyright (c) 2024, libracore and contributors
// For license information, please see license.txt

// render
frappe.listview_settings['Contact'] = {
    get_indicator: function(doc) {
        var status_color = {
            "Lead": "red",
            "Prospect": "orange",
            "Customer": "green",
            "Back-Office": "blue",
            "Passive": "grey"
        };
        return [__(doc.status), status_color[doc.status], "status,=,"+doc.status];
    }
};

