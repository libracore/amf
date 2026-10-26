/* Frappe v12 calls save callbacks with null after a non-JSON response.
 * Keep that transport failure from crashing the form or claiming a save.
 */
(function () {
    "use strict";

    if (frappe.call.__amf_stock_reconciliation_transport) {
        return;
    }

    const original_call = frappe.call;
    const save_method = "frappe.desk.form.save.savedocs";
    const cancel_method = "frappe.desk.form.save.cancel";

    function is_reconciliation_save(options) {
        if (!options || typeof options !== "object" || !options.args) {
            return false;
        }
        if (options.method === cancel_method) {
            return options.args.doctype === "Stock Reconciliation";
        }
        if (options.method !== save_method) {
            return false;
        }
        let doc = options.args.doc;
        if (typeof doc === "string") {
            try {
                doc = JSON.parse(doc);
            } catch (error) {
                return false;
            }
        }
        return doc && doc.doctype === "Stock Reconciliation";
    }

    function guarded_call(options) {
        if (!is_reconciliation_save(options)) {
            return original_call.apply(this, arguments);
        }

        let warned = false;
        let failed = false;
        let callback_called = false;
        let last_response = null;
        const callback = options.callback;
        const error_callback = options.error;

        function unconfirmed_response() {
            failed = true;
            if (!warned) {
                warned = true;
                frappe.msgprint({
                    title: __("Save confirmation unavailable"),
                    indicator: "orange",
                    message: __(
                        "The server did not return a valid save confirmation. Reload this Stock Reconciliation and check its status before trying again."
                    ),
                });
            }
            return {exc: "SaveConfirmationUnavailable"};
        }

        function response_or_error(response, is_error) {
            if (response && response.responseJSON) {
                response = response.responseJSON;
            }
            if (!response || typeof response !== "object" || Array.isArray(response)) {
                return unconfirmed_response();
            }
            if (response.exc || response.exc_type) {
                failed = true;
                last_response = response.exc ? response : Object.assign({}, response, {exc: true});
                return last_response;
            }
            const saved = Array.isArray(response.docs) && response.docs.some(
                (doc) => doc && doc.doctype === "Stock Reconciliation"
            );
            if (!is_error && !failed && saved) {
                last_response = response;
                return response;
            }
            if (response._server_messages) {
                failed = true;
                last_response = Object.assign({}, response, {exc: true});
                return last_response;
            }
            return unconfirmed_response();
        }

        const guarded = Object.assign({}, options, {
            callback: function (response, response_text) {
                callback_called = true;
                return callback && callback.call(this, response_or_error(response, false), response_text);
            },
            error: function (response) {
                callback_called = true;
                return error_callback && error_callback.call(this, response_or_error(response || last_response, true));
            },
            always: function (response) {
                const safe_response = response_or_error(response, false);
                // A malformed HTTP 200 response or offline request can skip
                // both normal callbacks. Complete the form's failure path too.
                if (warned && !callback_called) {
                    callback_called = true;
                    if (error_callback) {
                        error_callback.call(this, safe_response);
                    } else if (callback) {
                        callback.call(this, safe_response);
                    }
                }
                return options.always && options.always.call(this, safe_response);
            },
        });
        return original_call.call(this, guarded);
    }

    guarded_call.__amf_stock_reconciliation_transport = true;
    frappe.call = guarded_call;
}());
