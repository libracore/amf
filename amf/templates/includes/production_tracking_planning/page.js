// V12 website frappe.call runs opts.always BEFORE opts.callback and ignores
// opts.error. Use jqXHR completion handlers to guarantee callback/error/always order.
function trackingCall(opts) {
  return frappe.call({method: opts.method, args: opts.args || {}, type: opts.type || "POST"})
    .done(function (data) {
      if (data && !data.exc) { if (opts.callback) opts.callback(data); }
      else if (opts.error) opts.error(data);
    })
    .fail(function (xhr) { if (opts.error) opts.error(xhr); })
    .always(function () { if (opts.always) opts.always(); });
}

// ============================================================
//  PAGE : Production Tracking
//  Description : Gestion des OF, expéditions et notes de suivi
// ============================================================

window.addEventListener("load", function () {
  document.body.classList.add("pt-planning-page");
  document.querySelectorAll("nav.navbar, footer.web-footer").forEach(el => { el.style.display = "none"; });
});

// ============================================================
// 1. WORK ORDERS
// ============================================================
function loadWorkOrders() {
  trackingCall({
    method: "amf.www.production_tracking_planning.get_work_orders",
    callback: function (r) {
      if (!r.message) return;
      renderSubLists("ongoing",  r.message.ongoing  || []);
      renderSubLists("upcoming", r.message.upcoming || []);
    }
  });
}

function renderSubLists(baseId, data) {
  const assemblage = data.filter(it => it.operation_type === "Assemblage");
  const usinage    = data.filter(it => it.operation_type === "Usinage");

  renderList(`${baseId}-assemblage`, assemblage, baseId, "assemblage");
  renderList(`${baseId}-usinage`,    usinage,    baseId, "usinage");
}

function escapeHTML(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function renderList(containerId, data, baseId, opType) {
  const target = document.getElementById(containerId);
  if (!target) return;
  if (!data || !data.length) {
    target.innerHTML = '<p class="text-muted">Aucun ordre de fabrication</p>';
    return;
  }
  target.innerHTML = data.map((item, index) => {
    const timer = item.timer_info || {};
    const statusClass = timer.status === "IN PROCESS" ? "status-in-process" : "";
    const stateClass = `${baseId}-${opType}`;
    const ops = (timer.operators || "").split("/").map(o => o.trim()).filter(Boolean);
    const opsDisplay = escapeHTML(ops.slice(0, 2).join(" • ") + (ops.length > 2 ? " • …" : ""));
    const href = "/desk#Form/Work%20Order/" + encodeURIComponent(item.name);
    const name = escapeHTML(item.name), label = escapeHTML(item.item_name);
    if (index < 3) {
      return `<a class="order full ${stateClass} ${statusClass}" href="${href}" target="_blank" rel="noopener"><span class="order-left"><b>${name}</b> – ${label}</span><span class="order-right">${opsDisplay}</span></a>`;
    }
    const tooltip = `<div class="tooltip-content ${stateClass} ${statusClass}">${label}${opsDisplay ? " // <b>" + opsDisplay + "</b>" : ""}</div>`;
    return `<a class="order compact ${stateClass} ${statusClass}" href="${href}" target="_blank" rel="noopener" data-tooltip="${escapeHTML(tooltip)}"><span class="compact-number">${name}</span></a>`;
  }).join("");
}

let currentCompact = null;

document.addEventListener("mousemove", function (e) {
  if (!currentCompact) return;

  const tooltip = document.getElementById("big-tooltip");
  const tooltipWidth = tooltip.offsetWidth;

  // Centre la tooltip sous la souris
  tooltip.style.left = (e.pageX - tooltipWidth / 2) + "px";
  tooltip.style.top  = (e.pageY + 20) + "px";
});

// Quand on entre dans une carte compact
document.addEventListener("mouseenter", function (e) {

  const el = e.target instanceof Element ? e.target.closest(".order.compact") : null;
  if (!el) return;

  currentCompact = el;

  const tooltip = document.getElementById("big-tooltip");
  tooltip.innerHTML = el.getAttribute("data-tooltip");

  tooltip.classList.add("visible");
}, true);

// Quand on quitte une carte compact
document.addEventListener("mouseleave", function (e) {

  const el = e.target instanceof Element ? e.target.closest(".order.compact") : null;
  if (!el) return;

  const tooltip = document.getElementById("big-tooltip");
  tooltip.classList.remove("visible");

  currentCompact = null;
}, true);



// ============================================================
// 2. SHIPMENTS
// ============================================================
function getWeekInfo() {
  const now = new Date();
  const day = now.getDay();
  const diffToMonday = (day === 0 ? -6 : 1) - day;
  const monday = new Date(now);
  monday.setDate(now.getDate() + diffToMonday);
  const friday = new Date(monday);
  friday.setDate(monday.getDate() + 6);

  const weekNumber = getWeekNumber(now);
  const format = d => d.toLocaleDateString("fr-CH", { day: "2-digit", month: "2-digit" });

  return { week: weekNumber, start: format(monday), end: format(friday) };
}

function getWeekNumber(d) {
  d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

function loadShipments() {
  trackingCall({
    method: "amf.www.production_tracking_planning.get_shipments",
    callback: function (r) {
      const target = document.getElementById("shipments");
      const title = document.getElementById("shipments-title");

      const info = getWeekInfo();
      title.innerHTML = `Commandes à expédier – Semaine <b>${info.week}</b> du <b>${info.start}</b> au <b>${info.end}</b>`;

      if (!r.message || r.message.length === 0) {
        target.innerHTML = "<p class='text-muted'>Aucune commande prévue cette semaine</p>";
        return;
      }

      let html = `<div class="shipment-list">`;
      r.message.forEach(so => {
        const date = new Date(so.delivery_date);
        const formattedDate = date.toLocaleDateString("fr-CH", { day: "2-digit", month: "2-digit" });

        let statusClass = "";
        if (so.shipment_status === "green") statusClass = "shipment-green";
        else if (so.shipment_status === "orange") statusClass = "shipment-orange";
        else statusClass = "shipment-white";

        html += `
          <a class="shipment-item ${statusClass}"
              href="/desk#Form/Sales%20Order/${encodeURIComponent(so.name)}"
              target="_blank">
            <span class="shipment-id"><b>${escapeHTML(so.name)}</b></span>
            <span class="shipment-customer">${escapeHTML(so.customer_name || "")}</span>
            <span class="shipment-date">${formattedDate}</span>
          </a>`;
      });
      html += `</div>`;
      target.innerHTML = html;
    }
  });
}

// ============================================================
// 3. GLOBAL NOTE  (Doctype: Production Notes)
// ============================================================
let noteModified = null;
let noteDirty = false;
let noteSaving = false;
let noteBound = false;

function loadGlobalNote() {
  const textarea = document.getElementById("global-note");
  const button = document.getElementById("save-note-btn");
  const status = document.getElementById("note-status");
  trackingCall({
    method: "amf.www.production_tracking_planning.get_note",
    callback: function (r) {
      const note = r.message || {};
      textarea.value = note.text || "";
      textarea.disabled = !note.can_write;
      button.disabled = true;
      noteModified = note.modified;
      status.textContent = note.can_write ? "" : "Note en lecture seule selon vos droits d’accès.";
    },
    error: function () { status.textContent = "Impossible de charger la note."; }
  });
  if (noteBound) return;
  noteBound = true;
  textarea.addEventListener("input", function () {
    noteDirty = true;
    button.disabled = false;
    status.textContent = "Modifications non enregistrées";
  });
  button.addEventListener("click", function () {
    if (noteSaving) return;
    noteSaving = true;
    textarea.disabled = true;
    button.disabled = true;
    trackingCall({
      method: "amf.www.production_tracking_planning.save_note", type: "POST",
      args: {note_text: textarea.value, modified: noteModified},
      callback: function (r) {
        if (!r.message || r.exc) return;
        noteModified = r.message.modified;
        noteDirty = false;
        status.textContent = "Note enregistrée";
      },
      error: function () { status.textContent = "Échec de l’enregistrement. Votre texte est conservé."; },
      always: function () { noteSaving = false; textarea.disabled = false; button.disabled = !noteDirty; }
    });
  });
}

// ============================================================
// 4. RELOAD & INITIALISATION
// ============================================================
function reloadAll() {
  loadWorkOrders();
  loadShipments();
  loadGlobalNote();
}


frappe.ready(function () {
  if (frappe.session.user === 'Guest') {
    window.location.href = "/login?redirect-to=" + encodeURIComponent(window.location.pathname + window.location.hash);
    return; // stop ici
  }

  reloadAll();

  const btn = document.getElementById("refresh-btn");
  if (btn) {
    btn.addEventListener("click", function() {
      window.location.reload();
    });
  }

  const toggleBtn = document.getElementById("toggle-client-btn");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", function() {
      document.querySelectorAll(".shipment-customer").forEach(el => {
        el.classList.toggle("hidden-customer");
      });
    });
  }
});

// === HORLOGE TEMPS RÉEL ===
function updateClock() {
  const now = new Date();
  const formatted = now.toLocaleTimeString("fr-CH", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
  const clockEl = document.getElementById("clock-display");
  if (clockEl) clockEl.textContent = formatted;
}

// Met à jour toutes les secondes
setInterval(updateClock, 1000);
updateClock();

// Independent machining planning controller. No Desk-only DataTable dependency.
(function () {
  "use strict";
  const state = {columns: [], rows: [], pending: new Map(), loaded: false,
    loading: false, saving: null, search: "", report: ""};
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
    const busy = state.loading || !!state.saving;
    byId("planning-reload").disabled = busy;
    byId("planning-table").querySelectorAll("input, select, button").forEach(el => {
      el.disabled = busy || el.dataset.inactive === "1";
    });
  }

  function updateCount(visible) {
    byId("planning-count").textContent = `${visible} / ${state.rows.length} OF · ${state.pending.size} ligne(s) à enregistrer`;
  }

  function render() {
    const head = byId("planning-table").tHead;
    const body = byId("planning-table").tBodies[0];
    head.innerHTML = "";
    body.innerHTML = "";
    const header = head.insertRow();
    ["Rapport"].concat(state.columns.map(c => c.label + (c.fieldname === "expected_delivery_date_" ? " ↑" : "")), ["Actions"]).forEach(label => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = label;
      header.appendChild(th);
    });
    let visible = 0;
    state.rows.forEach(row => {
      const draft = state.pending.get(row.name);
      const values = Object.assign({}, row, draft ? draft.changes : {});
      if (state.report && !row._reports.includes(state.report)) return;
      if (state.search && !state.columns.some(c => String(values[c.fieldname] == null ? "" : values[c.fieldname]).toLocaleLowerCase().includes(state.search))) return;
      visible++;
      const tr = body.insertRow();
      tr.dataset.name = row.name;
      tr.classList.toggle("pt-dirty", !!draft);
      const source = tr.insertCell();
      source.className = "pt-source";
      source.textContent = row._reports.map(name => name.startsWith("Plug") ? "Plug" : "Valve Seat").join(" / ");
      source.title = row._reports.join(" / ");
      state.columns.forEach(column => {
        const td = tr.insertCell();
        td.style.minWidth = column.width + "px";
        const value = values[column.fieldname];
        const editable = row._editable_fields.includes(column.fieldname) && !row._unavailable;
        if (editable) {
          const input = document.createElement(column.fieldtype === "Select" ? "select" : "input");
          if (column.fieldtype === "Select") {
            const options = (column.options || "").split("\n");
            if (!options.includes("")) options.unshift("");
            if (value && !options.includes(String(value))) options.push(String(value));
            options.forEach(option => {
              const el = document.createElement("option");
              el.value = option;
              el.textContent = option || "—";
              input.appendChild(el);
            });
          } else {
            input.type = column.fieldtype === "Date" ? "date" : numeric.has(column.fieldtype) ? "number" : "text";
            if (input.type === "number") input.step = ["Int", "Check"].includes(column.fieldtype) ? "1" : "any";
          }
          input.value = value == null ? "" : value;
          input.required = !!column.reqd;
          input.dataset.field = column.fieldname;
          input.setAttribute("aria-label", column.label + " · " + row.name);
          input.title = column.label;
          if (column.fieldname === "production_item") input.title += " · Met aussi à jour la nomenclature par défaut et les champs de l’article";
          input.classList.toggle("pt-changed", !!draft && Object.prototype.hasOwnProperty.call(draft.changes, column.fieldname));
          td.appendChild(input);
        } else if (column.fieldname === "name") {
          const link = document.createElement("a");
          link.href = "/desk#Form/Work%20Order/" + encodeURIComponent(row.name);
          link.target = "_blank";
          link.rel = "noopener";
          link.textContent = row.name;
          td.appendChild(link);
        } else {
          td.textContent = value == null ? "" : value;
          td.className = "pt-readonly";
          td.title = column.reason || "Lecture seule pour cet ordre de fabrication";
        }
        if (column.fieldtype === "Attach" && value && /^(\/files\/|\/private\/files\/|https?:\/\/)/i.test(value)) {
          const link = document.createElement("a");
          link.href = value;
          link.target = "_blank";
          link.rel = "noopener";
          link.textContent = "Ouvrir";
          link.className = "pt-drawing-link";
          td.appendChild(link);
        }
      });
      const actions = tr.insertCell();
      actions.className = "pt-actions";
      [["save", "Enregistrer"], ["discard", "Annuler"]].forEach(([action, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = state.saving === row.name && action === "save" ? "Enregistrement…" : label;
        button.dataset.action = action;
        button.dataset.inactive = draft && (action === "discard" || !row._unavailable) ? "0" : "1";
        actions.appendChild(button);
      });
    });
    if (!visible) {
      const cell = body.insertRow().insertCell();
      cell.colSpan = state.columns.length + 2;
      cell.className = "pt-empty";
      cell.textContent = "Aucun ordre de fabrication pour cette sélection.";
    }
    updateCount(visible);
    setBusy();
  }

  function loadPlanning(preservePending, message) {
    if (state.loading || state.saving) return;
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
        filter.innerHTML = '<option value="">Tous les rapports</option>';
        data.reports.forEach(report => {
          const option = document.createElement("option");
          option.value = report;
          option.textContent = report + " (" + data.counts[report] + ")";
          filter.appendChild(option);
        });
        filter.value = state.report;
        status(message || "Planning chargé. Les lignes sont triées par date prévue.");
        render();
      },
      error: function () { status("Impossible de charger le planning. Réessayez avec « Actualiser le planning ».", true); },
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
    tr.querySelectorAll("button").forEach(button => {
      button.dataset.inactive = dirty ? "0" : "1";
      button.disabled = !dirty;
    });
    updateCount(byId("planning-table").tBodies[0].querySelectorAll("tr[data-name]").length);
    status(dirty ? "Modifications non enregistrées. Enregistrez la ligne pour appliquer les changements." : "");
  }

  function saveRow(name) {
    const draft = state.pending.get(name);
    if (!draft || state.saving || state.loading) return;
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
      window.history.replaceState(null, "", tab === tabs[1] ? "#usinage" : window.location.pathname);
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
    byId("planning-table").addEventListener("input", updateDraft);
    byId("planning-table").addEventListener("change", updateDraft);
    byId("planning-table").addEventListener("click", event => {
      const button = event.target.closest("button[data-action]");
      if (!button || state.loading || state.saving) return;
      const name = button.closest("tr").dataset.name;
      if (button.dataset.action === "save") saveRow(name);
      else {
        state.pending.delete(name);
        state.rows = state.rows.filter(row => row.name !== name || !row._unavailable);
        render();
        status("Modifications de " + name + " annulées.");
      }
    });
    if (window.location.hash === "#usinage") activateTab(tabs[1]);
    window.addEventListener("beforeunload", event => {
      if (!state.pending.size && !noteDirty && !state.saving && !noteSaving) return;
      event.preventDefault();
      event.returnValue = "";
    });
  });
}());
