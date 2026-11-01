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
assert.strictEqual(queries.seat_pin_item().filters.disabled, 0);

// Pin selection and Product code edits invalidate a previously displayed plan.
[() => events.seat_pin_item(frm), () => handlers["Item Creation Variant"].product_code(frm),
    () => handlers["Item Creation Variant"].product_reference(frm)].forEach(change => {
    frm.__creation_plan = {ready: true};
    change();
    assert.strictEqual(frm.__creation_plan, null);
});

// HV/HD choices remain visible and explain geometry requirements safely.
calls.length = 0;
frm = form({head_name: "VALVE HEAD-D-1-6-050-C-P", pump_hv_check: 1, product_variants: []});
sandbox.chooseItemCreationVariants(frm);
calls[0].callback({message: [
    {body: "561000", syringe: "70E000", configuration: "P101-O (HV) / S-2500-P", compatibility_note: "Requires <HV> head"},
    {body: "5C1000", syringe: "70F000", configuration: "P111-L (HV / HD) / S-5000-P", compatibility_note: "Requires HV head"},
]});
const choices = dialog.fields.find(field => field.fieldname === "variants").options;
assert.strictEqual(choices.length, 2);
assert.strictEqual(choices[0].danger, true);
assert.ok(choices[0].label.includes("Requires &lt;HV&gt; head"));
assert.ok(choices[1].label.includes("P111-L (HV / HD) / S-5000-P"));

// RVM mini is an explicit RVM configuration and requires no syringe.
calls.length = 0;
frm = form({rvm_check: 1, product_variants: []});
frm.clear_table = field => { frm.doc[field] = []; };
frm.add_child = field => { const row = {}; frm.doc[field].push(row); return row; };
frm.refresh_field = () => {};
frm.dirty = () => {};
sandbox.chooseItemCreationVariants(frm);
calls[0].callback({message: [
    {body: "5D1000", syringe: "", configuration: "P202-O (RVM mini)", compatibility_note: ""},
    {body: "5D1001", syringe: "", configuration: "P202-O RS485 (RVM mini)", compatibility_note: ""},
    {body: "5D1002", syringe: "", configuration: "P202-O CAN (RVM mini)", compatibility_note: ""},
    {body: "521003", syringe: "", configuration: "P201-O.LPH (RVM)", compatibility_note: "", configuration_note: "Review I2C <address>"},
]});
assert.ok(dialog.fields.find(field => field.fieldname === "variants").options[0].label.includes("P202-O (RVM mini)"));
assert.ok(dialog.fields.find(field => field.fieldname === "variants").options[3].label.includes("Review I2C &lt;address&gt;"));
dialog.primary_action({variants: ["5D1000:", "5D1001:", "5D1002:"]});
assert.strictEqual(frm.doc.product_variants[0].body, "5D1000");
assert.strictEqual(frm.doc.product_variants[1].body, "5D1001");
assert.strictEqual(frm.doc.product_variants[2].body, "5D1002");
assert.strictEqual(frm.doc.product_variants[0].syringe, "");
assert.strictEqual(frm.doc.product_variants[0].selected, 1);

// Reopening the configuration chooser retains an explicit Product code override.
calls.length = 0;
frm = form({head_code: "300ABC", rvm_check: 1,
    product_variants: [{body: "521000", syringe: "", selected: 1, product_code: "420XYZ", product_reference: "P201O300ABC-R1"}]});
frm.clear_table = field => { frm.doc[field] = []; };
frm.add_child = field => { const row = {}; frm.doc[field].push(row); return row; };
frm.refresh_field = () => {};
frm.dirty = () => {};
sandbox.chooseItemCreationVariants(frm);
calls[0].callback({message: [{body: "521000", syringe: "", configuration: "P201-O (RVM)"}]});
dialog.primary_action({variants: ["521000:"]});
assert.strictEqual(frm.doc.product_variants[0].product_code, "420XYZ");
assert.strictEqual(frm.doc.product_variants[0].product_reference, "P201O300ABC-R1");

// A reference conflict opens an editor for the exact row, without changing its code.
calls.length = 0; timers.clear();
frm = form({docstatus: 0, head_code: "300080", product_variants: [
    {selected: 1, body: "511000", syringe: "", product_code: "410001"}]});
let markedDirty = false;
frm.dirty = () => { markedDirty = true; };
frm.refresh_field = () => {};
let editReferenceClick;
const wrapper = {off: () => wrapper, on: (event, selector, callback) => { editReferenceClick = callback; return wrapper; }};
frm.fields_dict = {plan_preview: {$wrapper: wrapper}};
const conflictPlan = {summary: {}, actions: [], errors: [{message: "Reference conflict", reference_conflict:
    {configuration: "511000:", reference: "P200O300080", owners: ["/410080"]}}], product_suggestions: [
    {body: "511000", syringe: "", product_code: "410001", product_reference: "P200O300080", default_reference: "P200O300080"}]};
sandbox.refreshItemCreationPlan(frm);
calls[0].callback({message: conflictPlan});
assert.ok(frm.properties["plan_preview:options"].includes("Change Product Reference"));
assert.ok(!sandbox.renderItemCreationPlan(conflictPlan, false).includes("Change Product Reference"));
editReferenceClick({preventDefault: () => {}, currentTarget: {getAttribute: () => "511000:"}});
assert.strictEqual(dialog.fields.find(field => field.fieldname === "product_reference").default, "P200O300080");
dialog.primary_action({product_reference: " P200O300080-R1 "});
assert.strictEqual(frm.doc.product_variants[0].product_reference, "P200O300080-R1");
assert.strictEqual(frm.doc.product_variants[0].product_code, "410001");
assert.strictEqual(markedDirty, true);
assert.strictEqual(frm.__creation_plan, null);
// A dialog opened against old inputs cannot overwrite newer edits.
frm.__creation_plan = conflictPlan;
sandbox.editItemCreationProductReference(frm, "511000:");
frm.doc.head_code = "300081";
dialog.primary_action({product_reference: "OLD-300080"});
assert.strictEqual(frm.doc.product_variants[0].product_reference, "P200O300080-R1");

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
// Derived suggestions cannot overwrite overrides or invalidate an in-flight plan.
calls.length = 0;
frm = form({head_check: "No", head_item: "300080", product_only: 1,
    product_variants: [{selected: 1, body: "521000", syringe: "", product_code: "420XYZ"}]});
frm.refresh_field = () => {};
const beforeSuggestion = sandbox.itemCreationInputs(frm);
sandbox.suggestItemCreationProductCodes(frm);
calls[0].callback({message: [{body: "521000", syringe: "", product_code: "420XYZ"}]});
assert.strictEqual(frm.doc.product_variants[0].product_code, "420XYZ");
assert.strictEqual(frm.doc.product_variants[0].code_suggestion, "420XYZ");
assert.strictEqual(sandbox.itemCreationInputs(frm), beforeSuggestion);
sandbox.suggestItemCreationProductCodes(frm);
frm.doc.head_item = "300081";
calls[1].callback({message: [{body: "521000", syringe: "", product_code: "420OLD"}]});
assert.strictEqual(frm.doc.product_variants[0].code_suggestion, "420XYZ");

(async () => {
    const modeForm = form({product_only: 1, head_check: "No", head_item: "300080", head_code: "300080",
        seat_check: "Yes", plug_check: "Yes", replace_boms: 1});
    const changed = events.product_only(modeForm);
    events.head_check(modeForm); // Mode transition must retain the selected existing head.
    await changed;
    assert.strictEqual(modeForm.doc.head_item, "300080");
    assert.strictEqual(modeForm.doc.head_check, "No");
    assert.strictEqual(modeForm.doc.seat_check, "No");
    assert.strictEqual(modeForm.doc.plug_check, "No");
    assert.strictEqual(modeForm.doc.replace_boms, 0);
    assert.strictEqual(modeForm.properties["head_name:read_only"], true);
    console.log("Item Creation guided-form, review, preview, numbering and product-only tests passed.");
})().catch(error => { console.error(error); process.exitCode = 1; });
