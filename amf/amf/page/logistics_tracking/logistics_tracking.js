frappe.pages['logistics-tracking'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: '3PL Tracking',
        single_column: true
    });

    // Create a container for the table
    $(page.body).append('<div id="logistics-tracking-table"></div>');

    // Fetch data from the DHL Tracking Information doctype
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'DHL Tracking Information',
            fields: ['dn', 'tracking_number', 'customer', 'status', 'last_update', 'fetch_date'],
            order_by: 'fetch_date',
            limit_page_length:500,
        },
        callback: function(response) {
            var data = response.message;
            console.log(data)
            if (data && data.length > 0) {
                // Create a table
                var table = $('<table class="table table-bordered"><thead><tr></tr></thead><tbody></tbody></table>');

                // Define the headers
                var headers = ['Delivery Note', 'Tracking Number', 'Customer', 'Status', 'Last Update', 'Date'];
                var fields = ['dn', 'tracking_number', 'customer', 'status', 'last_update', 'fetch_date'];

                // Add table headers with inline styles
                headers.forEach(function(header) {
                    table.find('thead tr').append('<th style="background-color: #2b47d9; color: white; font-weight: bold;">' + header + '</th>');
                });

                // Add table rows
                data.forEach(function(row) {
                    var tableRow = $('<tr></tr>');

                    // Add delivery note as hyperlink
                    var deliveryNoteUrl = 'https://amf.libracore.ch/desk#Form/Delivery Note/' + row['dn'];
                    tableRow.append('<td style="background-color: white;"><a href="' + deliveryNoteUrl + '" target="_blank">' + row['dn'] + '</a></td>');

                    // Add tracking number as hyperlink
                    var trackingNumberUrl = 'https://www.dhl.com/ch-en/home/tracking/tracking-express.html?submit=1&tracking-id=' + row['tracking_number'];
                    tableRow.append('<td style="background-color: white;"><a href="' + trackingNumberUrl + '" target="_blank">' + row['tracking_number'] + '</a></td>');

                    // Add the rest of the fields
                    tableRow.append('<td style="background-color: white;">' + row['customer'] + '</td>');
                    tableRow.append('<td style="background-color: white;">' + row['status'] + '</td>');
                    tableRow.append('<td style="background-color: white;">' + row['last_update'] + '</td>');
                    tableRow.append('<td style="background-color: white;">' + row['fetch_date'] + '</td>');

                    table.find('tbody').append(tableRow);
                });

                // Append the table to the container
                $('#logistics-tracking-table').append(table);
            } else {
                $('#logistics-tracking-table').html('<p>No tracking information found.</p>');
            }
        }
    });
};