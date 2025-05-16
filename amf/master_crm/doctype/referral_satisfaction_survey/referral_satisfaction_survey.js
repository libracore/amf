// Copyright (c) 2025, libracore AG and contributors
// For license information, please see license.txt

frappe.ui.form.on('Referral Satisfaction Survey', {
    refresh: (frm) => {
        // Optional: put any logic you need on form load here
    },

    before_submit: (frm) => {
        // Build a meaningful title based on which contacts/orgs are present
        const { referred_contact_name, referred_organization_name, referring_organization_name } = frm.doc;

        if (referred_contact_name && referred_organization_name) {
            frm.set_value('title', `${referred_contact_name} for ${referred_organization_name}`);
        } else {
            frm.set_value('title', `Referral for ${referring_organization_name || ''}`);
        }
    },

    contact_person: (frm) => {
        // Clear the display field if the link itself is removed
        if (!frm.doc.contact_person) {
            frm.set_value('referred_contact_name', '');
        }
    },

    // Whenever the referring OR referred organization field changes,
    // fetch the matching contacts and set the query for the corresponding contact field.
    referred_organization: (frm) => {
        _handleOrgChange({
            frm,
            orgField: 'referred_organization',
            nameField: 'referred_organization_name',
            contactField: 'contact_person'
        });
    },

    referring_organization: (frm) => {
        _handleOrgChange({
            frm,
            orgField: 'referring_organization',
            nameField: 'referring_organization_name',
            contactField: 'referring_contact'
        });
    }
});

/**
 * Shared helper to:
 * 1. Clear the display-name field if the org-link is empty
 * 2. Fetch contacts linked to that org via our whitelisted Python method
 * 3. Apply a set_query filter on the target contact field
 *
 * @param {object}         params
 * @param {frappe.ui.form} params.frm
 * @param {string}         params.orgField      - e.g. 'referred_organization'
 * @param {string}         params.nameField     - e.g. 'referred_organization_name'
 * @param {string}         params.contactField  - e.g. 'contact_person' or 'referring_contact'
 */
function _handleOrgChange({ frm, orgField, nameField, contactField }) {
    const customer = frm.doc[orgField];

    // 1) Clear the display-name if the link is removed
    if (!customer) {
        frm.set_value(nameField, '');
        // also clear any previous contact selection or filter
        frm.set_value(contactField, Array.isArray(frm.doc[contactField]) ? [] : '');
        frm.set_query(contactField, null);
        return;
    }

    // 2) Call server to get an array of contact names
    frappe.call({
        method: 'amf.master_crm.utils.get_referring_contacts',
        args: { customer },
        callback: ({ message: contacts = [] }) => {
            if (contacts.length) {
                // 3a) Restrict the contact-field picklist to only those names
                frm.set_query(contactField, () => ({
                    filters: [
                        ['Contact', 'name', 'in', contacts]
                    ]
                }));

            } else {
                // 3b) No contacts → remove any custom filter so user sees all
                frm.set_query(contactField, null);
            }
        }
    });
}