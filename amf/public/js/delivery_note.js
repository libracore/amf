// Copyright (c) 2024, libracore and contributors
// For license information, please see license.txt

frappe.ui.form.on("Delivery Note", {
    refresh: function (frm) {
        // attach tooltip for EUR.1 form
        const description = "Fill out a paper EUR.1 form and place it on the package if the following criteria are met:\n\n"
            + "1. The destination is in the EU\n"
            + "2. The value exceeds €6,000, OR\n"
            + "3. The value exceeds 10,000 CHF";
        const tooltip = "&nbsp;<i class='fa fa-info' title='" + description + "'></i>";
        let labels = document.getElementsByClassName('control-label');
        for (let i = 0; i < labels.length; i++) {
            if (labels[i].innerHTML == "EUR.1 form number") {
                labels[i].innerHTML += tooltip;
            }
        }
        
    },
    validate: function (frm) {
        // validate eur.1 form
        if ((frm.doc.eur1_form_not_required === 0) && (!frm.doc.eur1_form)) {
            frappe.msgprint({
                indicator: 'red',
                title: __('Validation'),
                message: __('You have not entered the EUR.1 form number. If an EUR.1 form is not necessary for this shipment, please indicate below with a check mark.')
            });
            frappe.validated = false;
        }
    }
});
