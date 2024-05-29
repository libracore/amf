frappe.pages['home'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'AMF Operations',
		single_column: true
	});

	// Call the server-side method to get the data
    frappe.call({
        method: 'amf.amf.page.home.home.get_web_pages', // Adjust the path accordingly
        callback: function(r) {
            if (r.message) {
				console.log(r.message);
                renderTable(r.message, page);
            }
        }
    });
}

function renderTable(data, page) {
    var table = $('<table class="table table-bordered" style="background-color: white;">');
	var thead = $('<thead>').append('<tr style="background-color: #2b47d9; color: white; font-weight: bold;"><th>Web Page Name</th><th>Route</th></tr>');
	var tbody = $('<tbody>');

    data.forEach(function(row) {
		var nameLink = $('<a>').attr('href', 'http://amf.libracore.ch/desk#Form/Web%20Page/' + encodeURIComponent(row.name)).text(row.title);
        var routeLink = $('<a>').attr('href', row.route).text(row.route);
        var tr = $('<tr>').append($('<td>').append(nameLink)).append($('<td>').append(routeLink));
		tbody.append(tr);
    });

    table.append(thead).append(tbody);
	$(page.main).append(table);
}