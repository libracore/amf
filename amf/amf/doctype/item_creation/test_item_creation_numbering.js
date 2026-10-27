// Run with node: exercise actual form code without a browser or database.
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const handlers = {};
const calls = [];
const timers = new Map();
let nextTimer = 0;
let dialog;
const sandbox = {
    frappe: {
        ui: {form: {on: (doctype, events) => { handlers[doctype] = Object.assign(handlers[doctype] || {}, events); }},
            Dialog: function(options) { dialog = options; sandbox.lastDialog = this; this.show = () => {}; this.hide = () => {}; }},
        call: options => { calls.push(options); }, msgprint: () => {},
        throw: message => { throw new Error(message); },
        user_roles: ["System Manager"], session: {user: "Administrator"},
    },
    __: (message, values) => values ? message.replace(/\{(\d+)\}/g, (_, index) => values[index]) : message,
    setTimeout: callback => { const id = ++nextTimer; timers.set(id, callback); return id; },
    clearTimeout: id => { timers.delete(id); },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "item_creation.js"), "utf8"), sandbox);
const events = handlers["Item Creation"];
function form(doc) {
    return {doc, properties: {}, set_value(key, value) {
        if (typeof key === "object") Object.assign(doc, key); else doc[key] = value;
    }, set_df_property(field, property, value) { this.properties[field + ":" + property] = value; },
        set_intro: () => {}, is_dirty: () => false};
}
function flushTimers() {
    const callbacks = Array.from(timers.values()); timers.clear(); callbacks.forEach(callback => callback());
}
let frm = form({head_code: "300ABC", seat_check: "Yes", plug_check: "Yes"});
events.head_code(frm);
assert.strictEqual(frm.doc.seat_code, "200ABC");
assert.strictEqual(frm.doc.plug_code, "100ABC");
frm.doc.head_code = "300ABD";
events.head_code(frm);
assert.strictEqual(frm.doc.seat_code, "200ABD");
assert.strictEqual(frm.doc.plug_code, "100ABD");
assert.strictEqual(events.before_submit, undefined);

calls.length = 0; timers.clear();
frm = form({head_name: "VALVE HEAD-D-1-6-050-C-P", head_check: "Yes", __islocal: 1});
events.head_name(frm);
const oldRequests = calls.splice(0);
frm.doc.head_name = "VALVE HEAD-D-1-8-100-K-U";
events.head_name(frm);
oldRequests.find(call => call.method.endsWith(".suggest_bom_managed_item_code"))
    .callback({message: {item_code: "300001"}});
assert.strictEqual(frm.doc.head_code, undefined);
calls.find(call => call.method.endsWith(".suggest_bom_managed_item_code"))
    .callback({message: {item_code: "300ABC"}});
assert.strictEqual(frm.doc.head_code, "300ABC");

calls.length = 0; timers.clear();
frm = form({head_code: "300ABC", pump_hv_check: 1, pump_check: 0});
events.pump_hv_check(frm);
flushTimers();
assert.strictEqual(calls.length, 1);
assert.ok(calls[0].method.endsWith(".get_creation_plan"));
assert.strictEqual(calls[0].args.document.pump_hv_check, 1);

// A changed quantity invalidates an in-flight plan and only the latest response renders.
const stale = calls[0];
frm.doc.screw_quantity = 4;
events.screw_quantity(frm);
flushTimers();
const latest = calls[calls.length - 1];
stale.callback({message: {ready: true, actions: [], summary: {items: 999}}});
assert.strictEqual(frm.__creation_plan, null);
latest.callback({message: {ready: true, actions: [], summary: {items: 2}}});
assert.strictEqual(frm.__creation_plan.summary.items, 2);

// Unsaved user/catalogue strings cannot become preview HTML.
const evil = '<img src=x onerror="alert(1)">';
const html = sandbox.renderItemCreationPlan({summary: {}, errors: [{message: evil}], warnings: [evil],
    actions: [{item: {item_code: "100ABC", item_name: evil}, item_action: "create", bom_action: "create",
        proposed: {company: evil, uom: "Nos", materials: [{item_code: evil, qty: evil, uom: evil}]}}]});
assert.ok(!html.includes("<img"));
assert.ok(html.includes("&lt;img"));
assert.ok(html.includes("Quantity per unit"));

// Stock-UOM callbacks cannot overwrite a more recently selected rod.
calls.length = 0; timers.clear();
frm = form({plug_raw_material: "ROD-A"});
events.plug_raw_material(frm);
frm.doc.plug_raw_material = "ROD-B";
calls[0].callback({message: {stock_uom: "Wrong"}});
assert.strictEqual(frm.doc.plug_raw_uom, "");

// Review always requires saved inputs and the complete ready plan.
calls.length = 0;
frm = form({name: "REQUEST-A"});
frm.__creation_plan = {ready: true, fingerprint: "HASH"};
frm.is_dirty = () => true;
sandbox.reviewItemCreationPlan(frm);
assert.strictEqual(calls.length, 0);
frm.is_dirty = () => false;
sandbox.reviewItemCreationPlan(frm);
dialog.primary_action({notes: "Stock grade, quantities and recipe reviewed"});
assert.strictEqual(calls.length, 1);
assert.ok(calls[0].method.endsWith(".record_engineering_review"));
assert.strictEqual(calls[0].args.fingerprint, "HASH");
assert.strictEqual(calls[0].type, "POST");

// Cancellation asks for a reason and dismissal stops the native cancel action.
frm = form({name: "COMPLETED", docstatus: 1});
sandbox.frappe.validated = true;
events.before_cancel(frm);
dialog.primary_action({reason: "  Reviewed replacement required  "});
assert.strictEqual(frm.doc.cancellation_reason, "Reviewed replacement required");
sandbox.lastDialog.onhide();
assert.strictEqual(sandbox.frappe.validated, true);
events.before_cancel(frm);
sandbox.lastDialog.onhide();
assert.strictEqual(sandbox.frappe.validated, false);

// Child selectors retain the Body pattern and use the alphanumeric syringe query.
const queries = {};
frm = form({name: "DRAFT", docstatus: 0});
frm.set_query = (field, parent, query) => { queries[field] = query || parent; };
frm.add_custom_button = () => {};
events.refresh(frm);
assert.strictEqual(queries.body().filters.item_code[1], "5_1___");
assert.ok(queries.syringe().query.endsWith(".syringe_item_query"));

// Reverse links from either Item or BOM open the same report with exact filters.
let route;
sandbox.frappe.model = {can_read: () => true};
sandbox.frappe.set_route = (...args) => { route = args; };
vm.runInContext(fs.readFileSync(path.join(__dirname, "../../..", "public/js/item_creation_history.js"), "utf8"), sandbox);
["Item", "BOM"].forEach(doctype => {
    let action;
    handlers[doctype].refresh({doc: {name: "LINKED"}, add_custom_button: (label, callback) => { action = callback; }});
    action();
    assert.strictEqual(sandbox.frappe.route_options[doctype === "Item" ? "item_code" : "bom"], "LINKED");
    assert.strictEqual(route[1], "Item Creation Results");
});
console.log("Item Creation guided-form, review, preview and numbering tests passed.");
