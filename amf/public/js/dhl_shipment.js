// Copyright (c) 2026, libracore AG and contributors
// For license information, please see license.txt

function is_dhl_express_carrier(value) {
    return /(^|[^A-Z0-9])DHL($|[^A-Z0-9])/i.test(value || "");
}

function dhl_escape(value) {
    return frappe.utils.escape_html(String(value === undefined || value === null ? "" : value));
}

function dhl_remote_validation_html(result) {
    if (typeof result.validated !== "boolean") {
        return "";
    }
	const hasRemoteResponse = Boolean(
		result.http_status || result.response ||
		(result.dhl_errors || []).length || Object.keys(result.response_identifiers || {}).length
	);
	if (!hasRemoteResponse) {
		return "";
	}

    const status = result.http_status
        ? "HTTP " + dhl_escape(result.http_status) + (result.http_reason ? " " + dhl_escape(result.http_reason) : "")
        : __("No HTTP response received");
    const environment = result.environment ? " · " + dhl_escape(result.environment) : "";
    const identifiers = result.response_identifiers || {};
    const identifierHtml = Object.keys(identifiers).length
        ? "<p><strong>" + __("DHL request identifiers") + ":</strong> " +
            Object.keys(identifiers).map(key => "<code>" + dhl_escape(key) + "=" + dhl_escape(identifiers[key]) + "</code>").join(" · ") +
            "</p>"
        : "";

    if (result.validated) {
        return "<div class='alert alert-success'><strong>" + __("DHL validation passed") + "</strong><br>" +
            status + environment + "</div>" + identifierHtml;
    }

    const errors = result.dhl_errors || [];
    const errorHtml = errors.length
        ? "<ol style='padding-left: 22px;'>" + errors.map(error => {
            const metadata = [];
            if (error.code) {
                metadata.push(__("Code") + ": <code>" + dhl_escape(error.code) + "</code>");
            }
            if (error.path) {
                metadata.push(__("Field/path") + ": <code>" + dhl_escape(error.path) + "</code>");
            }
            const metadataHtml = metadata.length
                ? "<div class='text-muted small'>" + metadata.join(" · ") + "</div>"
                : "";
            return "<li style='margin-bottom: 10px;'><strong>" + dhl_escape(error.message) + "</strong>" + metadataHtml + "</li>";
        }).join("") + "</ol>"
        : "<div class='alert alert-warning'>" +
            __("DHL did not return a recognized structured error. Expand Raw MyDHL response below to see the complete response.") +
            "</div>";
    const rawResponse = dhl_escape(JSON.stringify(result.response || {}, null, 2));

	const failureLabel = result.failure_stage === "authentication"
		? __("DHL authentication failed — payload not validated")
		: (result.failure_stage === "authorization"
			? __("DHL authorization failed — payload not validated")
			: (result.failure_stage === "account_service_authorization"
				? __("DHL account/service authorization failed")
				: (result.failure_stage === "product_lookup"
					? __("DHL transport product lookup failed")
					: __("DHL validation rejected"))));

    return "<div class='alert alert-danger'><strong>" + failureLabel + "</strong><br>" +
        status + environment + "</div>" + identifierHtml +
        "<h5>" + __("What DHL reported") + "</h5>" + errorHtml +
        "<details open><summary><strong>" + __("Raw MyDHL response") + "</strong></summary>" +
        "<pre style='max-height: 320px; overflow: auto; white-space: pre-wrap;'>" + rawResponse + "</pre></details>";
}

function dhl_draft_message(result) {
    const draft = result.draft || result;
    const issues = draft.issues || [];
    const errors = issues.filter(issue => issue.severity === "error");
    const warnings = issues.filter(issue => issue.severity === "warning");
    const issueHtml = issues.length
        ? "<h5>" + __("Local ERPNext checks") + "</h5><ul>" + issues.map(issue => {
            const indicator = issue.severity === "error" ? "red" : "orange";
            return "<li><span class='indicator " + indicator + "'>" +
                dhl_escape(issue.message) + "</span>" +
                "<div class='text-muted small'>" + __("Code") + ": <code>" + dhl_escape(issue.code) +
                "</code> · " + __("Field/path") + ": <code>" + dhl_escape(issue.field) + "</code></div></li>";
        }).join("") + "</ul>"
        : "<h5>" + __("Local ERPNext checks") + "</h5><p><span class='indicator green'>" +
            __("Passed — no local blockers found") + "</span></p>";
    const payload = dhl_escape(JSON.stringify(draft.payload || {}, null, 2));
	const commodityCodes = ((draft.source_documents || {}).customs_commodity_codes || []);
	const commodityCodeHtml = commodityCodes.length
		? "<h5>" + __("Customs commodity codes from Delivery Note Items") + "</h5>" +
			"<div class='table-responsive'><table class='table table-bordered table-condensed'>" +
			"<thead><tr><th>" + __("DHL line") + "</th><th>" + __("Delivery Note") + "</th>" +
			"<th>" + __("Item") + "</th><th>" + __("DN customs_tariff_number_") + "</th>" +
			"<th>" + __("DHL outbound commodity code") + "</th></tr></thead><tbody>" +
			commodityCodes.map(row => "<tr><td>" + dhl_escape(row.line_number) + "</td><td>" +
				dhl_escape(row.delivery_note) + "</td><td>" + dhl_escape(row.item_code || row.delivery_note_item || "") +
				"</td><td><code>" + dhl_escape(row.source_value || "") + "</code></td><td><code>" +
				dhl_escape(row.dhl_value || __("not sent")) + "</code></td></tr>").join("") +
			"</tbody></table></div>"
		: "";
    const remoteMessage = result.message
        ? "<p>" + dhl_escape(result.message) + "</p>"
        : "";
    const remoteHtml = dhl_remote_validation_html(result);
    const hasValidationResult = typeof result.validated === "boolean";
    let title;
    let indicator;

    if (hasValidationResult && result.validated) {
        title = __("DHL Validation: Passed");
        indicator = "green";
	} else if (hasValidationResult && result.http_status) {
		if (result.failure_stage === "authentication") {
			title = __("DHL Authentication: Failed") + " (HTTP " + result.http_status + ")";
		} else if (result.failure_stage === "authorization") {
			title = __("DHL Authorization: Failed") + " (HTTP " + result.http_status + ")";
		} else if (result.failure_stage === "account_service_authorization") {
			title = __("DHL Account/Service: Not Allowed") + " (HTTP " + result.http_status + ")";
		} else if (result.failure_stage === "product_lookup") {
			title = __("DHL Transport Product: Lookup Failed") + " (HTTP " + result.http_status + ")";
		} else {
			title = __("DHL Validation: Rejected") + " (HTTP " + result.http_status + ")";
		}
        indicator = "red";
    } else if (hasValidationResult) {
        title = __("DHL Validation: Not completed");
        indicator = "red";
    } else {
        title = errors.length ? __("DHL Draft: Incomplete") : (warnings.length ? __("DHL Draft: Ready with warnings") : __("DHL Draft: Ready"));
        indicator = errors.length ? "red" : (warnings.length ? "orange" : "green");
    }

    return {
        title: title,
        indicator: indicator,
        message: remoteMessage + remoteHtml + issueHtml + commodityCodeHtml +
            "<details><summary>" + __("MyDHL validation payload") + "</summary>" +
            "<pre style='max-height: 420px; overflow: auto; white-space: pre-wrap;'>" + payload + "</pre></details>"
    };
}

function dhl_creation_message(result) {
	const status = result.http_status
		? "HTTP " + dhl_escape(result.http_status) + (result.http_reason ? " " + dhl_escape(result.http_reason) : "")
		: __("No HTTP response received");
	const environment = result.environment ? " · " + dhl_escape(result.environment) : "";
	const messageReference = result.message_reference
		? "<p><strong>" + __("DHL Message Reference") + ":</strong> <code>" +
			dhl_escape(result.message_reference) + "</code></p>"
		: "";
	const identifiers = result.response_identifiers || {};
	const identifierHtml = Object.keys(identifiers).length
		? "<p><strong>" + __("DHL response identifiers") + ":</strong> " +
			Object.keys(identifiers).map(key => "<code>" + dhl_escape(key) + "=" + dhl_escape(identifiers[key]) + "</code>").join(" · ") +
			"</p>"
		: "";

	if (result.created) {
		const pieces = (result.piece_tracking_numbers || []).length
			? "<p><strong>" + __("Piece tracking numbers") + ":</strong> " +
				result.piece_tracking_numbers.map(value => "<code>" + dhl_escape(value) + "</code>").join(" · ") + "</p>"
			: "";
		const dispatch = result.dispatch_confirmation_number
			? "<p><strong>" + __("Pickup dispatch confirmation") + ":</strong> <code>" +
				dhl_escape(result.dispatch_confirmation_number) + "</code></p>"
			: "";
		const tracking = result.tracking_url
			? "<p><a class='btn btn-default btn-sm' target='_blank' rel='noopener noreferrer' href='" +
				dhl_escape(result.tracking_url) + "'>" + __("Open DHL Tracking") + "</a></p>"
			: "";
		const documents = (result.attached_documents || []).length
			? "<h5>" + __("Private ERPNext attachments") + "</h5><ul>" +
				result.attached_documents.map(document => "<li><a href='" + dhl_escape(document.file_url) +
					"' target='_blank' rel='noopener noreferrer'>" + dhl_escape(document.file_name) + "</a></li>").join("") + "</ul>"
			: "";
		const warnings = (result.warnings || []).length
			? "<div class='alert alert-warning'><ul>" + result.warnings.map(warning => "<li>" + dhl_escape(warning) + "</li>").join("") + "</ul></div>"
			: "";
		return {
			title: __("DHL Shipment Created"),
			indicator: "green",
			message: "<div class='alert alert-success'><strong>" + dhl_escape(result.message) + "</strong><br>" +
				status + environment + "</div>" + messageReference + identifierHtml + pieces + dispatch + tracking + documents + warnings
		};
	}

	const errors = result.dhl_errors || [];
	const errorHtml = errors.length
		? "<h5>" + __("What DHL reported") + "</h5><ol>" + errors.map(error => {
			const metadata = [];
			if (error.code) {
				metadata.push(__("Code") + ": <code>" + dhl_escape(error.code) + "</code>");
			}
			if (error.path) {
				metadata.push(__("Field/path") + ": <code>" + dhl_escape(error.path) + "</code>");
			}
			return "<li><strong>" + dhl_escape(error.message) + "</strong>" +
				(metadata.length ? "<div class='text-muted small'>" + metadata.join(" · ") + "</div>" : "") + "</li>";
		}).join("") + "</ol>"
		: "";
	const rawResponse = result.response
		? "<details open><summary><strong>" + __("Raw MyDHL response") + "</strong></summary><pre style='max-height:320px;overflow:auto;white-space:pre-wrap;'>" +
			dhl_escape(JSON.stringify(result.response, null, 2)) + "</pre></details>"
		: "";
	return {
		title: result.outcome_unknown ? __("DHL Creation Outcome Unknown") : __("DHL Shipment Creation Failed"),
		indicator: "red",
		message: "<div class='alert alert-danger'><strong>" + dhl_escape(result.message || "") + "</strong><br>" +
			status + environment + "</div>" + messageReference + identifierHtml + errorHtml + rawResponse
	};
}

frappe.ui.form.on("Shipment", {
    refresh: function (frm) {
        if (!is_dhl_express_carrier(frm.doc.carrier)) {
            return;
        }

        frm.add_custom_button(__("Build DHL Draft"), function () {
            frappe.call({
                method: "amf.amf.utils.dhl_shipment.prepare_dhl_shipment_draft",
                args: { shipment: frm.doc },
                freeze: true,
                freeze_message: __("Building DHL draft..."),
                callback: function (response) {
                    if (response.message) {
                        frappe.msgprint(dhl_draft_message(response.message));
                    }
                }
            });
        }, __("DHL Express"));

		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch DHL Transport Products"), function () {
				frappe.call({
					method: "amf.amf.utils.dhl_shipment.get_dhl_shipment_products",
					args: { shipment_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Fetching available DHL transport products..."),
					callback: function (response) {
						const result = response.message;
						if (!result) {
							return;
						}
						if (!result.fetched || !(result.products || []).length) {
							const details = (result.dhl_errors || []).map(error =>
								"<li>" + dhl_escape(error.code ? error.code + ": " : "") + dhl_escape(error.message) + "</li>"
							).join("");
							const local = (result.issues || []).map(issue => "<li>" + dhl_escape(issue.message) + "</li>").join("");
							frappe.msgprint({
								title: __("DHL Product Lookup: Not completed"),
								indicator: "red",
								message: "<p>" + dhl_escape(result.message || "") + "</p>" +
									(details ? "<ul>" + details + "</ul>" : "") + (local ? "<ul>" + local + "</ul>" : "")
							});
							return;
						}

						const products = result.products;
						const productByCode = {};
						products.forEach(product => { productByCode[product.productCode] = product; });
						const rows = products.map(product =>
							"<tr><td><code>" + dhl_escape(product.productCode) + "</code></td><td>" +
							dhl_escape(product.productName || "") + "</td><td>" + dhl_escape(product.networkTypeCode || "") +
							"</td><td>" + dhl_escape(product.estimatedDeliveryDateAndTime || "") + "</td><td>" +
							(product.isCustomerAgreement ? __("Yes") : __("No")) + "</td></tr>"
						).join("");
						const table = "<div class='table-responsive'><table class='table table-bordered table-condensed'>" +
							"<thead><tr><th>" + __("Code") + "</th><th>" + __("DHL product") + "</th><th>" +
							__("Network") + "</th><th>" + __("Estimated delivery") + "</th><th>" +
							__("Customer agreement") + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
						frappe.prompt([
							{
								fieldname: "product_code",
								fieldtype: "Select",
								label: __("DHL Transport Product Code"),
								options: products.map(product => product.productCode).join("\n"),
								reqd: 1,
								description: table
							}
						], function (values) {
							if (productByCode[values.product_code]) {
								frm.set_value("dhl_product_code", values.product_code);
								frappe.show_alert({message: __("DHL transport product selected. Save the Shipment before validation."), indicator: "green"});
							}
						}, __("Available DHL Transport Products") + " — " + result.environment, __("Apply Product"));
					}
				});
			}, __("DHL Express"));
		}

        if (!frm.is_new() && frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Validate Data with DHL"), function () {
                frappe.confirm(
                    __("Send this draft to MyDHL with validateDataOnly=true? This validates data but does not create a shipment or AWB."),
                    function () {
                        frappe.call({
                            method: "amf.amf.utils.dhl_shipment.validate_dhl_shipment_draft",
                            args: { shipment_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Validating data with DHL..."),
                            callback: function (response) {
                                if (response.message) {
                                    frappe.msgprint(dhl_draft_message(response.message));
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("DHL Express"));
        }

		const canCreate = !frm.is_new() && frm.doc.docstatus === 0 &&
			frm.doc.dhl_validation_status === "Validated by DHL" &&
			frm.doc.dhl_validated_payload_hash &&
			!["Creation in progress", "Created", "Creation outcome unknown"].includes(frm.doc.dhl_creation_status || "") &&
			!frm.doc.shipment_id && !frm.doc.awb_number;
		if (canCreate) {
			const createLabel = __("Create DHL Shipment / AWB");
			frm.add_custom_button(createLabel, function () {
				if (frm.is_dirty()) {
					frappe.msgprint({
						title: __("Save and validate first"),
						indicator: "red",
						message: __("This Shipment has unsaved changes. Save it and run DHL validation again before creation.")
					});
					return;
				}
				const pickupEffect = frm.doc.pickup_type === "Pickup"
					? __("The validated payload requests a DHL courier pickup; successful creation may book that pickup.")
					: __("The validated payload does not request a DHL courier pickup.");
				frappe.prompt([
					{
						fieldname: "warning",
						fieldtype: "HTML",
						options: "<div class='alert alert-danger'><strong>" + __("This is an irreversible external operation.") +
							"</strong><br>" + __("MyDHL environment") + ": <strong>" +
							dhl_escape(frm.doc.dhl_validated_environment) + "</strong><br>" + dhl_escape(pickupEffect) +
							"<br>" + __("DHL will generate an AWB and transmit the shipment when the request succeeds.") + "</div>"
					},
					{
						fieldname: "confirmation",
						fieldtype: "Data",
						label: __("Type CREATE DHL SHIPMENT to confirm"),
						reqd: 1
					}
				], function (values) {
					if (values.confirmation !== "CREATE DHL SHIPMENT") {
						frappe.msgprint(__("Confirmation did not match CREATE DHL SHIPMENT. DHL was not contacted."));
						return;
					}
					frappe.call({
						method: "amf.amf.utils.dhl_shipment.create_dhl_shipment",
						args: {
							shipment_name: frm.doc.name,
							confirmation: values.confirmation
						},
						freeze: true,
						freeze_message: __("Creating DHL shipment and AWB..."),
						callback: function (response) {
							if (response.message) {
								frappe.msgprint(dhl_creation_message(response.message));
								frm.reload_doc();
							}
						}
					});
				}, __("Create DHL Shipment") + " — " + frm.doc.dhl_validated_environment, __("Create Shipment / AWB"));
			}, __("DHL Express"));
		}
    }
});
