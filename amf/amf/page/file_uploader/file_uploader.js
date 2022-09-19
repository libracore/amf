frappe.pages['file_uploader'].on_page_load = function (wrapper) {

	// LAYOUT STUFF
	///////////////////

	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'File Uploader',
		single_column: false,
	});

	let state = {
		files: [], // will contain a list of objects with attributes: name, fileObj, uploaded, error, message
	};

	page.set_primary_action('Upload', upload, 'octicon octicon-plus');

	let form = new frappe.ui.FieldGroup({
		fields: [{
			label: 'dropzone',
			fieldname: 'dropzone',
			fieldtype: 'HTML',
			options: '<div id="dropzone" style="padding: 50px 0px; text-align: center; border: #999999 dashed 3px ">Drag PDF scans here<div id="dropmessage" hidden>...and drop!</div></div>',
		}, {
			label: 'Instructions',
			fieldname: 'instructions',
			fieldtype: 'HTML',
			options: '<p>The name of the file must match the name of the PINV. Cancelled and amended documents are matched based on their original name: PINV-00130.pdf will be attached to PINV-00130-2 for example</p>',
		}, {

			label: '',
			fieldtype: 'Column Break',
		}, {
			label: 'statusTable',
			fieldname: 'statusTable',
			fieldtype: 'HTML',
			options: '<div id="statusTable"></div>',
		}],
		body: page.body
	});
	form.make();

	const dropzone = document.body; // document.getElementById("dropzone");
	const dropmessage = document.getElementById("dropmessage");
	const statusTable = document.getElementById("statusTable");

	const tableTemplate = `
	<table class="table">
	<tbody>
		<tr>
			<th>Name</th>
			<th>Uploaded?</th>
		</tr>
		{% for file in files %}
		<tr>
			<td>{{ file.name }}</td>
			<td>
				{% if file.uploaded %}
				<i class="octicon octicon-check" style="color: #4bc240"></i>
				{% endif %}

				{% if file.error %}
				<i class="octicon octicon-x" style="color: #db4242"></i>
				{% endif %}

				{{ file.message }}
			</td>
		</tr>
		{% endfor %}
	</tbody>
	</table>
	`;

	function draw_table() {
		statusTable.innerHTML = frappe.render_template(tableTemplate, { files: state.files });
	}

	draw_table()

	// LOGIC
	////////////////////////

	async function upload() {

		// Get list of all available PINV
		let pinvs = await frappe.db.get_list("Purchase Invoice", {
			limit: 100000,
			filters: {
				docstatus: ["<", "2"],
			}
		})

		let fail = function (i, message) {
			state.files[i].error = true;
			state.files[i].uploaded = false;
			state.files[i].message = message;
		}

		// Upload each document.
		for (let i in state.files) {
			let file = state.files[i];
			let docname = file.name.replace(/\.[^/.]+$/, "");

			// Find closest PINV name, latest ammended version (furthest down the alphabet):
			let closest_match = pinvs.filter(p => p.name.slice(0, "PINV-12345".length) == docname)
				.sort()
				.reverse()[0]?.name;

			if (!closest_match) {
				fail(i, `PINV does not exist: ${docname}`);
				continue
			}

			let formData = new FormData();
			formData.append('is_private', 1);
			formData.append('folder', 'Home/Attachments');
			formData.append('doctype', 'Purchase Invoice');
			// TODO: make sure the file has a name that exists. Maybe fetch available PINV, match closest one.
			formData.append('docname', closest_match); // strip extension
			formData.append('file', file.fileObj, file.name);

			fetch('/api/method/upload_file', {
				method: 'POST',
				body: formData,
				headers: {
					'X-Frappe-CSRF-Token': frappe.csrf_token,
					'Accept': 'application/json',
				}
			})
				.then(response => response.json())
				.then(result => {
					if (result.exc_type && result.exc_type != "DuplicateEntryError") { // If it's a duplicate, then the document is actually uploaded.
						fail(result.exc_type);
					} else {
						state.files[i].uploaded = true;
						state.files[i].error = false;
						state.files[i].message = `<a href="/desk#Form/Purchase Invoice/${closest_match}" target="_blank">${closest_match}</a>`;
					}
					console.log(result);
				})
				.catch(error => {
					frappe.throw(error);
					fail("Error uploading, see debug console.");
					console.log('Error uploading file', file.name, error)
				})
				.finally(draw_table);
		}
	}


	// LISTENERS
	////////////////////////

	dropzone.addEventListener("dragover", (event) => {
		event.preventDefault();
	});

	dropzone.addEventListener("dragenter", (event) => {
		console.log("Drag enter");
		dropmessage.hidden = false;
	});

	dropzone.addEventListener("dragleave", (event) => {
		console.log("Drag leave");
		dropmessage.hidden = true;
	});

	dropzone.addEventListener("drop", (event) => {
		console.log(event.dataTransfer.files);
		dropmessage.hidden = true;
		for (let file of event.dataTransfer.files) {

			// avoid duplicates:
			if (state.files.filter(f => f.name == file.name).length > 0) {
				console.log("Duplicate detected:", file.name);
				continue;
			}
			state.files.push({
				name: file.name,
				fileObj: file,
				uploaded: false,
				error: null,
			})
		}
		draw_table();
		event.preventDefault();
	});
}