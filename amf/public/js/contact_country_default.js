/* Frappe V12 applies global Country defaults even when df.default is empty.
 * Resolve just this field before full form / Quick Entry creation, so explicit
 * country values from a user or a caller are preserved.
 */
(function () {
    var original = frappe.model.get_default_value;
    frappe.model.get_default_value = function (df, doc, parent_doc) {
        if (doc.doctype === 'Contact' && df.fieldname === 'country') {
            return '';
        }
        return original.call(this, df, doc, parent_doc);
    };
}());
