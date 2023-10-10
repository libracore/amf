// Copyright (c) 2016, libracore AG and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Monthly Stock and Revenue Report"] = {
	"filters": [

	]
};

refresh(function() {
    frappe.require("assets/frappe/js/lib/frappe-charts.min.js", function() {
        frappe.call({
            "method": "frappe.desk.query_report.run",
            args: {
                report_name: "Monthly Stock and Revenue Report",
                filters: {}
            },
            callback: function(r) {
                const labels = r.message.map(d => d.month);
                const stock_values = r.message.map(d => d.stock_value);
                const revenue_values = r.message.map(d => d.revenue);

                const data = {
                    labels: labels,
                    datasets: [
                        {
                            name: "Stock Value",
                            values: stock_values
                        },
                        {
                            name: "Revenue",
                            values: revenue_values
                        }
                    ]
                };

                const chart = new frappe.Chart("#chart", {
                    data: data,
                    type: 'line'
                });
            }
        });
    });
});
