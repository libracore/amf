frappe.query_reports["Summary SC&M Dashboard"] = {
    "filters": [
      {
        "fieldname": "item_code",
        "label": __("Item Code"),
        "fieldtype": "Link",
        "options": "Item"
      },
      {
        "fieldname": "item_group",
        "label": __("Item Group"),
        "fieldtype": "Link",
        "options": "Item Group"
      },
      {
        "fieldname": "year",
        "label": __("Year"),
        "fieldtype": "Link",
        "options": "Fiscal Year"
      }
    ],
  
    onload: function(report) {
      report.page.add_inner_button(__("Update Charts"), function() {
        create_charts(report);
      });
    }
  };
  
  function create_charts(report) {
    let filters = report.get_values();
  
    frappe.call({
      method: "amf.amf.api.get_chart_data",
      args: {
        item_code: filters.item_code,
        item_group: filters.item_group,
        year: filters.year
      },
      callback: function(response) {
        let data = response.message;
  
        report.chart = new frappe.Chart(".chart-container", {
          title: "Item Purchased, Produced and Delivered",
          data: data,
          type: "line",
          height: 250,
          colors: ["green", "blue", "red"],
          axisOptions: {
            xIsSeries: 1
          },
          barOptions: {
            spaceRatio: 0.5
          },
          lineOptions: {
            dotSize: 5
          },
          tooltipOptions: {
            formatTooltipX: d => (d + "").toUpperCase(),
            formatTooltipY: d => d.toFixed(2) + " items"
          }
        });
      }
    });
  }
  