import frappe


PAGE_NAME = "fftest-stock-entry-debug"
PAGE_ROUTE = "fftest_stock_entry_debug"


MAIN_SECTION = """
<div class="fftest-debug-shell">
    <h2>FFtest Stock Entry Debug</h2>
    <p class="fftest-debug-help">
        Analyze the complete Work Order, BOM, Serial No, Batch and Stock Entry flow
        without changing stock. Execute is available only after a successful analysis.
    </p>

    <div id="fftest-debug-login" class="fftest-debug-alert error" hidden>
        Login is required. <a href="/login">Open login</a>
    </div>

    <div class="fftest-debug-form">
        <label>
            Source Work Order
            <input id="fftest-debug-work-order" type="text" placeholder="OF-04260">
        </label>
        <label>
            Finished body Serial No
            <input id="fftest-debug-serial" type="text" placeholder="P202-O00000070">
        </label>
        <label class="wide">
            Batch list (JSON)
            <textarea id="fftest-debug-batches" rows="3" placeholder='[{"batch_no":"...","quantity":"1"}]'>[]</textarea>
        </label>
    </div>

    <div class="fftest-debug-actions">
        <button id="fftest-debug-analyze" class="btn btn-primary">Analyze only</button>
        <button id="fftest-debug-execute" class="btn btn-danger" disabled>Execute real flow</button>
        <span id="fftest-debug-state"></span>
    </div>

    <div id="fftest-debug-output"></div>
</div>
"""


JAVASCRIPT = r"""
(function () {
    'use strict';

    let lastReport = null;

    function value(id) {
        return (document.getElementById(id).value || '').trim();
    }

    function queryValue(name) {
        return new URLSearchParams(window.location.search).get(name) || '';
    }

    function escapeHtml(input) {
        return String(input == null ? '' : input)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function setBusy(isBusy, message) {
        document.getElementById('fftest-debug-analyze').disabled = isBusy;
        document.getElementById('fftest-debug-execute').disabled =
            isBusy || !lastReport || !lastReport.ok || !lastReport.can_execute;
        document.getElementById('fftest-debug-state').textContent = message || '';
    }

    function getArgs() {
        const workOrder = value('fftest-debug-work-order');
        const serialNo = value('fftest-debug-serial');
        const batchText = value('fftest-debug-batches') || '[]';
        JSON.parse(batchText);
        if (!workOrder || !serialNo) {
            throw new Error('Work Order and Serial No are required.');
        }
        return {
            source_work_order_id: workOrder,
            serial_no_id: serialNo,
            batch_no_id: batchText
        };
    }

    function renderMessages(title, rows, className) {
        if (!rows || !rows.length) return '';
        return `<div class="fftest-debug-alert ${className}"><strong>${escapeHtml(title)}</strong><ul>`
            + rows.map(row => `<li>${escapeHtml(row)}</li>`).join('')
            + '</ul></div>';
    }

    function renderReport(report) {
        const output = document.getElementById('fftest-debug-output');
        const badgeClass = report.ok ? 'ok' : 'error';
        const badgeText = report.ok ? 'READY' : 'BLOCKED';
        const steps = (report.steps || []).map(step => `
            <tr>
                <td><span class="fftest-debug-status ${escapeHtml(step.status)}">${escapeHtml(step.status)}</span></td>
                <td>${escapeHtml(step.label)}</td>
                <td>${escapeHtml(step.doctype || '')}</td>
                <td>${escapeHtml(step.name || '')}</td>
                <td><code>${escapeHtml(JSON.stringify(step.details || {}))}</code></td>
            </tr>`).join('');
        const planned = (report.planned_documents || []).map((doc, index) => `
            <li><strong>${index + 1}. ${escapeHtml(doc.doctype)} — ${escapeHtml(doc.purpose || '')}</strong>
                <pre>${escapeHtml(JSON.stringify(doc, null, 2))}</pre>
            </li>`).join('');
        const related = (report.related_stock_entries || []).map(doc => `
            <tr>
                <td>${escapeHtml(doc.name)}</td>
                <td>${escapeHtml(doc.work_order)}</td>
                <td>${escapeHtml(doc.purpose)}</td>
                <td>${escapeHtml(doc.docstatus)}</td>
                <td>${escapeHtml(doc.posting_date)} ${escapeHtml(doc.posting_time)}</td>
            </tr>`).join('');

        output.innerHTML = `
            <div class="fftest-debug-summary">
                <span class="fftest-debug-badge ${badgeClass}">${badgeText}</span>
                <span>Read-only analysis; no DocType was changed.</span>
            </div>
            ${renderMessages('Errors', report.errors, 'error')}
            ${renderMessages('Warnings', report.warnings, 'warning')}
            <h3>Validation steps</h3>
            <div class="table-responsive"><table class="table table-bordered">
                <thead><tr><th>Status</th><th>Step</th><th>DocType</th><th>Name</th><th>Details</th></tr></thead>
                <tbody>${steps}</tbody>
            </table></div>
            <h3>Planned documents</h3>
            <ol class="fftest-debug-plan">${planned || '<li>None</li>'}</ol>
            <h3>Related Stock Entries</h3>
            <div class="table-responsive"><table class="table table-bordered">
                <thead><tr><th>Name</th><th>Work Order</th><th>Purpose</th><th>Docstatus</th><th>Posting</th></tr></thead>
                <tbody>${related || '<tr><td colspan="5">None</td></tr>'}</tbody>
            </table></div>
            <details><summary>Raw report</summary><pre>${escapeHtml(JSON.stringify(report, null, 2))}</pre></details>`;
    }

    async function analyze() {
        try {
            lastReport = null;
            setBusy(true, 'Analyzing…');
            const response = await frappe.call({
                method: 'amf.www.fftest_master_debug.debug_stock_entry_flow',
                args: getArgs()
            });
            lastReport = response.message;
            renderReport(lastReport);
            setBusy(false, lastReport.ok ? 'Analysis passed.' : 'Analysis found blockers.');
        } catch (error) {
            lastReport = null;
            setBusy(false, 'Analysis failed.');
            document.getElementById('fftest-debug-output').innerHTML =
                renderMessages('Error', [error.message || error], 'error');
        }
    }

    async function executeFlow() {
        if (!lastReport || !lastReport.ok || !lastReport.can_execute) return;
        if (!window.confirm(
            'This will create and submit real Work Orders/Stock Entries and change stock. Continue?'
        )) return;

        try {
            setBusy(true, 'Executing real stock flow…');
            const args = getArgs();
            args.batch_no_id = JSON.parse(args.batch_no_id);
            const response = await frappe.call({
                method: 'amf.www.fftest_master_debug.make_stock_entry',
                args: args
            });
            if (response.message && response.message.error) {
                throw new Error(response.message.error);
            }
            frappe.msgprint(__('FFTest stock flow completed successfully.'));
            await analyze();
        } catch (error) {
            setBusy(false, 'Execution failed.');
            frappe.msgprint({
                title: __('FFTest execution failed'),
                message: escapeHtml(error.message || error),
                indicator: 'red'
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (frappe.session.user === 'Guest') {
            document.getElementById('fftest-debug-login').hidden = false;
            document.getElementById('fftest-debug-analyze').disabled = true;
            return;
        }

        document.getElementById('fftest-debug-work-order').value = queryValue('of');
        document.getElementById('fftest-debug-serial').value = queryValue('sn');
        document.getElementById('fftest-debug-batches').value = queryValue('batch_list') || '[]';
        document.getElementById('fftest-debug-analyze').addEventListener('click', analyze);
        document.getElementById('fftest-debug-execute').addEventListener('click', executeFlow);

        if (value('fftest-debug-work-order') && value('fftest-debug-serial')) analyze();
    });
})();
"""


CSS = """
.fftest-debug-shell { max-width: 1200px; margin: 24px auto; padding: 0 18px 40px; }
.fftest-debug-help { color: #667085; margin-bottom: 20px; }
.fftest-debug-form { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.fftest-debug-form label { display: flex; flex-direction: column; gap: 6px; font-weight: 600; }
.fftest-debug-form .wide { grid-column: 1 / -1; }
.fftest-debug-form input, .fftest-debug-form textarea {
    width: 100%; border: 1px solid #d0d5dd; border-radius: 6px; padding: 9px 11px;
    background: #fff; color: #101828; font-family: inherit;
}
.fftest-debug-actions { display: flex; align-items: center; gap: 10px; margin: 18px 0; }
#fftest-debug-state { color: #667085; }
.fftest-debug-summary { display: flex; align-items: center; gap: 10px; margin: 18px 0; }
.fftest-debug-badge, .fftest-debug-status { border-radius: 999px; padding: 3px 9px; font-weight: 700; text-transform: uppercase; }
.fftest-debug-badge.ok, .fftest-debug-status.ok { background: #dcfae6; color: #067647; }
.fftest-debug-badge.error, .fftest-debug-status.error { background: #fee4e2; color: #b42318; }
.fftest-debug-status.warning { background: #fef0c7; color: #b54708; }
.fftest-debug-alert { border-radius: 6px; padding: 12px 16px; margin: 12px 0; }
.fftest-debug-alert.error { background: #fee4e2; color: #912018; }
.fftest-debug-alert.warning { background: #fef0c7; color: #93370d; }
.fftest-debug-alert ul { margin: 6px 0 0; }
.fftest-debug-plan pre, .fftest-debug-shell details pre { background: #f2f4f7; border-radius: 6px; padding: 12px; }
.fftest-debug-shell code { white-space: normal; word-break: break-word; }
@media (max-width: 700px) { .fftest-debug-form { grid-template-columns: 1fr; } .fftest-debug-form .wide { grid-column: auto; } }
"""


def install_fftest_debug_page():
    """Create or update the database-backed FFTest debug Web Page."""
    frappe.only_for("System Manager")
    if frappe.db.exists("Web Page", PAGE_NAME):
        page = frappe.get_doc("Web Page", PAGE_NAME)
    else:
        page = frappe.new_doc("Web Page")
        page.name = PAGE_NAME

    page.title = "FFtest Stock Entry Debug"
    page.route = PAGE_ROUTE
    page.published = 1
    page.show_title = 0
    page.content_type = "Rich Text"
    page.main_section = MAIN_SECTION
    page.insert_code = 1
    page.javascript = JAVASCRIPT
    page.insert_style = 1
    page.css = CSS
    page.show_sidebar = 0
    page.enable_comments = 0
    page.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "name": page.name,
        "title": page.title,
        "route": page.route,
        "url": "/{0}".format(page.route),
    }
