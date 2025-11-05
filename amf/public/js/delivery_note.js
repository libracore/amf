// Copyright (c) 2024, libracore and contributors
// For license information, please see license.txt

const eur1form_note = __('You have not entered the EUR.1 form number. If an EUR.1 form is not necessary for this shipment, please indicate below with a check mark.');

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

        // show dashboard note
        if ((frm.doc.eur1_form_not_required === 0) && (!frm.doc.eur1_form)) {
            cur_frm.dashboard.add_comment(eur1form_note, 'yellow', true);
        }
    },
    before_submit: function (frm) {
        // validate eur.1 form
        if ((frm.doc.eur1_form_not_required === 0) && (!frm.doc.eur1_form)) {
            frappe.msgprint({
                indicator: 'red',
                title: __('Validation'),
                message: eur1form_note
            });
            frappe.validated = false;
        }
    }
});

// // Client Script | Doctype: Delivery Note (ERPNext v12)
// // Purpose: Set Delivery Note Item.customs_tariff_number_ based on destination country and item category
// // Notes:
// // - Country is taken from the Shipping Address on the Delivery Note (fallback to Customer's primary address).
// // - Category detection tries, in order: explicit map by item_code, then by item_group, then by item_name keywords.
// // - If no category match is found, the row is left unchanged (and a console note is printed).
// // - Edit CATEGORY_MATCHERS to plug-in your exact item_code/item_group taxonomy for perfect matching.

// // --------------------------- CONFIGURATION ---------------------------

// // Mapping of HS/TARIC/etc by category and destination bloc.
// // Keep values exactly as you want them to appear in the child field.
// const HS_MAP = {
//     "SPM + LSPone": { US: "8413.50.0090", EU: "8413 50 40 90", CH: "8413.50.00", GB: "8413 50 40 00", CN: "8413 50 90", JP: "8413.50" },
//     "RVM": { US: "8481.80.9050", EU: "8481 80 99 70", CH: "8481.80.00", GB: "8481 80 99 00", CN: "8481 80 00", JP: "8481.80" },
//     "Valve Head": { US: "8481.90.9060", EU: "8481 80 90 05", CH: "8481.90.00", GB: "8481 90 90 60", CN: "8481 90 00", JP: "8481 90.000" },
//     "USB Cable (C101)": { US: "8544.42.9090", EU: "8544 42 90 00", CH: "8544.42.00", GB: "8544 42 90 00", CN: "8544 42 90", JP: "8544.42" },
//     "C102, DB9 Adaptor": { US: "8536.69.8000", EU: "8536 69 90 99", CH: "8536.69.00", GB: "8536 69 90 00", CN: "8536 69 90", JP: "8536.69" },
//     "Power Cord": { US: "8544.49.2000", EU: "8544 42 90 00", CH: "8544.42.00", GB: "8544 42 90 00", CN: "8544 42 90", JP: "8544.42" },
//     "Quick Start Kit": { US: "3917.40.0095", EU: "3917 40 00 95", CH: "3917.40.00", GB: "3917 40 00 00", CN: "3917 40 00", JP: "3917.40.000" },
//     "Syringe Change Tool - T100": { US: "8205.59.8000", EU: "8205 59 80 00", CH: "8205.59.00", GB: "8205 59 80 00", CN: "8205 59 00", JP: "8205.59.000" },
//     "C100 Power Supply": { US: "8504.40.9540", EU: "8504 40 90 90", CH: "8504.40.00", GB: "8504 40 99 90", CN: "8504 40 90", JP: "8504.40" },
//     "Syringe": { US: "7017.90.5000", EU: "7017 90 00 00", CH: null, GB: null, CN: null, JP: null } // Fill missing if needed
// };

// // Countries that map to the EU TARIC column.
// const EU_COUNTRIES = new Set([
//     "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Denmark", "Estonia", "Finland", "France",
//     "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands",
//     "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden"
// ]);

// // Optional: hard map known item_codes or item_groups directly to a category from HS_MAP
// // This is the most reliable way. Add your real codes/groups here.
// const DIRECT_ITEM_CODE_TO_CATEGORY = {
//     // e.g. "510000": "SPM + LSPone",
//     //       "C101": "USB Cable (C101)",
//     //       "C102": "C102, DB9 Adaptor",
//     //       "C100": "C100 Power Supply",
// };

// const DIRECT_ITEM_GROUP_TO_CATEGORY = {
//     // e.g. "Pumps": "SPM + LSPone",
//     //       "Rotary Valve Modules": "RVM",
//     //       "Valve Heads": "Valve Head",
//     //       "Cables": "Power Cord",
// };

// // Fallback keyword matchers against item_name (lowercased): first match wins
// const CATEGORY_MATCHERS = [
//     { cat: "SPM + LSPone", keywords: ["spm", "lspone", "lsp one", "syringe pump", "p1"] },
//     { cat: "RVM", keywords: ["rvm", "rotary valve module", "p2"] },
//     { cat: "Valve Head", keywords: ["valve head", "vh-", "V-"] },
//     { cat: "USB Cable (C101)", keywords: ["c101", "usb cable", "usb-cable"] },
//     { cat: "C102, DB9 Adaptor", keywords: ["c102", "db9", "rs232", "adapter", "adaptor"] },
//     { cat: "Power Cord", keywords: ["power cord", "mains cable", "power cable"] },
//     { cat: "Quick Start Kit", keywords: ["quick start kit", "qsk", "k-"] },
//     { cat: "Syringe Change Tool - T100", keywords: ["t100", "syringe change tool"] },
//     { cat: "C100 Power Supply", keywords: ["c100", "power supply", "psu", "c100"] },
//     { cat: "Syringe", keywords: ["syringe"] },
// ];

// // --------------------------- HELPERS ---------------------------

// async function get_country_from_address_name(address_name) {
//     if (!address_name) return null;
//     try {
//         const r = await frappe.db.get_value("Address", address_name, "country");
//         return (r && r.message && r.message.country) ? r.message.country : null;
//     } catch (e) {
//         console.warn("Address lookup failed:", e);
//         return null;
//     }
// }

// async function get_customer_primary_country(customer) {
//     if (!customer) return null;
//     try {
//         const addrResp = await frappe.db.get_value("Customer", customer, "customer_primary_address");
//         const primary = addrResp?.message?.customer_primary_address;
//         if (!primary) return null;
//         return await get_country_from_address_name(primary);
//     } catch (e) {
//         console.warn("Customer primary address lookup failed:", e);
//         return null;
//     }
// }

// function country_to_bloc(country) {
//     if (!country) return null;
//     if (country === "United States" || country === "United States of America" || country === "USA") return "US";
//     if (country === "Switzerland") return "CH";
//     if (country === "United Kingdom" || country === "Great Britain" || country === "UK") return "GB";
//     if (country === "China") return "CN";
//     if (country === "Japan") return "JP";
//     if (EU_COUNTRIES.has(country)) return "EU";
//     return null; // Unknown bloc -> no auto-fill
// }

// function detect_category_for_item(child) {
//     const code = (child.item_code || "").trim();
//     const group = (child.item_group || "").trim();
//     const nameL = (child.item_name || child.description || "").toLowerCase();

//     if (DIRECT_ITEM_CODE_TO_CATEGORY[code]) return DIRECT_ITEM_CODE_TO_CATEGORY[code];
//     if (DIRECT_ITEM_GROUP_TO_CATEGORY[group]) return DIRECT_ITEM_GROUP_TO_CATEGORY[group];

//     for (const m of CATEGORY_MATCHERS) {
//         if (m.keywords.some(k => nameL.includes(k))) return m.cat;
//     }
//     return null;
// }

// function get_hs_for(category, bloc) {
//     if (!category || !bloc) return null;
//     const row = HS_MAP[category];
//     if (!row) return null;
//     return row[bloc] || null;
// }

// // --------------------------- MAIN HOOK ---------------------------

// frappe.ui.form.on("Delivery Note", {
//     async before_save(frm) {
//         try {
//             console.log("before_save HS code algorithm...")
//             // Resolve shipping country
//             let country = await get_country_from_address_name(frm.doc.shipping_address_name);
//             if (!country) country = await get_country_from_address_name(frm.doc.customer_address);
//             if (!country) country = await get_customer_primary_country(frm.doc.customer);

//             const bloc = country_to_bloc(country);

//             if (!bloc) {
//                 console.warn("[HS AutoFill] Destination country not mapped to a bloc (US/EU/CH/GB/CN/JP). No changes applied.");
//                 return;
//             }

//             // Iterate items and set customs_tariff_number_ where we can determine a category & HS
//             (frm.doc.items || []).forEach(d => {
//                 const category = detect_category_for_item(d);
//                 const hs = get_hs_for(category, bloc);

//                 if (hs) {
//                     // Use model.set_value to ensure child grid is marked dirty and validated
//                     frappe.model.set_value(d.doctype, d.name, "customs_tariff_number_", hs);
//                 } else {
//                     // Leave untouched when unknown (do not overwrite manual value)
//                     if (!category) {
//                         console.info(`[HS AutoFill] No category match for item_code=${d.item_code} name=${d.item_name}.`);
//                     } else {
//                         console.info(`[HS AutoFill] No HS code for category='${category}' and bloc='${bloc}'.`);
//                     }
//                 }
//             });
//         } catch (e) {
//             // Fail-safe: never block saving for HS autofill errors
//             console.error("[HS AutoFill] Unexpected error:", e);
//         }
//     }
// });
