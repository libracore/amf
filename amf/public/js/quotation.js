// Copyright (c) 2024, libracore and contributors
// For license information, please see license.txt

frappe.ui.form.on("Quotation", {
    refresh: function (frm) {
        window.amf_quotation_product_definition.setup(frm);
    },

    on_submit: function(frm) {
        // update contact status
        if (frm.doc.contact_person) {
            frappe.call({
                'method': 'amf.master_crm.utils.update_status',
                'args': {
                    'contact': frm.doc.contact_person,
                    'status': 'Prospect'
                }
            });
        }
    },

    fill_items_table: function (frm) {
        window.amf_quotation_product_definition.add_selected_product_item(frm);
    },

    item_table: function (frm) {
        window.amf_quotation_product_definition.add_selected_product_item(frm);
    },

    reset: function (frm) {
        window.amf_quotation_product_definition.reset(frm);
    },

    body_filter: function (frm) {
        window.amf_quotation_product_definition.update_preview(frm);
    },

    syringe_code_filter: function (frm) {
        window.amf_quotation_product_definition.update_preview(frm);
    },

    head_filter: function (frm) {
        window.amf_quotation_product_definition.update_preview(frm);
    }
});

window.amf_quotation_product_definition = (function () {
    var HEAD_QUERY = "amf.amf.utils.quotation_product_definition.get_product_definition_head_query";
    var RESOLVE_METHOD = "amf.amf.utils.quotation_product_definition.resolve_product_definition_item";
    var STYLE_ID = "amf-quotation-product-definition-style";

    var LOW_VOLUME_SYRINGES = ["702000", "703000", "704000", "705000", "708000", "709000", "70D000"];
    var HIGH_VOLUME_SYRINGES = ["70E000", "70F000"];

    var RVM_PRODUCTS = {
        rvm_p200: {
            product: "rvm_p200",
            title: "P200-O",
            subtitle: "RVM LP",
            body_code: "511000",
            code_hint: "410___",
            detail: "Rotary valve body"
        },
        rvm_p201: {
            product: "rvm_p201",
            title: "P201-O",
            subtitle: "RVM fast",
            body_code: "521000",
            code_hint: "420___",
            detail: "Fast rotary valve body"
        },
        rvm_p202: {
            product: "rvm_p202",
            title: "P202-O",
            subtitle: "RVM mini",
            body_code: "5D1000",
            code_hint: "4D____",
            detail: "Mini rotary valve body"
        }
    };

    var PUMP_BODIES = {
        "low|standard|oem": {
            body_code: "551000",
            title: "P100-O",
            subtitle: "SPM",
            code_hint: "45____"
        },
        "low|standard|laboratory": {
            body_code: "571000",
            title: "P100-L",
            subtitle: "LSPone",
            code_hint: "47____"
        },
        "low|high_definition|oem": {
            body_code: "591000",
            title: "P110-O",
            subtitle: "SPM HD",
            code_hint: "49____"
        },
        "low|high_definition|laboratory": {
            body_code: "5B1000",
            title: "P110-L",
            subtitle: "LSPone HD",
            code_hint: "4B____"
        },
        "high|standard|oem": {
            body_code: "561000",
            title: "P101-O",
            subtitle: "SPM+",
            code_hint: "46____"
        },
        "high|standard|laboratory": {
            body_code: "581000",
            title: "P101-L",
            subtitle: "LSPone+",
            code_hint: "48____"
        },
        "high|high_definition|oem": {
            body_code: "5A1000",
            title: "P111-O",
            subtitle: "SPM+ HD",
            code_hint: "4A____"
        },
        "high|high_definition|laboratory": {
            body_code: "5C1000",
            title: "P111-L",
            subtitle: "LSPone+ HD",
            code_hint: "4C____"
        }
    };

    var BODY_STATE = {
        "510000": { product: "rvm_p200" },
        "511000": { product: "rvm_p200" },
        "520000": { product: "rvm_p201" },
        "521000": { product: "rvm_p201" },
        "5D0000": { product: "rvm_p202" },
        "5D1000": { product: "rvm_p202" },
        "550000": { product: "pump", volume: "low", definition: "standard", market: "oem" },
        "551000": { product: "pump", volume: "low", definition: "standard", market: "oem" },
        "560000": { product: "pump", volume: "high", definition: "standard", market: "oem" },
        "561000": { product: "pump", volume: "high", definition: "standard", market: "oem" },
        "570000": { product: "pump", volume: "low", definition: "standard", market: "laboratory" },
        "571000": { product: "pump", volume: "low", definition: "standard", market: "laboratory" },
        "580000": { product: "pump", volume: "high", definition: "standard", market: "laboratory" },
        "581000": { product: "pump", volume: "high", definition: "standard", market: "laboratory" },
        "590000": { product: "pump", volume: "low", definition: "high_definition", market: "oem" },
        "591000": { product: "pump", volume: "low", definition: "high_definition", market: "oem" },
        "5A0000": { product: "pump", volume: "high", definition: "high_definition", market: "oem" },
        "5A1000": { product: "pump", volume: "high", definition: "high_definition", market: "oem" },
        "5B0000": { product: "pump", volume: "low", definition: "high_definition", market: "laboratory" },
        "5B1000": { product: "pump", volume: "low", definition: "high_definition", market: "laboratory" },
        "5C0000": { product: "pump", volume: "high", definition: "high_definition", market: "laboratory" },
        "5C1000": { product: "pump", volume: "high", definition: "high_definition", market: "laboratory" }
    };

    var LEGACY_FIELDS = [
        "rvm", "spm", "fast", "slow", "high_volume", "low_volume",
        "high_definition", "standard", "oem", "laboratory",
        "body_filter", "syringe", "syringe_code_filter", "head_filter",
        "reset", "item_table", "drive_code", "drive_head_code1",
        "valve_head_code", "drive_head_code2", "syringe_code",
        "fill_items_table"
    ];

    function setup(frm) {
        if (!frm.fields_dict.product_definition_helper) {
            return;
        }

        ensure_style();
        hide_legacy_fields(frm);
        render(frm);
    }

    function hide_legacy_fields(frm) {
        $.each(LEGACY_FIELDS, function (idx, fieldname) {
            if (frm.fields_dict[fieldname]) {
                frm.set_df_property(fieldname, "hidden", 1);
            }
        });
    }

    function ensure_style() {
        if (document.getElementById(STYLE_ID)) {
            return;
        }

        $("<style id='" + STYLE_ID + "'>")
            .text([
                ".amf-pd{border:1px solid #d9e2ec;border-radius:6px;background:#fff;padding:14px 16px;margin:0 0 12px;}",
                ".amf-pd__top{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:12px;}",
                ".amf-pd__eyebrow{font-size:11px;font-weight:700;text-transform:uppercase;color:#607589;letter-spacing:.02em;}",
                ".amf-pd__title{font-size:15px;font-weight:600;color:#243746;margin-top:2px;}",
                ".amf-pd__grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:12px;}",
                ".amf-pd__card{border:1px solid #cfd9e3;background:#f8fafc;border-radius:6px;text-align:left;padding:10px 11px;min-height:88px;color:#243746;}",
                ".amf-pd__card:hover{border-color:#7aa7d9;background:#f3f8ff;}",
                ".amf-pd__card.is-active{border-color:#2b6cb0;background:#edf6ff;box-shadow:inset 0 0 0 1px #2b6cb0;}",
                ".amf-pd__card-title{font-weight:700;font-size:14px;line-height:1.25;}",
                ".amf-pd__card-subtitle{font-size:12px;color:#536b7f;margin-top:2px;}",
                ".amf-pd__code{display:inline-block;font-family:monospace;font-size:12px;color:#1d5f3f;background:#e8f5ee;border:1px solid #c7e5d2;border-radius:4px;padding:2px 5px;margin-top:8px;}",
                ".amf-pd__body{display:grid;grid-template-columns:1.1fr 1.2fr;gap:12px;align-items:start;}",
                ".amf-pd__panel{border:1px solid #e1e7ee;border-radius:6px;background:#fbfcfe;padding:11px;}",
                ".amf-pd__panel-title{font-size:12px;font-weight:700;text-transform:uppercase;color:#607589;margin-bottom:8px;}",
                ".amf-pd__segments{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-bottom:8px;}",
                ".amf-pd__segment{border:1px solid #cfd9e3;background:#fff;border-radius:5px;padding:7px 9px;text-align:center;font-size:12px;color:#243746;}",
                ".amf-pd__segment.is-active{border-color:#2f855a;background:#ecf8f0;color:#22543d;font-weight:700;}",
                ".amf-pd__selected{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:10px;}",
                ".amf-pd__selected-item{border:1px solid #e1e7ee;border-radius:5px;background:#fff;padding:8px;min-height:56px;}",
                ".amf-pd__label{font-size:11px;color:#607589;text-transform:uppercase;font-weight:700;}",
                ".amf-pd__value{font-size:13px;color:#243746;font-weight:600;margin-top:3px;}",
                ".amf-pd__controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:4px;}",
                ".amf-pd__preview{border-radius:5px;padding:10px;margin-top:10px;border:1px solid #d9e2ec;background:#f8fafc;color:#364a5a;}",
                ".amf-pd__preview.is-ready{border-color:#b7dfc6;background:#eef9f2;color:#22543d;}",
                ".amf-pd__preview.is-warning{border-color:#f0d38a;background:#fff8e5;color:#714b13;}",
                ".amf-pd__preview-code{font-family:monospace;font-weight:700;}",
                ".amf-pd__actions{display:flex;gap:8px;justify-content:flex-end;margin-top:10px;}",
                "@media(max-width:991px){.amf-pd__grid{grid-template-columns:repeat(2,minmax(0,1fr));}.amf-pd__body{grid-template-columns:1fr;}}",
                "@media(max-width:640px){.amf-pd__grid,.amf-pd__selected,.amf-pd__controls{grid-template-columns:1fr;}.amf-pd__top{display:block;}}"
            ].join(""))
            .appendTo("head");
    }

    function render(frm) {
        var wrapper = frm.fields_dict.product_definition_helper.$wrapper;
        var state = get_state(frm);
        var body = get_body_config(state);

        wrapper.html(build_html(state, body));
        bind_events(frm, wrapper);
        make_controls(frm, wrapper, state);
        update_preview(frm);
    }

    function build_html(state, body) {
        var cards = [
            build_product_card("rvm_p200", state),
            build_product_card("rvm_p201", state),
            build_product_card("rvm_p202", state),
            build_product_card("pump", state)
        ].join("");

        return [
            "<div class='amf-pd'>",
            "<div class='amf-pd__top'>",
            "<div>",
            "<div class='amf-pd__eyebrow'>Product selector</div>",
            "<div class='amf-pd__title'>Product Definition</div>",
            "</div>",
            "<div class='amf-pd__code'>" + frappe.utils.escape_html(body ? body.code_hint : "Select product") + "</div>",
            "</div>",
            "<div class='amf-pd__grid'>" + cards + "</div>",
            "<div class='amf-pd__body'>",
            "<div class='amf-pd__panel'>",
            "<div class='amf-pd__panel-title'>Configuration</div>",
            build_pump_options(state),
            build_selected_body(body),
            "</div>",
            "<div class='amf-pd__panel'>",
            "<div class='amf-pd__panel-title'>Selection</div>",
            "<div class='amf-pd__controls'>",
            "<div data-amf-pd-control='syringe'></div>",
            "<div data-amf-pd-control='head'></div>",
            "</div>",
            "<div class='amf-pd__preview' data-amf-pd-preview></div>",
            "<div class='amf-pd__actions'>",
            "<button type='button' class='btn btn-default btn-sm' data-amf-pd-action='reset'>" + __("Reset") + "</button>",
            "<button type='button' class='btn btn-primary btn-sm' data-amf-pd-action='add-item'>" + __("Add Item") + "</button>",
            "</div>",
            "</div>",
            "</div>",
            "</div>"
        ].join("");
    }

    function build_product_card(key, state) {
        var card = key === "pump" ? {
            title: "SPM / LSPone",
            subtitle: "Pump",
            code_hint: "4_____",
            detail: "Syringe pump family"
        } : RVM_PRODUCTS[key];
        var active = state.product === key || (key === "pump" && state.product === "pump");

        return [
            "<button type='button' class='amf-pd__card " + (active ? "is-active" : "") + "' data-amf-pd-product='" + key + "'>",
            "<div class='amf-pd__card-title'>" + frappe.utils.escape_html(card.title) + "</div>",
            "<div class='amf-pd__card-subtitle'>" + frappe.utils.escape_html(card.subtitle) + "</div>",
            "<div class='amf-pd__card-subtitle'>" + frappe.utils.escape_html(card.detail) + "</div>",
            "<span class='amf-pd__code'>" + frappe.utils.escape_html(card.code_hint) + "</span>",
            "</button>"
        ].join("");
    }

    function build_pump_options(state) {
        if (state.product !== "pump") {
            return "";
        }

        return [
            "<div class='amf-pd__segments'>",
            build_segment("volume", "low", "Low volume", state.volume),
            build_segment("volume", "high", "High volume", state.volume),
            "</div>",
            "<div class='amf-pd__segments'>",
            build_segment("definition", "standard", "Standard", state.definition),
            build_segment("definition", "high_definition", "High definition", state.definition),
            "</div>",
            "<div class='amf-pd__segments'>",
            build_segment("market", "oem", "OEM", state.market),
            build_segment("market", "laboratory", "Laboratory", state.market),
            "</div>"
        ].join("");
    }

    function build_segment(group, value, label, current) {
        return [
            "<button type='button' class='amf-pd__segment " + (value === current ? "is-active" : "") + "' ",
            "data-amf-pd-segment-group='" + group + "' data-amf-pd-segment-value='" + value + "'>",
            frappe.utils.escape_html(label),
            "</button>"
        ].join("");
    }

    function build_selected_body(body) {
        return [
            "<div class='amf-pd__selected'>",
            "<div class='amf-pd__selected-item'>",
            "<div class='amf-pd__label'>Body</div>",
            "<div class='amf-pd__value'>" + frappe.utils.escape_html(body ? body.title : "-") + "</div>",
            "</div>",
            "<div class='amf-pd__selected-item'>",
            "<div class='amf-pd__label'>Item family</div>",
            "<div class='amf-pd__value'>" + frappe.utils.escape_html(body ? body.code_hint : "-") + "</div>",
            "</div>",
            "</div>"
        ].join("");
    }

    function bind_events(frm, wrapper) {
        wrapper.find("[data-amf-pd-product]").on("click", function () {
            select_product(frm, $(this).attr("data-amf-pd-product"));
        });

        wrapper.find("[data-amf-pd-segment-group]").on("click", function () {
            select_pump_segment(
                frm,
                $(this).attr("data-amf-pd-segment-group"),
                $(this).attr("data-amf-pd-segment-value")
            );
        });

        wrapper.find("[data-amf-pd-action='reset']").on("click", function () {
            reset(frm);
        });

        wrapper.find("[data-amf-pd-action='add-item']").on("click", function (event) {
            event.preventDefault();
            if (frm._amf_pd_adding_item) {
                return;
            }
            add_selected_product_item(frm);
        });
    }

    function make_controls(frm, wrapper, state) {
        var body = get_body_config(state);
        var show_syringe = state.product === "pump";
        var syringe_parent = wrapper.find("[data-amf-pd-control='syringe']");

        frm._amf_pd_syringe_control = null;
        frm._amf_pd_head_control = null;

        if (show_syringe) {
            frm._amf_pd_syringe_control = make_syringe_control(frm, syringe_parent);
        } else {
            syringe_parent.html([
                "<div class='amf-pd__selected-item'>",
                "<div class='amf-pd__label'>Syringe</div>",
                "<div class='amf-pd__value'>Not required</div>",
                "</div>"
            ].join(""));
            set_field_value(frm, "syringe", "");
            set_field_value(frm, "syringe_code_filter", "");
            set_field_value(frm, "syringe_code", "");
        }

        frm._amf_pd_head_control = make_head_control(
            frm,
            wrapper.find("[data-amf-pd-control='head']"),
            body
        );
    }

    function make_syringe_control(frm, parent) {
        parent.empty();
        var control = frappe.ui.form.make_control({
            parent: parent.get(0),
            render_input: true,
            df: {
                fieldtype: "Link",
                fieldname: "amf_pd_syringe",
                label: __("Syringe"),
                options: "Item",
                reqd: 1,
                get_query: function () {
                    return {
                        filters: {
                            item_code: ["in", get_allowed_syringes(get_state(frm))],
                            disabled: 0
                        }
                    };
                },
                onchange: function () {
                    var value = control.get_value();
                    set_field_value(frm, "syringe", value || "");
                    set_field_value(frm, "syringe_code_filter", value || "");
                    set_field_value(frm, "syringe_code", value || "");
                    update_preview(frm);
                }
            }
        });

        control.set_value(frm.doc.syringe_code_filter || frm.doc.syringe_code || "");
        return control;
    }

    function make_head_control(frm, parent, body) {
        parent.empty();
        var control = frappe.ui.form.make_control({
            parent: parent.get(0),
            render_input: true,
            df: {
                fieldtype: "Link",
                fieldname: "amf_pd_head",
                label: __("Valve Head"),
                options: "Item",
                reqd: 1,
                get_query: function () {
                    return {
                        query: HEAD_QUERY,
                        filters: {
                            body_item_code: body ? body.body_code : "",
                            syringe_item_code: get_state(frm).product === "pump" ? (frm.doc.syringe_code_filter || "") : ""
                        }
                    };
                },
                onchange: function () {
                    var value = control.get_value();
                    set_field_value(frm, "head_filter", value || "");
                    set_field_value(frm, "valve_head_code", value || "");
                    update_preview(frm);
                }
            }
        });

        control.set_value(frm.doc.head_filter || frm.doc.valve_head_code || "");
        return control;
    }

    function select_product(frm, product) {
        var state = get_state(frm);

        if (product === "pump") {
            state.product = "pump";
            state.volume = state.volume || "low";
            state.definition = state.definition || "standard";
            state.market = state.market || "oem";
        } else {
            state = {
                product: product,
                volume: "low",
                definition: "standard",
                market: "oem"
            };
        }

        set_current_state(frm, state);
        apply_state(frm, state);
        render(frm);
    }

    function select_pump_segment(frm, group, value) {
        var state = get_state(frm);
        state.product = "pump";
        state[group] = value;
        set_current_state(frm, state);
        apply_state(frm, state);
        render(frm);
    }

    function apply_state(frm, state) {
        var body = get_body_config(state);
        var allowed_syringes = get_allowed_syringes(state);
        var syringe = frm.doc.syringe_code_filter || frm.doc.syringe_code || "";

        if (state.product !== "pump" || allowed_syringes.indexOf(syringe) === -1) {
            syringe = "";
        }

        set_current_state(frm, state);
        set_field_value(frm, "rvm", state.product && state.product !== "pump" ? 1 : 0);
        set_field_value(frm, "spm", state.product === "pump" ? 1 : 0);
        set_field_value(frm, "fast", state.product === "rvm_p201" ? 1 : 0);
        set_field_value(frm, "slow", state.product === "rvm_p200" ? 1 : 0);
        set_field_value(frm, "high_volume", state.product === "pump" && state.volume === "high" ? 1 : 0);
        set_field_value(frm, "low_volume", state.product === "pump" && state.volume === "low" ? 1 : 0);
        set_field_value(frm, "high_definition", state.product === "pump" && state.definition === "high_definition" ? 1 : 0);
        set_field_value(frm, "standard", state.product === "pump" && state.definition === "standard" ? 1 : 0);
        set_field_value(frm, "oem", state.product === "pump" && state.market === "oem" ? 1 : 0);
        set_field_value(frm, "laboratory", state.product === "pump" && state.market === "laboratory" ? 1 : 0);
        set_field_value(frm, "body_filter", body ? body.body_code : "");
        set_field_value(frm, "drive_code", body ? body.body_code : "");
        set_field_value(frm, "syringe", syringe);
        set_field_value(frm, "syringe_code_filter", syringe);
        set_field_value(frm, "syringe_code", syringe);
    }

    function set_current_state(frm, state) {
        frm._amf_pd_state = $.extend({
            product: "",
            volume: "low",
            definition: "standard",
            market: "oem"
        }, state || {});
    }

    function get_state(frm) {
        if (frm._amf_pd_state) {
            return $.extend({}, frm._amf_pd_state);
        }

        var body_code = frm.doc.body_filter || frm.doc.drive_code || "";
        var from_body = BODY_STATE[body_code];

        if (from_body) {
            set_current_state(frm, $.extend(
                {
                    volume: "low",
                    definition: "standard",
                    market: "oem"
                },
                from_body
            ));
            return $.extend({}, frm._amf_pd_state);
        }

        if (cint(frm.doc.spm)) {
            set_current_state(frm, {
                product: "pump",
                volume: cint(frm.doc.high_volume) ? "high" : "low",
                definition: cint(frm.doc.high_definition) ? "high_definition" : "standard",
                market: cint(frm.doc.laboratory) ? "laboratory" : "oem"
            });
            return $.extend({}, frm._amf_pd_state);
        }

        if (cint(frm.doc.rvm)) {
            set_current_state(frm, {
                product: cint(frm.doc.fast) ? "rvm_p201" : (cint(frm.doc.slow) ? "rvm_p200" : "rvm_p202"),
                volume: "low",
                definition: "standard",
                market: "oem"
            });
            return $.extend({}, frm._amf_pd_state);
        }

        set_current_state(frm, {
            product: "",
            volume: "low",
            definition: "standard",
            market: "oem"
        });
        return $.extend({}, frm._amf_pd_state);
    }

    function get_body_config(state) {
        if (!state || !state.product) {
            return null;
        }

        if (state.product === "pump") {
            return PUMP_BODIES[[state.volume, state.definition, state.market].join("|")];
        }

        return RVM_PRODUCTS[state.product] || null;
    }

    function get_allowed_syringes(state) {
        if (!state || state.product !== "pump") {
            return [];
        }

        return state.volume === "high" ? HIGH_VOLUME_SYRINGES : LOW_VOLUME_SYRINGES;
    }

    function set_field_value(frm, fieldname, value) {
        if (!frm.fields_dict[fieldname]) {
            frm.doc[fieldname] = value;
            return Promise.resolve();
        }

        if ((frm.doc[fieldname] || "") === (value || "")) {
            return Promise.resolve();
        }

        var result = frm.set_value(fieldname, value);
        frm.doc[fieldname] = value;
        return result && result.then ? result : Promise.resolve();
    }

    function update_preview(frm) {
        var wrapper = get_wrapper(frm);
        if (!wrapper || !wrapper.length) {
            return Promise.resolve(null);
        }

        return resolve_current_product_item(frm, false, { force: true, render: true });
    }

    function get_current_selection(frm) {
        var state = get_state(frm);
        var body = get_body_config(state);
        var head = get_head_value(frm);
        var syringe = state.product === "pump" ? get_syringe_value(frm) : "";

        return {
            state: state,
            body: body,
            head: head,
            syringe: syringe,
            key: [body ? body.body_code : "", head || "", syringe || ""].join("|")
        };
    }

    function resolve_current_product_item(frm, show_messages, options) {
        options = options || {};
        var selection = get_current_selection(frm);
        var state = selection.state;
        var body = selection.body;
        var head = selection.head;
        var syringe = selection.syringe;

        if (frm._amf_pd_resolve_key !== selection.key) {
            frm._amf_pd_resolved_item = null;
            frm._amf_pd_resolve_key = null;
        }

        if (!body) {
            frm._amf_pd_resolved_item = null;
            frm._amf_pd_resolve_key = null;
            frm._amf_pd_resolve_request_id = (frm._amf_pd_resolve_request_id || 0) + 1;
            render_preview(frm, "warning", "Select a product.");
            return Promise.resolve(null);
        }

        if (state.product === "pump" && !syringe) {
            frm._amf_pd_resolved_item = null;
            frm._amf_pd_resolve_key = null;
            frm._amf_pd_resolve_request_id = (frm._amf_pd_resolve_request_id || 0) + 1;
            render_preview(frm, "warning", "Select a syringe.");
            return Promise.resolve(null);
        }

        if (!head) {
            frm._amf_pd_resolved_item = null;
            frm._amf_pd_resolve_key = null;
            frm._amf_pd_resolve_request_id = (frm._amf_pd_resolve_request_id || 0) + 1;
            render_preview(frm, "warning", "Select a valve head.");
            return Promise.resolve(null);
        }

        if (!options.force && frm._amf_pd_resolved_item && frm._amf_pd_resolve_key === selection.key) {
            if (options.render !== false) {
                render_resolved_item(frm, frm._amf_pd_resolved_item);
            }
            return Promise.resolve(frm._amf_pd_resolved_item);
        }

        var request_id = (frm._amf_pd_resolve_request_id || 0) + 1;
        frm._amf_pd_resolve_request_id = request_id;

        if (options.render !== false) {
            render_preview(frm, "", "Resolving item...");
        }

        return new Promise(function (resolve) {
            var request = frappe.call({
                method: RESOLVE_METHOD,
                args: {
                    body_item_code: body.body_code,
                    head_item_code: head,
                    syringe_item_code: syringe
                },
                callback: function (response) {
                    var item = response.message || {};
                    var still_current = get_current_selection(frm).key === selection.key;

                    if (!still_current) {
                        resolve(null);
                        return;
                    }

                    if (item.item_code && !item.missing && !item.error) {
                        frm._amf_pd_resolved_item = item;
                        frm._amf_pd_resolve_key = selection.key;
                        if (options.render !== false && frm._amf_pd_resolve_request_id === request_id) {
                            render_resolved_item(frm, item);
                        }
                        resolve(item);
                        return;
                    }

                    if (options.render !== false && frm._amf_pd_resolve_request_id === request_id) {
                        render_missing_item(frm, item);
                    }
                    if (show_messages) {
                        frappe.msgprint(__("No active Item was found for the selected product definition."));
                    }
                    resolve(null);
                }
            });

            if (request && request.fail) {
                request.fail(function () {
                    if (options.render !== false && frm._amf_pd_resolve_request_id === request_id) {
                        render_preview(frm, "warning", "Could not resolve the selected product.");
                    }
                    if (show_messages) {
                        frappe.msgprint(__("Could not resolve the selected product. Please try again."));
                    }
                    resolve(null);
                });
            }
        });
    }

    function render_resolved_item(frm, item) {
        render_preview(
            frm,
            "ready",
            "<span class='amf-pd__preview-code'>" + frappe.utils.escape_html(item.item_code) + "</span> " +
            frappe.utils.escape_html(item.item_name || "")
        );
    }

    function render_missing_item(frm, item) {
        var expected = item && item.expected_reference_code ? item.expected_reference_code : "-";
        var fallback = item && item.fallback_item_code ? item.fallback_item_code : "-";
        render_preview(
            frm,
            "warning",
            "No active Item found. Reference " +
            frappe.utils.escape_html(expected) +
            ", code " +
            frappe.utils.escape_html(fallback) +
            "."
        );
    }

    function render_preview(frm, status, html) {
        var wrapper = get_wrapper(frm);
        var preview = wrapper.find("[data-amf-pd-preview]");
        var add_button = wrapper.find("[data-amf-pd-action='add-item']");

        preview
            .removeClass("is-ready is-warning")
            .addClass(status === "ready" ? "is-ready" : (status === "warning" ? "is-warning" : ""))
            .html(html || "");

        add_button.prop("disabled", !!frm._amf_pd_adding_item);
    }

    function get_wrapper(frm) {
        if (!frm.fields_dict.product_definition_helper) {
            return $();
        }
        return frm.fields_dict.product_definition_helper.$wrapper;
    }

    function get_head_value(frm) {
        if (frm._amf_pd_head_control) {
            return frm._amf_pd_head_control.get_value();
        }
        return frm.doc.head_filter || frm.doc.valve_head_code || "";
    }

    function get_syringe_value(frm) {
        if (frm._amf_pd_syringe_control) {
            return frm._amf_pd_syringe_control.get_value();
        }
        return frm.doc.syringe_code_filter || frm.doc.syringe_code || "";
    }

    function reset(frm) {
        var clear_values = {
            rvm: 0,
            spm: 0,
            fast: 0,
            slow: 0,
            high_volume: 0,
            low_volume: 0,
            high_definition: 0,
            standard: 0,
            oem: 0,
            laboratory: 0,
            body_filter: "",
            syringe: "",
            syringe_code_filter: "",
            head_filter: "",
            drive_code: "",
            valve_head_code: "",
            syringe_code: ""
        };

        $.each(clear_values, function (fieldname, value) {
            set_field_value(frm, fieldname, value);
        });

        set_current_state(frm, {});
        frm._amf_pd_resolved_item = null;
        frm._amf_pd_resolve_key = null;
        render(frm);
    }

    function add_selected_product_item(frm) {
        if (frm._amf_pd_adding_item) {
            return Promise.resolve();
        }

        frm._amf_pd_adding_item = true;
        set_add_button_busy(frm, true);

        return resolve_current_product_item(frm, true, { render: true }).then(function (item) {
            if (!item || !item.item_code) {
                return;
            }

            if (has_item_row(frm, item.item_code)) {
                frappe.msgprint({
                    title: __("Item already present"),
                    indicator: "orange",
                    message: __("Item {0} is already in the table.", [item.item_code])
                });
                return;
            }

            var row = frm.add_child("items");
            frm.refresh_field("items");

            return make_add_item_task(row, item)().then(function () {
                frm.refresh_field("items");
                frappe.show_alert({
                    message: __("Item added: {0}", [item.item_code]),
                    indicator: "green"
                });
            });
        }).then(null, function () {
            frappe.msgprint(__("Could not add the selected item. Please try again."));
        }).then(function () {
            frm._amf_pd_adding_item = false;
            set_add_button_busy(frm, false);
            update_preview(frm);
        });
    }

    function set_add_button_busy(frm, busy) {
        var button = get_wrapper(frm).find("[data-amf-pd-action='add-item']");
        if (!button.length) {
            return;
        }

        button
            .prop("disabled", !!busy)
            .text(busy ? __("Adding...") : __("Add Item"));
    }

    function has_item_row(frm, item_code) {
        var found = false;

        $.each(frm.doc.items || [], function (idx, row) {
            if ((row.item_code || "").toUpperCase() === (item_code || "").toUpperCase()) {
                found = true;
                return false;
            }
        });

        return found;
    }

    function make_add_item_task(row, item) {
        return function () {
            return frappe.run_serially([
                function () {
                    return frappe.model.set_value(row.doctype, row.name, "item_code", item.item_code);
                },
                function () {
                    return frappe.after_ajax();
                },
                function () {
                    return set_child_value_if_exists(row, "qty", 1);
                },
                function () {
                    if (!row.item_name) {
                        return set_child_value_if_exists(row, "item_name", item.item_name || item.item_code);
                    }
                },
                function () {
                    if (!row.description) {
                        return set_child_value_if_exists(row, "description", item.item_name || item.item_code);
                    }
                },
                function () {
                    return frappe.after_ajax();
                }
            ]);
        };
    }

    function set_child_value_if_exists(row, fieldname, value) {
        if (frappe.meta.has_field(row.doctype, fieldname)) {
            return frappe.model.set_value(row.doctype, row.name, fieldname, value);
        }

        return Promise.resolve();
    }

    return {
        setup: setup,
        reset: reset,
        update_preview: update_preview,
        add_selected_product_item: add_selected_product_item
    };
}());
