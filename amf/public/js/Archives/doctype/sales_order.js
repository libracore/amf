/*
Sales Order Script
--------------------

What this does:
* Handles click on "Add shipping and taxes" button:
    * Empties taxes table
    * Replaces by two items: first item shipping, second item VAT (applies to previous total)

*/
frappe.ui.form.on("Sales Order", {
    /*
    before_save: function (frm) {
        // If sales_order_type is not set and at least one item contains 'GX'
        if (!frm.doc.sales_order_type && frm.doc.items.some(item => item.item_code.includes('GX'))) {
            frm.set_value('sales_order_type', 'R&D');
        } else if (!frm.doc.sales_order_type && !frm.doc.items.some(item => item.item_code.includes('GX'))) {
            frm.set_value('sales_order_type', 'Production');
        }
    },
    */

    refresh: function (frm) {

        // If sales_order_type is not set and at least one item contains 'GX'
        if (frm.doc.items.some(item => item.item_code.includes('GX'))) {
            frm.set_value('sales_order_type', 'R&D');
        } else if (!frm.doc.items.some(item => item.item_code.includes('GX'))) {
            frm.set_value('sales_order_type', 'Production');
        }

        /* remove button "Multiple Variants"
        var $group = cur_frm.page.get_inner_group_button("Create");
        for (i = 0; i < $group.find(".dropdown-menu").children("li").length; i++) {
            var li = $group.find(".dropdown-menu").children("li")[i]; 
            if (li.getElementsByTagName("a")[0].innerHTML == __("Work Order")) {
                $group.find(".dropdown-menu").children("li")[i].remove();
            }
        }
        */

        frm.add_custom_button(__("Work Order Creation"), function () {
            // start your function
            frm.call({
                //doc: frm.doc,
                method: 'amf.amf.utils.bom_creation.get_wo_items',
                args: {
                    sales_order: frm.doc.name
                },
                callback: function (r) {
                    if (!r.message) {
                        frappe.msgprint({
                            title: __('Work Order not created'),
                            message: __('No Items with Bill of Materials to Manufacture'),
                            indicator: 'orange'
                        });
                        return;
                    }
                    else if (!r.message) {
                        frappe.msgprint({
                            title: __('Work Order not created'),
                            message: __('Work Order already created for all items with BOM'),
                            indicator: 'orange'
                        });
                        return;
                    } else {
                        // For each item, call an API to fetch its stock balance and then display it
                        let fetchPromises = r.message.map(function (item) {
                            return frappe.call({
                                method: 'amf.amf.utils.bom_creation.get_stock_balance_for_all_warehouses',
                                args: {
                                    item_code: item.item_code,
                                },
                                callback: function (response) {
                                    item.stock_balance = Object.entries(response.message)
                                        .map(([wh, qty]) => `${wh}: ${qty}`)
                                        .join(' • ');
                                }
                            });
                        });

                        Promise.all(fetchPromises).then(() => {
                            const fields = [{
                                label: 'Items',
                                fieldtype: 'Table',
                                fieldname: 'items',
                                description: __('Select BOM & Quantity for Production'),
                                fields: [{
                                    fieldtype: 'Read Only',
                                    fieldname: 'item_code',
                                    label: __('Item Code'),
                                    in_list_view: 1
                                }, {
                                    fieldtype: 'Link',
                                    fieldname: 'bom',
                                    options: 'BOM',
                                    reqd: 1,
                                    label: __('Select BOM'),
                                    in_list_view: 1,
                                    hidden: 1,
                                    get_query: function (doc) {
                                        return { filters: { item: doc.item_code } };
                                    }
                                }, {
                                    // Add your stock_balance field here
                                    fieldtype: 'Read Only',
                                    fieldname: 'stock_balance',
                                    reqd: 1,
                                    label: __('Stock Balance'),
                                    in_list_view: 1
                                }, {
                                    fieldtype: 'Float',
                                    fieldname: 'pending_qty',
                                    reqd: 1,
                                    label: __('Qty'),
                                    in_list_view: 1
                                }, {
                                    fieldtype: 'Select',
                                    fieldname: 'destination',
                                    reqd: 1,
                                    label: __('Destination'),
                                    in_list_view: 1,
                                    options: [
                                        { label: 'P201-O', value: 'P201-O' },
                                        { label: 'P200-O', value: 'P200-O' },
                                        { label: 'P100-L', value: 'P100-L' },
                                        { label: 'P100-O', value: 'P100-O' },
                                        { label: 'UFM', value: 'UFM' },
                                        { label: 'N/A', value: 'N/A' }
                                    ],
                                    default: 'N/A',
                                }, {
                                    fieldtype: 'Data',
                                    fieldname: 'sales_order_item',
                                    reqd: 1,
                                    label: __('Sales Order Item'),
                                    hidden: 1
                                }, {
                                    fieldtype: 'Long Text',  // or 'Text' for multiline input
                                    fieldname: 'simple_description',
                                    label: __('Notes'),
                                    reqd: 0,
                                    in_list_view: 1
                                }],
                                data: r.message,
                                get_data: () => {
                                    return r.message;
                                }
                            }];
                            var d = new frappe.ui.Dialog({
                                title: __('Select Items to Manufacture'),
                                fields: fields,
                                size: 'large',
                                primary_action: function () {
                                    var data = d.get_values();
                                    frm.call({
                                        method: 'amf.amf.utils.work_order_creation.make_work_orders',
                                        args: {
                                            items: data,
                                            company: frm.doc.company,
                                            sales_order: frm.doc.name
                                        },
                                        freeze: true,
                                        callback: function (r) {
                                            if (r.message) {
                                                frappe.msgprint({
                                                    message: __('Work Orders Created: {0}',
                                                        [r.message.map(function (d) {
                                                            return repl('<a href="#Form/Work Order/%(name)s">%(name)s</a>', { name: d });
                                                        }).join(', ')]),
                                                    indicator: 'green'
                                                });
                                            }
                                            d.hide();
                                        }
                                    });
                                },
                                primary_action_label: __('Create')
                            });
                            d.show();
                        });
                    }
                }
            });
        });

        frm.add = function (cost, costCenter, VATaccountHead, VATrate, VATdescription) {
            frm.clear_table("taxes");

            if (cost > 0) {
                var shipping = frm.add_child("taxes");
                frappe.model.set_value(shipping.doctype, shipping.name, "charge_type", "Actual");
                frappe.model.set_value(shipping.doctype, shipping.name, "cost_center", costCenter);
                frappe.model.set_value(shipping.doctype, shipping.name, "account_head", "3410 - Transport and commission costs - AMF21");
                frappe.model.set_value(shipping.doctype, shipping.name, "tax_amount", cost);
            }
            var taxes = frm.add_child("taxes");
            if (cost > 0) {
                frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Previous Row Total");
                frappe.model.set_value(taxes.doctype, taxes.name, "row_id", "1");
            } else {
                frappe.model.set_value(taxes.doctype, taxes.name, "charge_type", "On Net Total");
            }
            frappe.model.set_value(taxes.doctype, taxes.name, "cost_center", costCenter);

            frappe.model.set_value(taxes.doctype, taxes.name, "account_head", VATaccountHead);
            setTimeout(function () {
                if (cost > 0) {
                    frappe.model.set_value(shipping.doctype, shipping.name, "description", "Shipping");
                }
                frappe.model.set_value(taxes.doctype, taxes.name, "rate", VATrate);
                frappe.model.set_value(taxes.doctype, taxes.name, "description", VATdescription);
            }, 400);

            frm.refresh_field("taxes");
        };
        
        $.each(frm.doc.items || [], function(i, item) {
            item.qty_pcs_rem = item.qty - item.delivered_qty;
        });
    },

    add_shipping_and_taxes: function (frm) {
        frappe.prompt([{
            'fieldname': 'cost',
            'fieldtype': 'Currency',
            'label': 'Shipping Cost',
            'reqd': 0,
            'default': 0,
        }, {
            'fieldname': 'costCenter',
            'fieldtype': 'Select',
            'options': 'General - AMF21\n' +
                'Automation - AMF21\n' +
                'Patch - AMF21',
            'label': 'Cost Center',
            'reqd': 1,
            'default': 0,
        }, {
            'fieldname': 'vat',
            'fieldtype': 'Select',
            'options':
                'VAT 8.1%\n' +
                'VAT 8.1% - Import of Services\n' +
                'VAT 0%\n' +
                'VAT 0% - Import of Services',
            'label': 'VAT',
            'reqd': 1,
        }],
            function (values) {
                console.log(values);
                var VATaccountHead;
                var VATrate;
                var VATdescription;
                switch (values.vat) {
                    case 'VAT 8.1%':
                        VATaccountHead = '2200 - VAT due - AMF21';
                        VATrate = 8.1;
                        VATdescription = 'VAT 8.1%';
                        break;
                    case 'VAT 8.1% - Import of Services':
                        VATaccountHead = '2226 - VAT payable on import of services - AMF21';
                        VATrate = 8.1;
                        VATdescription = 'VAT 8.1%';
                        break;
                    case 'VAT 0%':
                        VATaccountHead = '2200 - VAT due - AMF21';
                        VATrate = 0;
                        VATdescription = 'VAT 0%';
                        break;
                    case 'VAT 0% - Import of Services':
                        VATaccountHead = '2226 - VAT payable on import of services - AMF21';
                        VATrate = 0;
                        VATdescription = 'VAT 0%';
                        break;
                }
                frm.add(values.cost, values.costCenter, VATaccountHead, VATrate, VATdescription);
            },
            'Shipping Cost Entry',
            'Add',
        );
    },
});