// Frappe V12 websites run their own callbacks in a different order from Desk.
// jqXHR handlers keep success/error/completion ordering consistent on this page.
function trackingCall(opts) {
  return frappe.call({method: opts.method, args: opts.args || {}, type: opts.type || "POST"})
    .done(function (data) {
      if (data && !data.exc) { if (opts.callback) opts.callback(data); }
      else if (opts.error) opts.error(data);
    })
    .fail(function (xhr) { if (opts.error) opts.error(xhr); })
    .always(function () { if (opts.always) opts.always(); });
}

const ptIconPaths = {
  factory: '<path d="M3 21V10l6 3V8l6 3V3h5v18H3Z"/><path d="M7 17h1m4 0h1m4 0h1"/>',
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18m-13 5h3"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2l1 4M4 12l1 4a8 8 0 0 0 13 2"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8l10-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  truck: '<path d="M1 4h13v12H1zM14 9h4l4 4v3h-8"/><circle cx="5.5" cy="18" r="2.5"/><circle cx="18.5" cy="18" r="2.5"/>',
  alert: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v4m0 4h.01"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 3 2 2-1 3 3 2 2 3h4l1-3 3-1 2-3-2-2 1-3-3-2-2-3H9Z"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  note: '<path d="M14 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-9M14 3v7h7l-7-7Z"/><path d="M7 14h9m-9 3h6"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2Z"/><path d="M7 3v6h9V3M7 21v-8h10v8"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  chart: '<path d="M4 3v18h17M8 16v-5m5 5V7m5 9v-8"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  reset: '<path d="M3 4v5h5M3 9a9 9 0 1 1 0 6"/>',
  sort: '<path d="M7 3v18m-4-4 4 4 4-4M13 5h8m-8 5h6m-6 5h4"/>',
  edit: '<path d="m16 3 5 5-12 12-6 1 1-6L16 3Zm-2 2 5 5"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  undo: '<path d="M3 10V4m0 6h6M3 10l4-4a8 8 0 1 1-1 12"/>',
  link: '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>'
};
function ptIcon(name) {
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + (ptIconPaths[name] || ptIconPaths.layers) + '</svg>';
}
function ptHydrateIcons() {
  document.querySelectorAll('.pt-page [data-icon]').forEach(el => { el.innerHTML = ptIcon(el.dataset.icon); });
}
function escapeHTML(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
let ptSiteToday = new Intl.DateTimeFormat('sv-SE', {timeZone: 'Europe/Zurich'}).format(new Date());
function ptDay(value) {
  const text = String(value || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const parts = text.split('-').map(Number);
  return Date.UTC(parts[0], parts[1] - 1, parts[2]);
}
function ptDaysUntil(value) {
  const day = ptDay(value), today = ptDay(ptSiteToday);
  return day === null || today === null ? null : Math.round((day - today) / 86400000);
}
function ptFormatDate(value) {
  const day = ptDay(value);
  return day === null ? 'Date à préciser' : new Intl.DateTimeFormat('fr-CH', {day: '2-digit', month: 'short', timeZone: 'UTC'}).format(day);
}
function ptDateInfo(value) {
  const days = ptDaysUntil(value);
  if (days === null) return {label: 'Date à préciser', hint: 'Sans date prévue', color: 'amber', days: null};
  if (days < 0) return {label: ptFormatDate(value), hint: Math.abs(days) + ' j de retard', color: 'red', days: days};
  if (days === 0) return {label: "Aujourd’hui", hint: "Prévu aujourd’hui", color: 'amber', days: days};
  return {label: ptFormatDate(value), hint: days === 1 ? 'Prévu demain' : 'Dans ' + days + ' jours', color: 'gray', days: days};
}
function ptNumber(value, digits) {
  return Number(value || 0).toLocaleString('fr-CH', {maximumFractionDigits: digits == null ? 0 : digits});
}
const ptOverview = {orders: null, shipments: null, hiddenCustomers: false, errors: new Set()};
function ptSync(source, failed) {
  if (failed) ptOverview.errors.add(source); else ptOverview.errors.delete(source);
  const el = document.getElementById('sync-status');
  const error = ptOverview.errors.size > 0;
  el.classList.toggle('pt-error', error);
  el.innerHTML = '<i></i>' + (error ? 'Certaines données sont indisponibles' : 'Mis à jour à ' + new Intl.DateTimeFormat('fr-CH', {hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich'}).format(new Date()));
}
function ptSetText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }

function loadWorkOrders() {
  trackingCall({
    method: 'amf.www.production_tracking_planning.get_work_orders',
    callback: function (r) {
      if (!r.message) return;
      ptOverview.orders = r.message;
      if (r.message.today) ptSiteToday = r.message.today;
      const ongoing = r.message.ongoing || [], upcoming = r.message.upcoming || [];
      renderSubLists('ongoing', ongoing);
      renderSubLists('upcoming', upcoming);
      ptSetText('kpi-ongoing', ongoing.length);
      ptSetText('kpi-upcoming', upcoming.length);
      ptSetText('overview-tab-count', ongoing.length + upcoming.length);
      const assembly = ongoing.concat(upcoming).filter(row => row.operation_type === 'Assemblage').length;
      ptSetText('assembly-total', assembly + ' OF');
      ptSetText('kpi-ongoing-detail', ongoing.filter(row => row.operation_type === 'Assemblage').length + ' assemblage · ' + ongoing.filter(row => row.operation_type === 'Usinage').length + ' usinage');
      ptSync('orders', false);
    },
    error: function () {
      ['ongoing-assemblage','upcoming-assemblage','ongoing-usinage','upcoming-usinage'].forEach(id => {
        document.getElementById(id).innerHTML = '<p class="pt-empty">Chargement impossible. Actualisez la page.</p>';
      });
      ptSync('orders', true);
    }
  });
}
function renderSubLists(baseId, data) {
  ['Assemblage', 'Usinage'].forEach(type => {
    const items = data.filter(row => row.operation_type === type);
    const id = baseId + '-' + type.toLowerCase();
    ptSetText(id + '-count', items.length);
    renderList(id, items, baseId, type.toLowerCase());
  });
}
function renderList(containerId, data, baseId, opType) {
  const target = document.getElementById(containerId);
  if (!target) return;
  if (!data.length) { target.innerHTML = '<p class="pt-empty">' + ptIcon('check') + '<br>Aucun OF ' + (baseId === 'ongoing' ? 'en cours' : 'à venir') + '</p>'; return; }
  const sorted = data.slice().sort((a, b) => {
    const first = ptDay(a.expected_delivery_date_ || a.expected_delivery_date);
    const second = ptDay(b.expected_delivery_date_ || b.expected_delivery_date);
    return (first === null ? Infinity : first) - (second === null ? Infinity : second) || Number(a.priority || 0) - Number(b.priority || 0) || a.name.localeCompare(b.name);
  });
  target.innerHTML = sorted.map(item => {
    const timer = item.timer_info || {};
    const active = timer.status === 'IN PROCESS';
    const date = ptDateInfo(item.expected_delivery_date_ || item.expected_delivery_date);
    const ops = (timer.operators || '').split('/').map(o => o.trim()).filter(Boolean);
    const operator = ops.length ? '<span class="pt-operator" title="' + escapeHTML(ops.join(' · ')) + '"><span class="pt-operator-avatar">' + escapeHTML(ops[0].slice(0, 2).toUpperCase()) + '</span>' + escapeHTML(ops.slice(0, 2).join(' · ')) + (ops.length > 2 ? ' +' + (ops.length - 2) : '') + '</span>' : '<span class="pt-order-stage">' + escapeHTML(opType === 'usinage' ? item.progress || 'À usiner' : timer.status === 'PAUSED' ? 'Assemblage en pause' : baseId === 'ongoing' ? 'Assemblage' : 'À assembler') + '</span>';
    const machine = item.machine ? '<span class="pt-meta-separator">·</span><span>' + escapeHTML(item.machine) + '</span>' : '';
    return '<a class="pt-order-card' + (active ? ' pt-order-active' : '') + '" href="/desk#Form/Work%20Order/' + encodeURIComponent(item.name) + '" target="_blank" rel="noopener">' +
      '<div class="pt-order-top"><span class="pt-order-id">' + escapeHTML(item.name) + '</span><span class="pt-badge pt-badge-' + date.color + '" title="' + escapeHTML(date.hint) + '">' + (date.days !== null && date.days < 0 ? ptIcon('alert') : '') + escapeHTML(date.label) + '</span></div>' +
      '<strong class="pt-order-name">' + escapeHTML(item.item_name || item.production_item) + '</strong><div class="pt-order-meta"><span>' + escapeHTML(item.production_item) + '</span><span class="pt-meta-separator">·</span><span>' + ptNumber(item.qty, 6) + ' pce</span>' + machine + '</div>' +
      '<div class="pt-order-bottom">' + operator + '<span class="pt-badge pt-badge-' + (active ? 'teal' : timer.status === 'PAUSED' ? 'amber' : baseId === 'ongoing' ? 'green' : 'blue') + '">' + (active ? 'Timer actif' : timer.status === 'PAUSED' ? 'En pause' : baseId === 'ongoing' ? 'En cours' : 'À venir') + '</span></div></a>';
  }).join('');
}
function getWeekInfo() {
  const monday = new Date(ptDay(ptSiteToday));
  const weekday = monday.getUTCDay() || 7;
  monday.setUTCDate(monday.getUTCDate() - weekday + 1);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  const thursday = new Date(monday);
  thursday.setUTCDate(monday.getUTCDate() + 3);
  const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((thursday - yearStart) / 86400000) + 1) / 7);
  return {week: week, start: ptFormatDate(monday.toISOString().slice(0,10)), end: ptFormatDate(sunday.toISOString().slice(0,10))};
}
function renderShipments() {
  const data = ptOverview.shipments;
  if (!data) return;
  const info = getWeekInfo();
  ptSetText('shipments-title', 'Semaine ' + info.week + ' · ' + info.start + ' – ' + info.end);
  const ready = data.filter(row => row.shipment_status === 'green').length;
  ptSetText('kpi-shipments', data.length - ready);
  ptSetText('kpi-shipment-late', data.filter(row => row.shipment_status === 'orange').length);
  ptSetText('kpi-shipments-detail', ready + ' avec bon validé sur ' + data.length + ' commande' + (data.length > 1 ? 's' : ''));
  document.getElementById('shipments').innerHTML = data.length ? data.map(so => {
    const color = so.shipment_status === 'green' ? 'green' : so.shipment_status === 'orange' ? 'red' : 'amber';
    const label = color === 'green' ? 'Bon validé' : color === 'red' ? 'En retard' : 'À expédier';
    return '<a class="pt-shipment" href="/desk#Form/Sales%20Order/' + encodeURIComponent(so.name) + '" target="_blank" rel="noopener"><span class="pt-shipment-id">' + escapeHTML(so.name) + '</span><span class="pt-shipment-customer' + (ptOverview.hiddenCustomers ? ' hidden-customer' : '') + '">' + escapeHTML(so.customer_name || '') + '</span><span class="pt-shipment-date">' + escapeHTML(ptFormatDate(so.delivery_date)) + '</span><span class="pt-badge pt-badge-' + color + '">' + label + '</span></a>';
  }).join('') : '<p class="pt-empty">Aucune commande à expédier cette semaine.</p>';
}
function loadShipments() {
  trackingCall({method: 'amf.www.production_tracking_planning.get_shipments',
    callback: function (r) { ptOverview.shipments = r.message || []; renderShipments(); ptSync('shipments', false); },
    error: function () { document.getElementById('shipments').innerHTML = '<p class="pt-empty">Expéditions indisponibles avec vos droits actuels.</p>'; ptSync('shipments', true); }
  });
}
let noteModified = null;
let noteDirty = false;
let noteSaving = false;
let noteBound = false;
function loadGlobalNote() {
  const textarea = document.getElementById('global-note');
  const button = document.getElementById('save-note-btn');
  const status = document.getElementById('note-status');
  if (noteDirty) return;
  trackingCall({method: 'amf.www.production_tracking_planning.get_note',
    callback: function (r) {
      const note = r.message || {};
      textarea.value = note.text || '';
      textarea.disabled = !note.can_write;
      button.disabled = true;
      noteModified = note.modified;
      status.textContent = note.can_write ? 'Note partagée avec l’équipe' : 'Lecture seule selon vos droits';
    }, error: function () { status.textContent = 'Impossible de charger la note.'; }
  });
  if (noteBound) return;
  noteBound = true;
  textarea.addEventListener('input', function () { noteDirty = true; button.disabled = false; status.textContent = 'Modifications non enregistrées'; });
  button.addEventListener('click', function () {
    if (noteSaving) return;
    noteSaving = true;
    textarea.disabled = true;
    button.disabled = true;
    trackingCall({method: 'amf.www.production_tracking_planning.save_note', type: 'POST', args: {note_text: textarea.value, modified: noteModified},
      callback: function (r) { if (!r.message || r.exc) return; noteModified = r.message.modified; noteDirty = false; status.textContent = 'Note enregistrée'; },
      error: function () { status.textContent = 'Échec de l’enregistrement. Votre texte est conservé.'; },
      always: function () { noteSaving = false; textarea.disabled = false; button.disabled = !noteDirty; }
    });
  });
}
function reloadAll() { loadWorkOrders(); loadShipments(); loadGlobalNote(); }
function updateClock() {
  const now = new Date();
  ptSetText('clock-display', new Intl.DateTimeFormat('fr-CH', {hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich'}).format(now));
  ptSetText('date-display', new Intl.DateTimeFormat('fr-CH', {weekday: 'short', day: '2-digit', month: 'long', timeZone: 'Europe/Zurich'}).format(now));
}
frappe.ready(function () {
  document.body.classList.add('pt-planning-page');
  ptHydrateIcons();
  if (frappe.session.user === 'Guest') { window.location.href = '/login?redirect-to=' + encodeURIComponent(window.location.pathname + window.location.hash); return; }
  updateClock();
  setInterval(updateClock, 30000);
  reloadAll();
  document.getElementById('refresh-btn').addEventListener('click', () => window.location.reload());
  document.getElementById('toggle-client-btn').addEventListener('click', function () {
    ptOverview.hiddenCustomers = !ptOverview.hiddenCustomers;
    this.setAttribute('aria-pressed', String(ptOverview.hiddenCustomers));
    this.setAttribute('aria-label', ptOverview.hiddenCustomers ? 'Afficher les noms des clients' : 'Masquer les noms des clients');
    this.title = ptOverview.hiddenCustomers ? 'Afficher les clients' : 'Masquer les clients';
    renderShipments();
  });
  document.querySelectorAll('[data-open-planning]').forEach(button => button.addEventListener('click', () => document.getElementById('machining-tab').click()));
  document.querySelector('.pt-brand').addEventListener('click', function (event) { event.preventDefault(); document.getElementById('overview-tab').click(); });
});

// Independent machining planning controller. No Desk-only DataTable dependency.
(function () {
  "use strict";
  const state = {columns: [], rows: [], pending: new Map(), loaded: false,
    loading: false, saving: null, deleting: null, search: "", report: "", machine: "", quick: "all"};
  const api = "amf.www.production_tracking_planning.";
  const byId = id => document.getElementById(id);
  const numeric = new Set(["Int", "Float", "Currency", "Percent", "Check"]);

  function status(message, error) {
    byId("planning-status").textContent = message;
    byId("planning-status").classList.toggle("pt-error", !!error);
  }

  function equalValue(column, first, second) {
    if (numeric.has(column.fieldtype)) return Number(first || 0) === Number(second || 0);
    return String(first == null ? "" : first) === String(second == null ? "" : second);
  }

  function setBusy() {
    const busy = state.loading || !!state.saving || !!state.deleting;
    byId("planning-reload").disabled = busy;
    byId("planning-table").querySelectorAll("input, select, button").forEach(el => {
      el.disabled = busy || el.dataset.inactive === "1";
    });
  }

  const labels = {name: 'OF', production_item: 'Article', item_name: 'Désignation', rd_code: 'Code R&D', qty: 'Qté', progress: 'Avancement', expected_delivery_date_: 'Date prévue', priority: 'Priorité', machine: 'Machine', raw_material: 'Matière', drawing: 'Plan', docstatus: 'Statut', temps_de_fabrication_estime_jours: 'Estimation (j)'};
  const widths = {name: 110, production_item: 118, item_name: 230, rd_code: 115, qty: 80, progress: 132, expected_delivery_date_: 150, priority: 80, machine: 125, raw_material: 135, drawing: 155, docstatus: 100, temps_de_fabrication_estime_jours: 105};
  const UNASSIGNED = '__pt_unassigned__';

  function valuesFor(row) {
    const draft = state.pending.get(row.name);
    return Object.assign({}, row, draft ? draft.changes : {});
  }
  function matchesContext(row, includeMachine) {
    const values = valuesFor(row);
    if (state.report && !row._reports.includes(state.report)) return false;
    if (state.search && !state.columns.some(c => String(values[c.fieldname] == null ? '' : values[c.fieldname]).toLocaleLowerCase().includes(state.search))) return false;
    if (includeMachine && state.machine) {
      const machine = String(values.machine || '').trim();
      if (state.machine === UNASSIGNED ? !!machine : machine !== state.machine) return false;
    }
    return true;
  }
  function matchesQuick(row, filter) {
    const values = valuesFor(row);
    const days = ptDaysUntil(values.expected_delivery_date_);
    if (filter === 'overdue') return days !== null && days < 0;
    if (filter === 'today') return days === 0;
    if (filter === 'unassigned') return !String(values.machine || '').trim();
    if (filter === 'changed') return state.pending.has(row.name);
    return true;
  }
  function updateCount(visible) {
    byId('planning-count').textContent = visible + ' / ' + state.rows.length + ' OF · ' + state.columns.length + ' colonnes';
    byId('planning-pending-bar').hidden = state.pending.size === 0;
    byId('planning-pending-text').textContent = state.pending.size + ' ligne' + (state.pending.size > 1 ? 's modifiées' : ' modifiée') + ' · Enregistrez chaque ligne.';
    const base = state.rows.filter(row => matchesContext(row, true));
    byId('planning-quick-filters').querySelectorAll('button[data-filter]').forEach(button => {
      const active = button.dataset.filter === state.quick;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
      button.querySelector('[data-filter-count]').textContent = base.filter(row => matchesQuick(row, button.dataset.filter)).length;
    });
  }
  function renderSummary() {
    const rows = state.rows.filter(row => !row._unavailable);
    ptSetText('planning-kpi-total', rows.length);
    ptSetText('machining-tab-count', rows.length);
    const plugs = rows.filter(row => row._reports.some(name => name.startsWith('Plug'))).length;
    ptSetText('planning-kpi-parts', plugs + ' plugs · ' + (rows.length - plugs) + ' Valve Seats');
    ptSetText('planning-kpi-overdue', rows.filter(row => { const days = ptDaysUntil(row.expected_delivery_date_); return days !== null && days < 0; }).length);
    ptSetText('planning-kpi-unassigned', rows.filter(row => !String(row.machine || '').trim()).length);
    const estimated = rows.filter(row => row.temps_de_fabrication_estime_jours !== null && row.temps_de_fabrication_estime_jours !== '' && Number.isFinite(Number(row.temps_de_fabrication_estime_jours)));
    const load = estimated.reduce((sum, row) => sum + Number(row.temps_de_fabrication_estime_jours), 0);
    ptSetText('planning-kpi-load', estimated.length ? ptNumber(load, 1) + ' j' : '—');
    ptSetText('planning-kpi-load-detail', estimated.length === rows.length ? 'Total des estimations enregistrées' : (rows.length - estimated.length) + ' estimation(s) non renseignée(s)');
  }
  function renderWorkloads() {
    const groups = new Map();
    state.rows.filter(row => !row._unavailable && matchesContext(row, false)).forEach(row => {
      const machine = String(row.machine || '').trim();
      if (!groups.has(machine)) groups.set(machine, {count: 0, late: 0, days: 0});
      const group = groups.get(machine);
      group.count++;
      const days = ptDaysUntil(row.expected_delivery_date_);
      if (days !== null && days < 0) group.late++;
      const estimate = Number(row.temps_de_fabrication_estime_jours);
      if (Number.isFinite(estimate)) group.days += estimate;
    });
    const maximum = Math.max(1, ...Array.from(groups.values(), group => group.count));
    const target = byId('planning-workloads');
    target.innerHTML = '';
    Array.from(groups.entries()).sort((a,b) => b[1].count - a[1].count || a[0].localeCompare(b[0])).forEach(([machine, group]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'pt-workload';
      button.dataset.machine = machine || UNASSIGNED;
      button.setAttribute('aria-label', 'Filtrer : ' + (machine || 'Sans machine') + ', ' + group.count + ' OF');
      button.innerHTML = '<span class="pt-workload-heading"><span>' + escapeHTML(machine || 'Sans machine') + '</span><strong>' + group.count + ' OF</strong></span><span class="pt-workload-track"><i class="pt-load-late" style="width:' + (group.late / maximum * 100) + '%"></i><i style="width:' + ((group.count - group.late) / maximum * 100) + '%"></i></span><small>' + ptNumber(group.days, 1) + ' j estimés · ' + group.late + ' en retard</small>';
      target.appendChild(button);
    });
    if (!groups.size) target.innerHTML = '<p class="pt-empty">Aucun OF pour cette sélection.</p>';
  }
  function dateHint(td, value) {
    const info = ptDateInfo(value);
    let hint = td.querySelector('.pt-date-hint');
    if (!hint) { hint = document.createElement('span'); td.appendChild(hint); }
    hint.className = 'pt-date-hint' + (info.days !== null && info.days < 0 ? ' pt-date-late' : info.days === 0 ? ' pt-date-today' : '');
    hint.textContent = (info.days === null ? '' : ptFormatDate(value) + ' · ') + info.hint;
  }
  function render() {
    const head = byId('planning-table').tHead;
    const body = byId('planning-table').tBodies[0];
    head.innerHTML = '';
    body.innerHTML = '';
    const header = head.insertRow();
    ['Pièce'].concat(state.columns.map(c => labels[c.fieldname] || c.label), ['Actions']).forEach((label, index) => {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = label;
      if (index > 0 && index <= state.columns.length) {
        const column = state.columns[index - 1];
        th.title = column.label;
        if (column.fieldname === 'expected_delivery_date_') {
          th.innerHTML = escapeHTML(label) + ' ↓';
          th.className = 'pt-date-heading';
          th.setAttribute('aria-sort', 'ascending');
        }
      }
      header.appendChild(th);
    });
    let visible = 0;
    state.rows.forEach(row => {
      const draft = state.pending.get(row.name);
      const values = valuesFor(row);
      if (!matchesContext(row, true) || !matchesQuick(row, state.quick)) return;
      visible++;
      const tr = body.insertRow();
      tr.dataset.name = row.name;
      tr.classList.toggle('pt-dirty', !!draft);
      const days = ptDaysUntil(values.expected_delivery_date_);
      tr.classList.toggle('pt-overdue', days !== null && days < 0);
      const source = tr.insertCell();
      source.className = 'pt-source';
      const isPlug = row._reports.some(name => name.startsWith('Plug'));
      source.innerHTML = '<span class="pt-source-badge' + (isPlug ? '' : ' pt-seat') + '">' + (isPlug ? 'Plug' : 'Valve Seat') + '</span>';
      source.title = row._reports.join(' / ');
      state.columns.forEach(column => {
        const td = tr.insertCell();
        td.style.minWidth = (widths[column.fieldname] || Math.min(230, column.width)) + 'px';
        const value = values[column.fieldname];
        const editable = row._editable_fields.includes(column.fieldname) && !row._unavailable;
        if (numeric.has(column.fieldtype)) td.classList.add('pt-numeric-cell');
        if (editable) {
          const input = document.createElement(column.fieldtype === 'Select' ? 'select' : 'input');
          if (column.fieldtype === 'Select') {
            const options = (column.options || '').split('\n');
            if (!options.includes('')) options.unshift('');
            if (value && !options.includes(String(value))) options.push(String(value));
            options.forEach(option => {
              const el = document.createElement('option');
              el.value = option;
              el.textContent = option || '—';
              input.appendChild(el);
            });
          } else {
            input.type = column.fieldtype === 'Date' ? 'date' : numeric.has(column.fieldtype) ? 'number' : 'text';
            if (input.type === 'number') input.step = ['Int', 'Check'].includes(column.fieldtype) ? '1' : 'any';
          }
          input.value = value == null ? '' : value;
          input.required = !!column.reqd;
          input.dataset.field = column.fieldname;
          input.setAttribute('aria-label', (labels[column.fieldname] || column.label) + ' · ' + row.name);
          input.title = column.label;
          if (column.fieldname === 'production_item') input.title += ' · Met aussi à jour la nomenclature par défaut et les champs de l’article';
          if (column.fieldname === 'machine') input.placeholder = 'Affecter…';
          if (column.fieldname === 'raw_material') input.placeholder = 'À préciser';
          if (column.fieldname === 'drawing') input.placeholder = 'Lien vers le plan';
          input.classList.toggle('pt-changed', !!draft && Object.prototype.hasOwnProperty.call(draft.changes, column.fieldname));
          td.appendChild(input);
        } else if (column.fieldname === 'name') {
          td.classList.add('pt-id-cell');
          const link = document.createElement('a');
          link.href = '/desk#Form/Work%20Order/' + encodeURIComponent(row.name);
          link.target = '_blank';
          link.rel = 'noopener';
          link.textContent = row.name;
          td.appendChild(link);
        } else if (column.fieldname === 'docstatus') {
          td.innerHTML = '<span class="pt-badge pt-badge-gray">' + escapeHTML(['Brouillon','Validé','Annulé'][Number(value)] || value) + '</span>';
          td.title = 'docstatus = ' + value + ' · ' + column.reason;
        } else {
          td.textContent = value == null ? '—' : numeric.has(column.fieldtype) ? ptNumber(value, 2) : value;
          td.classList.add('pt-readonly');
          if (column.fieldname === 'item_name') td.classList.add('pt-name-cell');
          td.title = (value == null ? '' : value + ' · ') + (column.reason || 'Lecture seule pour cet ordre');
        }
        if (column.fieldname === 'expected_delivery_date_') dateHint(td, value);
        if (column.fieldtype === 'Attach' && value && /^(\/files\/|\/private\/files\/|https?:\/\/)/i.test(value)) {
          const link = document.createElement('a');
          link.href = value;
          link.target = '_blank';
          link.rel = 'noopener';
          link.innerHTML = ptIcon('link') + 'Ouvrir le plan';
          link.className = 'pt-drawing-link';
          td.appendChild(link);
        }
      });
      const actions = tr.insertCell();
      actions.className = 'pt-actions';
      const controls = document.createElement('div');
      controls.className = 'pt-row-controls';
      controls.innerHTML = '<span class="pt-row-saved">' + ptIcon('check') + 'À jour</span>';
      [['save','Enregistrer','save'], ['discard','Annuler les modifications','undo'], ['delete','Supprimer cet OF','trash']].forEach(([action, label, icon]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.innerHTML = ptIcon(icon);
        button.title = label + ' · ' + row.name;
        button.setAttribute('aria-label', label + ' · ' + row.name);
        button.dataset.action = action;
        if (action === 'delete') {
          button.dataset.inactive = row._can_delete && !row._unavailable ? '0' : '1';
          if (row._delete_reason) button.title = row._delete_reason;
        } else button.dataset.inactive = draft && (action === 'discard' || !row._unavailable) ? '0' : '1';
        controls.appendChild(button);
      });
      actions.appendChild(controls);
    });
    if (!visible) {
      const cell = body.insertRow().insertCell();
      cell.colSpan = state.columns.length + 2;
      cell.className = 'pt-empty';
      cell.innerHTML = ptIcon(state.quick === 'changed' ? 'check' : 'search') + '<br>' + (state.quick === 'changed' ? 'Aucune modification en attente pour cette sélection.' : 'Aucun OF ne correspond à vos filtres.');
    }
    renderSummary();
    renderWorkloads();
    updateCount(visible);
    setBusy();
  }

  function loadPlanning(preservePending, message) {
    if (state.loading || state.saving || state.deleting) return;
    if (!preservePending && state.pending.size) {
      if (!window.confirm("Abandonner les modifications non enregistrées et actualiser le planning ?")) return;
      state.pending.clear();
    }
    state.loading = true;
    setBusy();
    status("Chargement du planning complet…");
    trackingCall({
      method: api + "get_machining_planning",
      callback: function (r) {
        if (!r.message || r.exc) return;
        const data = r.message;
        if (data.today) ptSiteToday = data.today;
        const oldRows = state.rows;
        state.columns = data.columns;
        state.rows = data.rows;
        oldRows.forEach(row => {
          if (state.pending.has(row.name) && !state.rows.some(fresh => fresh.name === row.name)) {
            state.rows.push(Object.assign({}, row, {_unavailable: true}));
          }
        });
        state.loaded = true;
        const filter = byId("planning-report");
        filter.innerHTML = '<option value="">Toutes les pièces</option>';
        data.reports.forEach(report => {
          const option = document.createElement("option");
          option.value = report;
          option.textContent = (report.startsWith('Plug') ? 'Plugs' : 'Valve Seats') + ' (' + data.counts[report] + ')';
          filter.appendChild(option);
        });
        filter.value = state.report;
        const machineFilter = byId('planning-machine');
        machineFilter.innerHTML = '<option value="">Toutes les machines</option><option value="' + UNASSIGNED + '">Sans machine</option>';
        const machines = Array.from(new Set(state.rows.map(row => String(row.machine || '').trim()).filter(Boolean))).sort();
        if (state.machine && state.machine !== UNASSIGNED && !machines.includes(state.machine)) machines.push(state.machine);
        machines.forEach(machine => { const option = document.createElement('option'); option.value = machine; option.textContent = machine; machineFilter.appendChild(option); });
        machineFilter.value = state.machine;
        status(message || '');
        ptSync('planning', false);
        render();
      },
      error: function () { status("Impossible de charger le planning. Réessayez avec « Actualiser le planning ».", true); ptSync('planning', true); },
      always: function () { state.loading = false; setBusy(); }
    });
  }

  function updateDraft(event) {
    const input = event.target;
    if (!input.dataset.field) return;
    const tr = input.closest("tr");
    const row = state.rows.find(row => row.name === tr.dataset.name);
    const column = state.columns.find(c => c.fieldname === input.dataset.field);
    let draft = state.pending.get(row.name) || {changes: {}, modified: row._modified};
    if (equalValue(column, row[column.fieldname], input.value)) delete draft.changes[column.fieldname];
    else draft.changes[column.fieldname] = input.value;
    const dirty = Object.keys(draft.changes).length > 0;
    if (dirty) state.pending.set(row.name, draft);
    else state.pending.delete(row.name);
    input.classList.toggle("pt-changed", Object.prototype.hasOwnProperty.call(draft.changes, column.fieldname));
    tr.classList.toggle("pt-dirty", dirty);
    if (column.fieldname === 'expected_delivery_date_') {
      dateHint(input.parentElement, input.value);
      const days = ptDaysUntil(input.value);
      tr.classList.toggle('pt-overdue', days !== null && days < 0);
    }
    tr.querySelectorAll('button[data-action="save"], button[data-action="discard"]').forEach(button => {
      button.dataset.inactive = dirty ? "0" : "1";
      button.disabled = !dirty;
    });
    updateCount(byId("planning-table").tBodies[0].querySelectorAll("tr[data-name]").length);
    status(dirty ? "Modifications non enregistrées. Enregistrez la ligne pour appliquer les changements." : "");
  }

  function saveRow(name) {
    const draft = state.pending.get(name);
    if (!draft || state.saving || state.deleting || state.loading) return;
    const tr = Array.from(byId("planning-table").tBodies[0].rows).find(tr => tr.dataset.name === name);
    if (!Array.from(tr.querySelectorAll("input, select")).every(input => input.reportValidity())) return;
    state.saving = name;
    setBusy();
    status("Enregistrement de " + name + "…");
    let saved = false;
    trackingCall({
      method: api + "save_machining_work_order", type: "POST",
      args: {name: name, changes: JSON.stringify(draft.changes), modified: draft.modified},
      callback: function (r) {
        if (!r.message || r.exc) return;
        saved = true;
        state.pending.delete(name);
      },
      error: function () { status("Échec de l’enregistrement de " + name + ". Vos modifications sont conservées. En cas de conflit, actualisez le planning.", true); },
      always: function () {
        state.saving = null;
        if (saved) {
          loadPlanning(true, name + " enregistré. Si ses valeurs ne correspondent plus aux filtres des rapports, il quitte le planning.");
          loadWorkOrders();
        } else setBusy();
      }
    });
  }

  function deleteRow(name) {
    const row = state.rows.find(row => row.name === name);
    if (!row || !row._can_delete || row._unavailable || state.saving || state.deleting || state.loading) return;
    const draft = state.pending.get(name);
    const message = "Supprimer l’ordre de fabrication brouillon " + name + " dans l’ERP ?\n\n" +
      "Cette action supprime l’ordre de fabrication et sa ligne dans les rapports." +
      (draft ? "\nLes modifications non enregistrées de cette ligne seront perdues." : "");
    if (!window.confirm(message)) return;
    state.deleting = name;
    setBusy();
    status("Suppression de " + name + "…");
    let deleted = false;
    trackingCall({
      method: api + "delete_machining_work_order", type: "POST",
      args: {name: name, modified: draft ? draft.modified : row._modified},
      callback: function (r) {
        if (!r.message || !r.message.deleted || r.exc) return;
        deleted = true;
        state.pending.delete(name);
        state.rows = state.rows.filter(row => row.name !== name);
        render();
      },
      error: function () {
        status("Échec de la suppression de " + name + ". Vos modifications sont conservées. Vérifiez vos droits, les documents liés ou actualisez le planning en cas de conflit.", true);
      },
      always: function () {
        state.deleting = null;
        if (deleted) {
          loadPlanning(true, name + " supprimé.");
          loadWorkOrders();
        } else setBusy();
      }
    });
  }

  frappe.ready(function () {
    if (frappe.session.user === "Guest") return;
    const tabs = [byId("overview-tab"), byId("machining-tab")];
    function activateTab(tab) {
      tabs.forEach(button => {
        const active = button === tab;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
        byId(button.getAttribute("aria-controls")).hidden = !active;
      });
      window.history.replaceState(null, "", window.location.pathname + window.location.search + (tab === tabs[1] ? "#usinage" : ''));
      if (tab === tabs[1] && !state.loaded) loadPlanning(true);
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activateTab(tab));
      tab.addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[1] : tabs[1 - index];
        activateTab(next);
        next.focus();
      });
    });
    byId("planning-reload").addEventListener("click", () => loadPlanning(false));
    byId("planning-search").addEventListener("input", event => {
      state.search = event.target.value.toLocaleLowerCase().trim();
      render();
    });
    byId("planning-report").addEventListener("change", event => {
      state.report = event.target.value;
      render();
    });
    byId('planning-machine').addEventListener('change', event => { state.machine = event.target.value; render(); });
    byId('planning-quick-filters').addEventListener('click', event => {
      const button = event.target.closest('button[data-filter]');
      if (!button) return;
      state.quick = button.dataset.filter;
      render();
    });
    function clearFilters() {
      state.search = ''; state.report = ''; state.machine = ''; state.quick = 'all';
      byId('planning-search').value = ''; byId('planning-report').value = ''; byId('planning-machine').value = '';
    }
    byId('planning-clear-filters').addEventListener('click', () => { clearFilters(); render(); });
    byId('planning-show-changed').addEventListener('click', () => { clearFilters(); state.quick = 'changed'; render(); byId('planning-table-wrap').focus(); });
    byId('planning-load-toggle').addEventListener('click', function () {
      const expanded = this.getAttribute('aria-expanded') === 'true';
      this.setAttribute('aria-expanded', String(!expanded));
      byId('planning-load-panel').hidden = expanded;
      if (!expanded) renderWorkloads();
    });
    byId('planning-workloads').addEventListener('click', event => {
      const button = event.target.closest('button[data-machine]');
      if (!button) return;
      state.machine = button.dataset.machine;
      byId('planning-machine').value = state.machine;
      render();
    });
    byId("planning-table").addEventListener("input", updateDraft);
    byId("planning-table").addEventListener("change", updateDraft);
    byId("planning-table").addEventListener("click", event => {
      const button = event.target.closest("button[data-action]");
      if (!button || button.disabled || state.loading || state.saving || state.deleting) return;
      const name = button.closest("tr").dataset.name;
      if (button.dataset.action === "save") saveRow(name);
      else if (button.dataset.action === "delete") deleteRow(name);
      else {
        state.pending.delete(name);
        state.rows = state.rows.filter(row => row.name !== name || !row._unavailable);
        render();
        status("Modifications de " + name + " annulées.");
      }
    });
    loadPlanning(true);
    if (window.location.hash === "#usinage") activateTab(tabs[1]);
    window.addEventListener("beforeunload", event => {
      if (!state.pending.size && !noteDirty && !state.saving && !state.deleting && !noteSaving) return;
      event.preventDefault();
      event.returnValue = "";
    });
  });
}());
