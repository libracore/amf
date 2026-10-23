/* Run with node. Uses the installed v12 request and form-save implementations. */
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const bench = path.resolve(__dirname, "../../../..");
const request_source = fs.readFileSync(path.join(bench, "apps/frappe/frappe/public/js/frappe/request.js"), "utf8");
const save_source = fs.readFileSync(path.join(bench, "apps/frappe/frappe/public/js/frappe/form/save.js"), "utf8");
const guard_source = fs.readFileSync(path.join(__dirname, "../public/js/stock_reconciliation_transport.js"), "utf8");

function environment(guarded = true) {
    const state = {messages: [], alerts: [], errors: [], callbacks: [], requests: [], online: true};
    const element = {
        prop(key, value) { state[key] = value; return this; },
        addClass() { return this; },
        attr() { return this; },
        trigger() { return this; },
        ajaxSend() {}, ajaxComplete() {},
    };
    function $(value) { return element; }
    $.extend = Object.assign;
    $.isPlainObject = (value) => !!value && typeof value === "object" && !Array.isArray(value);
    $.isArray = Array.isArray;
    $.each = (values, fn) => Object.keys(values).forEach((key) => fn(key, values[key]));
    $.ajax = (args) => {
        const callbacks = [];
        const result = {
            done(fn) { callbacks.push(["done", fn]); return this; },
            always(fn) { callbacks.push(["always", fn]); return this; },
            fail(fn) { callbacks.push(["fail", fn]); return this; },
            settle(status, body) {
                const xhr = {status, responseText: typeof body === "string" ? body : JSON.stringify(body),
                    responseJSON: typeof body === "object" ? body : undefined,
                    statusCode() { return {status}; }};
                const ok = status === 200 && typeof body !== "string";
                callbacks.forEach(([kind, fn]) => {
                    if (kind === "always" || kind === (ok ? "done" : "fail")) {
                        try {
                            fn(...(ok ? [body, "success", xhr] : [xhr, "error"]));
                        } catch (error) {
                            state.errors.push(error);
                        }
                    }
                });
            },
        };
        state.requests.push({args, result});
        return result;
    };
    const frappe = {
        ui: {form: {}}, request: {},
        provide(name) {
            let target = context;
            name.split(".").forEach((part) => { target = target[part] || (target[part] = {}); });
        },
        is_online: () => state.online,
        msgprint: (value) => state.messages.push(value),
        hide_msgprint() {},
        show_alert: (value) => state.alerts.push(value),
        get_cookie: () => "signed-in-test-session",
        utils: {play_sound() {}},
        dom: {freeze() {}, unfreeze() { state.unfrozen = true; }},
        model: {get_all_docs: () => [], sync() {}, is_table: () => false},
        meta: {docfield_list: {}},
    };
    const context = vm.createContext({frappe, $, window: {}, document: {},
        __: (value) => value, toTitle: (value) => value,
        console: {log() {}, trace: (error) => state.errors.push(error)}});
    vm.runInContext(request_source, context);
    vm.runInContext(save_source, context);
    if (guarded) vm.runInContext(guard_source, context);
    function save() {
        const frm = {doc: {doctype: "Stock Reconciliation", name: "TEST-SR", docstatus: 0},
            wrapper: {}, meta: {}, is_new: () => false};
        frappe.ui.form.save(frm, "Submit", (response) => {
            // The normal form callbacks require an object with exc.
            state.callbacks.push(response.exc ? "failed" : "saved");
        }, {});
        return state.requests[state.requests.length - 1].result;
    }
    return {state, frappe, context, save};
}

let tests = 0;
function test(name, fn) {
    fn();
    tests++;
    console.log("PASS", name);
}
const saved_doc = {docs: [{doctype: "Stock Reconciliation", name: "TEST-SR", docstatus: 1}]};

test("original v12 reproduces the null exc exception after an HTML response", () => {
    const {state, save} = environment(false);
    save().settle(502, "<html>Bad Gateway</html>");
    assert(state.errors.some((error) => /exc/.test(error.message)));
});

for (const status of [502, 504, 0, 403]) {
    test("invalid response " + status + " fails safely and releases the form", () => {
        const {state, frappe, save} = environment();
        save().settle(status, "<html>Unavailable</html>");
        assert.strictEqual(state.errors.length, 0);
        assert.strictEqual(frappe.ui.form.is_saving, false);
        assert.strictEqual(state.disabled, false);
        assert(state.unfrozen);
        assert(state.callbacks.length > 0 && state.callbacks.every((value) => value === "failed"));
        assert(!state.alerts.some((alert) => alert.indicator === "green"));
        assert.strictEqual(state.messages.filter((msg) => msg.title === "Save confirmation unavailable").length, 1);
        // A subsequent user-initiated save still works; the guard never retries.
        assert.strictEqual(state.requests.length, 1);
        save().settle(200, saved_doc);
        assert.strictEqual(state.callbacks[state.callbacks.length - 1], "saved");
    });
}

test("valid submission keeps normal callbacks and success feedback", () => {
    const {state, save} = environment();
    save().settle(200, saved_doc);
    assert.deepStrictEqual(state.callbacks, ["saved"]);
    assert.strictEqual(state.errors.length, 0);
    assert.strictEqual(state.messages.length, 0);
    assert(state.alerts.some((alert) => alert.indicator === "green"));
});

test("successful save with a server warning stays successful", () => {
    const {state, save} = environment();
    save().settle(200, Object.assign({}, saved_doc, {_server_messages: JSON.stringify(["Informational warning"])}));
    assert.deepStrictEqual(state.callbacks, ["saved"]);
    assert.strictEqual(state.errors.length, 0);
    assert(state.alerts.some((alert) => alert.indicator === "green"));
});

test("normal server validation errors are preserved", () => {
    const {state, save} = environment();
    save().settle(417, {exc: JSON.stringify(["ValidationError: Stock moved"]), exc_type: "ValidationError",
        _server_messages: JSON.stringify(["Stock moved; recount"])});
    assert.deepStrictEqual(state.callbacks, ["failed"]);
    assert.strictEqual(state.errors.length, 0);
    assert(!state.messages.some((msg) => msg.title === "Save confirmation unavailable"));
    assert(!state.alerts.some((alert) => alert.indicator === "green"));
});

test("malformed HTTP 200 cannot be reported as saved", () => {
    const {state, save} = environment();
    save().settle(200, {});
    assert(state.callbacks.every((value) => value === "failed"));
    assert.strictEqual(state.errors.length, 0);
    assert(!state.alerts.some((alert) => alert.indicator === "green"));
});

test("offline saves cannot crash or claim success", () => {
    const {state, frappe, save} = environment();
    state.online = false;
    save();
    assert.strictEqual(frappe.ui.form.is_saving, false);
    assert.deepStrictEqual(state.callbacks, ["failed"]);
    assert(!state.alerts.some((alert) => alert.indicator === "green"));
});

test("unrelated API calls retain their return value and payload", () => {
    const {state, frappe} = environment();
    let response;
    const returned = frappe.call({method: "example.read", args: {}, callback: (r) => { response = r; }});
    assert.strictEqual(returned, state.requests[0].result);
    const payload = {message: "original result"};
    returned.settle(200, payload);
    assert.strictEqual(response, payload);
});

test("loading the doctype script twice does not install nested guards", () => {
    const {frappe, context} = environment();
    const wrapper = frappe.call;
    vm.runInContext(guard_source, context);
    assert.strictEqual(frappe.call, wrapper);
});

console.log(tests + " tests passed");
