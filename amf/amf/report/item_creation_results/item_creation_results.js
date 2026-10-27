frappe.query_reports["Item Creation Results"] = {
    filters: [
        {fieldname: "request", label: __("Request"), fieldtype: "Link", options: "Item Creation"},
        {fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item"},
        {fieldname: "bom", label: __("BOM or Previous Revision"), fieldtype: "Link", options: "BOM"},
        {fieldname: "status", label: __("Request Status"), fieldtype: "Select", options: "All\nSubmitted\nCancelled", default: "All"},
    ],
};
