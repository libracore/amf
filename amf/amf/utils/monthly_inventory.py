# -*- coding: utf-8 -*-
"""Monthly cycle counts for ERPNext v12. Never write Bin or SLE directly."""
from __future__ import unicode_literals

import hashlib
import json
import math
import random
from decimal import Decimal
from contextlib import contextmanager
from html import escape

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, get_url_to_form, now_datetime, nowdate
from erpnext.stock.utils import get_stock_balance
from erpnext.stock.stock_ledger import get_previous_sle

SETTINGS = "Monthly Inventory Settings"
CHECK = "Monthly Inventory Check"
DEFAULT_ASSIGNEE = "alexandre.trachsel@amf.ch"
SAMPLE_SIZE = 10
MANAGERS = {"System Manager", "Stock Manager"}
PRECISION = 6
EDITABLE_ROW_FIELDS = ("counted", "counted_qty", "counted_rate", "reason",
                       "correction_type", "correction_document")
SNAPSHOT_FIELDS = ("item_code", "item_name", "warehouse", "stock_uom", "tracked_item",
                   "current_qty", "current_rate", "ledger_token", "snapshot_on")
PROTECTED_ROW_FIELDS = SNAPSHOT_FIELDS + ("checked_by", "checked_on", "resolved",
                                          "qty_difference", "value_difference", "row_status")
PROTECTED_FIELDS = ("company", "warehouse_root", "period", "assigned_to", "due_date", "selected_items",
                    "selection_log", "reconciliation", "status", "completed_on", "completed_by",
                    "reference_count", "checked_rows", "total_rows", "currency")


def is_manager(user=None):
    return (user or frappe.session.user) == "Administrator" or bool(
        MANAGERS.intersection(frappe.get_roles(user)))


def require_manager():
    if not is_manager():
        frappe.throw(_("Only a Stock Manager or System Manager can do this."), frappe.PermissionError)


def permission_query(user=None):
    user = user or frappe.session.user
    if is_manager(user):
        return ""
    return "`tabMonthly Inventory Check`.assigned_to = {0}".format(frappe.db.escape(user))


def has_permission(doc, user=None, ptype=None):
    user = user or frappe.session.user
    if not is_manager(user) and user != doc.assigned_to:
        return False


@contextmanager
def transition(name):
    previous = getattr(frappe.local, "monthly_inventory_transition", None)
    frappe.local.monthly_inventory_transition = name
    try:
        yield
    finally:
        frappe.local.monthly_inventory_transition = previous


def internal_change(doc):
    return getattr(frappe.local, "monthly_inventory_transition", None) == doc.name


def load_locked_check(name):
    # Every MIC writer first locks this unique parent row (including core save).
    # Do not lock the child range: v12/MariaDB may scan and lock the whole table.
    records = frappe.db.sql("SELECT * FROM `tabMonthly Inventory Check` WHERE name=%s FOR UPDATE", name, as_dict=True)
    if not records:
        frappe.throw(_("Inventory check {0} does not exist.").format(name), frappe.DoesNotExistError)
    data = records[0]
    snapshot = frappe.db.sql("SELECT modified FROM `tabMonthly Inventory Check` WHERE name=%s", name)
    if not snapshot or comparable(snapshot[0][0]) != comparable(data.modified):
        # Under REPEATABLE READ, an earlier query may have established an old
        # snapshot. Never combine its children with a newer locked parent.
        frappe.throw(_("This inventory check changed during the request. Reload it before saving."),
                     frappe.TimestampMismatchError)
    data["doctype"] = CHECK
    data["rows"] = frappe.db.sql("""SELECT * FROM `tabMonthly Inventory Check Row` FORCE INDEX (parent)
        WHERE parent=%s AND parenttype=%s AND parentfield='rows' ORDER BY idx""", (name, CHECK), as_dict=True)
    return frappe.get_doc(data)


def lock_check(name, write=True):
    # Lock before loading: two requests cannot create two adjustment vouchers.
    doc = load_locked_check(name)
    if write:
        doc.check_permission("write")
        if not is_manager() and frappe.session.user != doc.assigned_to:
            frappe.throw(_("This inventory check is assigned to another user."), frappe.PermissionError)
    return doc


def validate_settings(doc):
    doc.sample_size = doc.minimum_items = doc.maximum_items = SAMPLE_SIZE
    doc.warehouse_root = production_root(doc.company).name if doc.company else None
    if not 1 <= cint(doc.due_day) <= 28:
        frappe.throw(_("The due day must be between 1 and 28."))
    groups = get_inventory_item_groups()
    synchronize_group_rows(doc, groups)
    seen = set()
    for row in doc.excluded_items:
        if row.item_code in seen:
            frappe.throw(_("Duplicate excluded reference: {0}").format(row.item_code))
        seen.add(row.item_code)
    if cint(doc.enabled):
        if not doc.company:
            frappe.throw(_("Choose a Company before enabling monthly inventory."))
        validate_assignee(doc.assigned_to)
        if len(get_eligible_references(doc, groups)) < SAMPLE_SIZE:
            frappe.throw(_("The enabled item groups and exclusions must leave at least {0} active stock references.").format(SAMPLE_SIZE))


def get_inventory_item_groups():
    return frappe.get_all("Item Group", fields=["name", "parent_item_group"], order_by="lft, name")


def default_group_enabled(name):
    return cint(name.strip().lower() != "product")


def synchronize_group_rows(doc, groups):
    """Add new groups without resetting saved choices or dropping exclusions."""
    seen = set()
    for row in doc.item_groups:
        if row.item_group in seen:
            frappe.throw(_("Duplicate item group: {0}").format(row.item_group))
        seen.add(row.item_group)
        row.enabled = cint(row.enabled)
        if row.enabled not in (0, 1):
            frappe.throw(_("Item group Enabled must be checked or unchecked."))
    previous = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
    previous_rules = {row.item_group: row.enabled for row in previous.item_groups} if previous else {}
    for group in groups:
        if group.name not in seen:
            doc.append("item_groups", {"item_group": group.name,
                "enabled": previous_rules.get(group.name, default_group_enabled(group.name))})


def effective_item_groups(settings, groups):
    """A disabled group vetoes its whole subtree, including enabled children."""
    parents = {group.name: group.parent_item_group for group in groups}
    rules = {group.name: default_group_enabled(group.name) for group in groups}
    rules.update({row.item_group: cint(row.enabled) for row in settings.item_groups})
    enabled = []
    for name in parents:
        current, path = name, set()
        while current:
            if current in path or current not in parents:
                frappe.throw(_("Invalid Item Group hierarchy. Repair the item group tree before generating inventory checks."))
            path.add(current)
            if not rules[current]:
                break
            current = parents[current]
        else:
            enabled.append(name)
    return enabled


def get_eligible_references(settings, groups=None):
    groups = groups if groups is not None else get_inventory_item_groups()
    enabled = effective_item_groups(settings, groups)
    if not enabled:
        return []
    excluded = sorted({row.item_code for row in settings.excluded_items if row.item_code})
    values = list(enabled) + [nowdate()]
    condition = ""
    if excluded:
        condition = " AND name NOT IN ({0})".format(", ".join(["%s"] * len(excluded)))
        values.extend(excluded)
    return [row[0] for row in frappe.db.sql("""SELECT name FROM tabItem
        WHERE item_group IN ({0}) AND IFNULL(disabled, 0)=0
        AND is_stock_item=1 AND IFNULL(has_variants, 0)=0 AND docstatus<2
        AND (end_of_life IS NULL OR end_of_life >= %s)""".format(", ".join(["%s"] * len(enabled)))
        + condition + " ORDER BY name", values)]


@frappe.whitelist()
def get_item_group_defaults():
    require_manager()
    return [{"item_group": group.name, "enabled": default_group_enabled(group.name)}
            for group in get_inventory_item_groups()]


def validate_assignee(user):
    details = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    if not details or not details.enabled or details.user_type != "System User":
        frappe.throw(_("The inventory assignee must be an enabled System User."))


def validate_item(code):
    item = frappe.db.get_value("Item", code,
        ["name", "item_name", "disabled", "is_stock_item", "has_variants", "end_of_life",
         "stock_uom", "has_batch_no", "has_serial_no"], as_dict=True)
    if not item or item.disabled or not item.is_stock_item or item.has_variants or (
            item.end_of_life and getdate(item.end_of_life) < getdate(nowdate())):
        frappe.throw(_("Reference {0} must be an active stock item without variants.").format(code))
    return item


def choose_references(candidates, rng=None):
    """Exactly ten distinct references, uniformly sampled without replacement."""
    rng = rng or random.SystemRandom()
    candidates = sorted(set(candidates))
    if len(candidates) < SAMPLE_SIZE:
        raise ValueError("Not enough eligible references outside open checks")
    return rng.sample(candidates, SAMPLE_SIZE)


def run_monthly_inventory():
    # Daily catch-up also covers an unavailable scheduler on the first day.
    if not cint(frappe.db.get_single_value(SETTINGS, "enabled")):
        return
    return generate_check()


def check_name(company, period):
    return "MIC-{0}-{1}".format(getdate(period).strftime("%Y-%m"),
        hashlib.sha256(company.encode("utf-8")).hexdigest()[:10])


@frappe.whitelist()
def generate_current_month():
    require_manager()
    return generate_check()


def generate_check():
    # The singleton lock is held until the enclosing Frappe transaction commits.
    frappe.db.sql("SELECT field FROM tabSingles WHERE doctype=%s FOR UPDATE", SETTINGS)
    settings = frappe.get_single(SETTINGS)
    validate_settings(settings)
    validate_assignee(settings.assigned_to)
    if not settings.company:
        frappe.throw(_("Choose a Company in Monthly Inventory Settings."))
    period = getdate(nowdate()).replace(day=1)
    key = check_name(settings.company, period)
    existing = frappe.db.sql("SELECT name FROM `tabMonthly Inventory Check` WHERE name=%s FOR UPDATE", key)
    if existing:
        return existing[0][0]
    candidates = get_eligible_references(settings)
    busy = frappe.db.sql("""SELECT DISTINCT r.item_code
        FROM `tabMonthly Inventory Check Row` r
        JOIN `tabMonthly Inventory Check` c ON c.name=r.parent
        WHERE c.company=%s AND c.status!='Passed'""", settings.company)
    candidates = set(candidates).difference(row[0] for row in busy)
    history = dict(frappe.db.sql("""SELECT r.item_code, MAX(c.period)
        FROM `tabMonthly Inventory Check Row` r
        JOIN `tabMonthly Inventory Check` c ON c.name=r.parent
        WHERE c.company=%s GROUP BY r.item_code""", settings.company))
    try:
        selected = choose_references(candidates)
    except ValueError:
        frappe.throw(_("Not enough available references. Finish open checks or review enabled groups and excluded references; at least {0} are required.").format(SAMPLE_SIZE))
    doc = frappe.get_doc({"doctype": CHECK, "name": key, "company": settings.company,
        "currency": frappe.db.get_value("Company", settings.company, "default_currency"),
        "period": period, "assigned_to": settings.assigned_to,
        "due_date": period.replace(day=cint(settings.due_day)),
        "status": "In Progress", "selected_items": json.dumps(selected),
        "reference_count": len(selected), "selection_log": json.dumps({
            "algorithm": "uniform random sample of 10 distinct references without replacement v3",
            "eligibility": "enabled item groups; disabled ancestors and explicit exclusions veto v2",
            "enabled_item_groups": effective_item_groups(settings, get_inventory_item_groups()),
            "excluded_references": sorted(row.item_code for row in settings.excluded_items),
            "available_references": len(candidates), "selected": selected,
            "previous_selection": {code: str(history.get(code) or "Never") for code in selected}}, indent=2)})
    with transition(key):
        populate_rows(doc)
        doc.insert(ignore_permissions=True)
    # Explicitly share write access; assignment alone shares read access in v12.
    frappe.share.add(CHECK, doc.name, settings.assigned_to, write=1,
                     flags={"ignore_share_permission": True})
    from frappe.desk.form.assign_to import add
    add({"doctype": CHECK, "name": doc.name, "assign_to": settings.assigned_to,
         "description": _("Monthly inventory sanity check: {0} references, due {1}.").format(
             len(selected), doc.due_date), "date": doc.due_date, "notify": 0})
    # Queued in the same transaction. No outgoing message during installation.
    frappe.sendmail(recipients=[settings.assigned_to],
        subject=_("Monthly inventory check {0}").format(period.strftime("%Y-%m")),
        message=_("Please verify {0} references in enabled warehouses under AMF Warehouse / Production by {1}.").format(len(selected), doc.due_date)
        + '<p><a href="{0}">{1}</a></p>'.format(escape(get_url_to_form(CHECK, doc.name), quote=True),
                                                _("Open inventory checklist")),
        reference_doctype=CHECK, reference_name=doc.name)
    return doc.name


def production_root(company):
    roots = frappe.db.sql("""SELECT w.name, w.lft, w.rgt, w.disabled, w.is_group,
        p.disabled AS parent_disabled FROM tabWarehouse w
        JOIN tabWarehouse p ON p.name=w.parent_warehouse AND p.company=w.company
        WHERE w.company=%s AND w.warehouse_name='Production'
        AND p.warehouse_name='AMF Warehouse'""", company, as_dict=True)
    if len(roots) != 1 or roots[0].disabled or roots[0].parent_disabled or not roots[0].is_group:
        frappe.throw(_("An enabled Production warehouse group directly under AMF Warehouse is required for company {0}.").format(company))
    return roots[0]


def warehouses(company):
    # Use the same Production subtree for snapshots, corrections and completion.
    root = production_root(company)
    return frappe.db.sql("""SELECT w.name FROM tabWarehouse w
        WHERE w.company=%s AND w.is_group=0 AND IFNULL(w.disabled, 0)=0
        AND w.warehouse_name!='OLD BATCH'
        AND w.lft>%s AND w.rgt<%s
        AND NOT EXISTS (SELECT 1 FROM tabWarehouse blocked
            WHERE blocked.company=w.company AND blocked.disabled=1
            AND blocked.lft<=w.lft AND blocked.rgt>=w.rgt)
        ORDER BY w.lft, w.name""", (company, root.lft, root.rgt), as_dict=True)


def stock_state(code, warehouse, exclude=None, current=False):
    """A bounded metadata query detects movement, cancellation and reposting.

    Include cancelled entries in the fingerprint; use ERPNext's balance function
    for quantities/rates. Net-zero movements must still invalidate a count.
    """
    args = {"item": code, "warehouse": warehouse, "now": now_datetime()}
    condition = ""
    if exclude:
        condition = " AND NOT (voucher_type=%(type)s AND voucher_no=%(voucher)s)"
        args.update({"type": exclude[0], "voucher": exclude[1]})
    info = frappe.db.sql("""SELECT COUNT(*) AS entries, MAX(modified) AS modified,
        MAX(creation) AS creation, SUM(actual_qty) AS qty_sum,
        SUM(stock_value_difference) AS value_sum,
        SUM(qty_after_transaction) AS balance_sum, SUM(valuation_rate) AS rate_sum,
        SUM(CASE WHEN IFNULL(is_cancelled, 'No')='Yes' THEN 1 ELSE 0 END) AS cancelled_entries,
        SUM(CASE WHEN TIMESTAMP(posting_date, posting_time)>%(now)s
            AND IFNULL(is_cancelled, 'No')='No' THEN 1 ELSE 0 END) AS future_entries
        FROM `tabStock Ledger Entry` WHERE item_code=%(item)s AND warehouse=%(warehouse)s"""
        + condition + (" FOR UPDATE" if current else ""), args, as_dict=True)[0]
    if info.future_entries:
        frappe.throw(_("Future-dated stock entries exist for {0} in {1}. Resolve them before counting.").format(code, warehouse))
    token = hashlib.sha256(json.dumps(dict(info), sort_keys=True, default=str).encode("utf-8")).hexdigest()
    if current:
        stamp = args["now"]
        latest = get_previous_sle({"item_code": code, "warehouse": warehouse,
            "posting_date": stamp.date(), "posting_time": stamp.time()}, for_update=True)
        qty, rate = latest.get("qty_after_transaction", 0), latest.get("valuation_rate", 0)
    else:
        qty, rate = get_stock_balance(code, warehouse, with_valuation_rate=True)
    return {"qty": flt(qty, PRECISION), "rate": flt(rate, PRECISION), "token": token}


def populate_rows(doc):
    root = production_root(doc.company)
    locations = warehouses(doc.company)
    if not locations:
        frappe.throw(_("Production has no enabled stock warehouses to count."))
    doc.warehouse_root = root.name
    audit = json.loads(doc.selection_log or "{}")
    audit.update({"warehouse_root": root.name, "warehouses": [location.name for location in locations]})
    doc.selection_log = json.dumps(audit, indent=2)
    doc.set("rows", [])
    stamp = now_datetime()
    for code in json.loads(doc.selected_items):
        item = validate_item(code)
        for location in locations:
            state = stock_state(code, location.name)
            doc.append("rows", {"item_code": code, "item_name": item.item_name,
                "stock_uom": item.stock_uom, "warehouse": location.name,
                "tracked_item": cint(item.has_serial_no or item.has_batch_no),
                "current_qty": state["qty"], "current_rate": state["rate"],
                "counted_qty": max(0, state["qty"]), "counted_rate": max(0, state["rate"]),
                "snapshot_on": stamp, "ledger_token": state["token"], "row_status": "Pending"})


def comparable(value):
    if isinstance(value, (int, float, Decimal)):
        return format(Decimal(str(value)).normalize(), "f")
    return "" if value is None else str(value)


def number(value, label):
    try:
        result = float(value)
    except (ValueError, TypeError):
        frappe.throw(_("Enter a number for {0}.").format(label))
    if not math.isfinite(result) or result < 0:
        frappe.throw(_("{0} must be a finite, non-negative number.").format(label))
    if result >= 1000000000000:
        frappe.throw(_("{0} exceeds ERPNext's supported numeric range.").format(label))
    return flt(result, PRECISION)


def differs(row):
    return flt(row.counted_qty, PRECISION) != flt(row.current_qty, PRECISION) or (
        flt(row.counted_qty, PRECISION) != 0 and
        flt(row.counted_rate, PRECISION) != flt(row.current_rate, PRECISION))


def validate_check(doc):
    internal = internal_change(doc)
    if doc.is_new():
        if not internal:
            frappe.throw(_("Generate checks from Monthly Inventory Settings."))
    else:
        old = load_locked_check(doc.name)
        if not internal:
            if old.status == "Passed":
                frappe.throw(_("A passed inventory check is locked."))
            if not is_manager() and frappe.session.user != old.assigned_to:
                frappe.throw(_("Only the assignee or a Stock Manager can record counts."), frappe.PermissionError)
            for field in PROTECTED_FIELDS:
                if comparable(doc.get(field)) != comparable(old.get(field)):
                    frappe.throw(_("Inventory field {0} is managed by the system.").format(field))
            before = {row.name: row for row in old.rows}
            if set(before) != {row.name for row in doc.rows} or len(before) != len(doc.rows):
                frappe.throw(_("Inventory rows cannot be added or removed. Use Refresh Stock."))
            for row in doc.rows:
                previous = before[row.name]
                for field in PROTECTED_ROW_FIELDS:
                    if comparable(row.get(field)) != comparable(previous.get(field)):
                        frappe.throw(_("Inventory snapshots and verification fields cannot be edited."))
                edited = any(comparable(row.get(f)) != comparable(previous.get(f)) for f in EDITABLE_ROW_FIELDS)
                if edited:
                    if old.reconciliation and frappe.db.get_value("Stock Reconciliation", old.reconciliation, "docstatus") == 0:
                        frappe.throw(_("Delete the draft reconciliation before changing counts."))
                    count_changed = any(comparable(row.get(f)) != comparable(previous.get(f))
                                        for f in ("counted", "counted_qty", "counted_rate"))
                    if count_changed or row.correction_document != previous.correction_document or row.correction_type != previous.correction_type:
                        row.resolved = 0
                    if count_changed and cint(row.counted):
                        if stock_state(row.item_code, row.warehouse)["token"] != row.ledger_token:
                            frappe.throw(_("Stock moved for {0} in {1}. Refresh Stock and recount.").format(row.item_code, row.warehouse))
                        row.checked_by, row.checked_on = frappe.session.user, now_datetime()
                    elif count_changed:
                        row.checked_by, row.checked_on = None, None
    for row in doc.rows:
        row.counted = cint(row.counted)
        if row.counted not in (0, 1):
            frappe.throw(_("Confirmation must be checked or unchecked."))
        row.counted_qty = number(row.counted_qty, _("Counted Quantity"))
        row.counted_rate = number(row.counted_rate, _("Verified Valuation Rate"))
        if cint(row.counted):
            if frappe.db.get_value("UOM", row.stock_uom, "must_be_whole_number") and row.counted_qty % 1:
                frappe.throw(_("{0} requires a whole-number count.").format(row.item_code))
            if row.counted_qty and not row.counted_rate and differs(row):
                frappe.throw(_("A positive valuation rate is required for nonzero stock."))
            if differs(row) and not (row.reason or "").strip():
                frappe.throw(_("Explain the difference for {0} in {1}.").format(row.item_code, row.warehouse))
        row.qty_difference = flt(row.counted_qty - row.current_qty, PRECISION)
        row.value_difference = flt(row.counted_qty * row.counted_rate - row.current_qty * row.current_rate, PRECISION)
        row.row_status = ("Pending" if not row.counted else "Corrected" if row.resolved else
                          "Difference" if differs(row) else "Matched")
    doc.total_rows = len(doc.rows)
    doc.checked_rows = sum(bool(row.counted) for row in doc.rows)
    if doc.status != "Passed":
        doc.status = "Awaiting Reconciliation" if any(row.counted and differs(row) and not row.resolved
                     for row in doc.rows) else "In Progress"


def ensure_scope(doc):
    for code in json.loads(doc.selected_items):
        item = validate_item(code)
        if any(row.item_code == code and (
                cint(row.tracked_item) != cint(item.has_serial_no or item.has_batch_no) or
                row.stock_uom != item.stock_uom) for row in doc.rows):
            frappe.throw(_("Item tracking or stock UOM changed. Refresh Stock and recount."))
    expected = {(code, wh.name) for code in json.loads(doc.selected_items) for wh in warehouses(doc.company)}
    if expected != {(row.item_code, row.warehouse) for row in doc.rows}:
        frappe.throw(_("The warehouse scope changed. Refresh Stock and recount."))


def require_all_counted(doc):
    ensure_scope(doc)
    if not doc.rows or any(not row.counted for row in doc.rows):
        frappe.throw(_("Confirm every warehouse row, including zero quantities, before continuing."))


def assert_unchanged(row, current=True):
    state = stock_state(row.item_code, row.warehouse, current=current)
    qty = row.counted_qty if row.resolved else row.current_qty
    rate = row.counted_rate if row.resolved else row.current_rate
    if state["token"] != row.ledger_token or state["qty"] != flt(qty, PRECISION) or (
            state["qty"] and state["rate"] != flt(rate, PRECISION)):
        frappe.throw(_("Stock moved for {0} in {1}. Refresh Stock and recount.").format(row.item_code, row.warehouse))


def lock_stock_rows(rows):
    # Deterministic locking order limits deadlocks with concurrent stock posts.
    # ERPNext also locks these records while posting/reposting the ledger.
    for code, warehouse in sorted({(row.item_code, row.warehouse) for row in rows}):
        frappe.db.sql("""SELECT name FROM `tabStock Ledger Entry`
            WHERE item_code=%s AND warehouse=%s FOR UPDATE""", (code, warehouse))
        frappe.db.sql("SELECT name FROM tabBin WHERE item_code=%s AND warehouse=%s FOR UPDATE", (code, warehouse))


@frappe.whitelist()
def refresh_stock(name):
    doc = lock_check(name)
    if doc.status == "Passed":
        frappe.throw(_("A passed check cannot be refreshed."))
    if doc.reconciliation and frappe.db.get_value("Stock Reconciliation", doc.reconciliation, "docstatus") == 0:
        frappe.throw(_("Delete the draft reconciliation before refreshing stock."))
    with transition(name):
        populate_rows(doc)
        doc.reconciliation = None
        doc.save()
    doc.add_comment("Info", _("Stock refreshed. All counts cleared; recount every warehouse row."))
    return doc.name


@frappe.whitelist()
def get_stale_rows(name):
    doc = frappe.get_doc(CHECK, name)
    doc.check_permission("read")
    if doc.status == "Passed":
        return []
    return [row.name for row in doc.rows if stock_state(row.item_code, row.warehouse)["token"] != row.ledger_token]


@frappe.whitelist()
def create_reconciliation(name):
    doc = lock_check(name)
    if doc.status == "Passed":
        frappe.throw(_("This check has already passed."))
    frappe.has_permission("Stock Reconciliation", "create", throw=True)
    require_all_counted(doc)
    if doc.reconciliation and frappe.db.get_value("Stock Reconciliation", doc.reconciliation, "docstatus") != 2:
        return doc.reconciliation
    changes = [row for row in doc.rows if differs(row) and not row.resolved and not row.tracked_item]
    if not changes:
        frappe.throw(_("No automatic corrections to create. Tracked items need a batch/serial-aware Stock Entry or Stock Reconciliation."))
    for row in doc.rows:
        assert_unchanged(row, current=False)
    stamp = now_datetime()
    reco = frappe.get_doc({"doctype": "Stock Reconciliation", "company": doc.company,
        "purpose": "Stock Reconciliation", "set_posting_time": 1,
        "posting_date": stamp.date(), "posting_time": str(stamp.time()),
        "monthly_inventory_check": doc.name,
        "items": [{"item_code": row.item_code, "warehouse": row.warehouse,
                   "qty": row.counted_qty, "valuation_rate": row.counted_rate} for row in changes]})
    reco.set_new_name()
    # Reserve the backlink before insert so the voucher hook can authenticate it.
    doc.db_set("reconciliation", reco.name)
    reco.insert()  # normal ERPNext accounting validations and permissions
    doc.reload()
    with transition(name):
        for row in doc.rows:
            if (row.item_code, row.warehouse) in {(r.item_code, r.warehouse) for r in changes}:
                row.correction_type, row.correction_document = "Stock Reconciliation", reco.name
        doc.save()
    return reco.name


def guard_reconciliation(reco, method=None):
    # Prevent detaching the link through the normal document API.
    original = frappe.db.get_value("Stock Reconciliation", reco.name, "monthly_inventory_check") if not reco.is_new() else None
    if original and original != reco.get("monthly_inventory_check"):
        frappe.throw(_("The monthly inventory link cannot be removed or changed."))
    if not reco.get("monthly_inventory_check"):
        return
    doc = lock_check(reco.monthly_inventory_check, write=False)
    if doc.reconciliation != reco.name or doc.status == "Passed":
        frappe.throw(_("Generate this reconciliation from its inventory check."))
    require_all_counted(doc)
    expected = {(r.item_code, r.warehouse): r for r in doc.rows if differs(r) and not r.resolved and not r.tracked_item}
    if reco.company != doc.company or reco.purpose != "Stock Reconciliation" or len(reco.items) != len(expected):
        frappe.throw(_("The reconciliation must match the inventory check exactly."))
    seen = set()
    for row in reco.items:
        key = (row.item_code, row.warehouse)
        source = expected.get(key)
        if not source or key in seen or row.serial_no or row.batch_no or (
                flt(row.qty, PRECISION) != flt(source.counted_qty, PRECISION) or
                flt(row.valuation_rate, PRECISION) != flt(source.counted_rate, PRECISION)):
            frappe.throw(_("Reconciliation quantities and rates must match the verified counts."))
        seen.add(key)
    posting = getattr(reco, "_action", None) == "submit"
    if posting:
        lock_stock_rows(expected.values())
    for source in expected.values():
        assert_unchanged(source, current=posting)
    # Fresh posting time on save/submit: do not overwrite transactions at an old time.
    stamp = now_datetime()
    reco.set_posting_time = 1
    # Frappe v12's JSON encoder supports dates/timedeltas, but not datetime.time.
    # before_submit runs after field coercion, so retain a serializable value
    # for the savedocs response instead of leaving a time object on the document.
    reco.posting_date, reco.posting_time = stamp.date(), str(stamp.time())


def verify_correction(row, company):
    kind, voucher = row.correction_type, row.correction_document
    if kind not in ("Stock Entry", "Stock Reconciliation") or not voucher:
        frappe.throw(_("Link a submitted stock correction for {0} in {1}.").format(row.item_code, row.warehouse))
    source = frappe.db.get_value(kind, voucher, ["docstatus", "company", "posting_date", "posting_time"], as_dict=True)
    if not source or source.docstatus != 1 or source.company != company:
        frappe.throw(_("The correction must be submitted and belong to the same company."))
    entries = frappe.db.sql("""SELECT name FROM `tabStock Ledger Entry`
        WHERE item_code=%s AND warehouse=%s AND voucher_type=%s AND voucher_no=%s
        AND IFNULL(is_cancelled, 'No')='No' AND creation >= %s""",
        (row.item_code, row.warehouse, kind, voucher, row.checked_on))
    if not entries or stock_state(row.item_code, row.warehouse, exclude=(kind, voucher), current=True)["token"] != row.ledger_token:
        frappe.throw(_("Other stock movements occurred, or this correction predates the count. Refresh Stock and recount."))
    state = stock_state(row.item_code, row.warehouse, current=True)
    if state["qty"] != flt(row.counted_qty, PRECISION) or (
            state["qty"] and state["rate"] != flt(row.counted_rate, PRECISION)):
        frappe.throw(_("The submitted correction does not match the counted quantity and rate for {0} in {1}.").format(row.item_code, row.warehouse))
    row.resolved, row.ledger_token = 1, state["token"]


@frappe.whitelist()
def complete_check(name):
    doc = lock_check(name)
    return verify_and_complete(doc)


def verify_and_complete(doc):
    if doc.status == "Passed":
        return doc.name
    require_all_counted(doc)
    lock_stock_rows(doc.rows)
    with transition(doc.name):
        for row in doc.rows:
            if differs(row) and not row.resolved:
                verify_correction(row, doc.company)
            else:
                assert_unchanged(row)
        doc.status, doc.completed_on, doc.completed_by = "Passed", now_datetime(), frappe.session.user
        doc.save(ignore_permissions=True)
    from frappe.desk.form.assign_to import close_all_assignments
    close_all_assignments(CHECK, doc.name)
    doc.add_comment("Info", _("Sanity check passed: all warehouse counts and submitted stock corrections verified."))
    return doc.name


def on_correction_cancel(doc, method=None):
    # A cancelled correction invalidates the audit result, including manual ones.
    names = frappe.db.sql("""SELECT DISTINCT parent FROM `tabMonthly Inventory Check Row`
        WHERE correction_type=%s AND correction_document=%s""", (doc.doctype, doc.name))
    for (name,) in names:
        check = lock_check(name, write=False)
        with transition(name):
            for row in check.rows:
                if row.correction_type == doc.doctype and row.correction_document == doc.name:
                    row.counted, row.resolved = 0, 0
                    row.checked_by, row.checked_on = None, None
            check.status, check.completed_on, check.completed_by = "In Progress", None, None
            check.save(ignore_permissions=True)
        check.add_comment("Info", _("Correction {0} cancelled. Refresh stock and recount before completing again.").format(doc.name))
        todos = frappe.get_all("ToDo", filters={"reference_type": CHECK,
            "reference_name": name, "owner": check.assigned_to}, fields=["name"])
        if todos:
            todo = frappe.get_doc("ToDo", todos[0].name)
            todo.status = "Open"
            todo.save(ignore_permissions=True)


def on_reconciliation_trash(doc, method=None):
    if doc.get("monthly_inventory_check"):
        check = lock_check(doc.monthly_inventory_check, write=False)
        if check.reconciliation == doc.name:
            with transition(check.name):
                check.reconciliation = None
                for row in check.rows:
                    if row.correction_type == doc.doctype and row.correction_document == doc.name:
                        row.correction_type, row.correction_document = None, None
                check.save(ignore_permissions=True)


def setup_monthly_inventory():
    """Idempotent installation; preserve choices and never enable mail implicitly."""
    # v12 retains a separate column cache when this Single was loaded before sync.
    frappe.clear_cache(doctype=SETTINGS)
    frappe.local.valid_columns.pop(SETTINGS, None)
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Stock Reconciliation": [{
        "fieldname": "monthly_inventory_check", "label": "Monthly Inventory Check",
        "fieldtype": "Link", "options": CHECK, "insert_after": "company",
        "read_only": 1, "no_copy": 1}]})
    existing = {row[0] for row in frappe.db.sql("SELECT field FROM tabSingles WHERE doctype=%s", SETTINGS)}
    defaults = {"enabled": 0, "assigned_to": DEFAULT_ASSIGNEE, "sample_size": SAMPLE_SIZE,
                "minimum_items": SAMPLE_SIZE, "maximum_items": SAMPLE_SIZE, "due_day": 15,
                "company": frappe.defaults.get_global_default("company")}
    for field, value in defaults.items():
        if field not in existing and value is not None:
            frappe.db.set_value(SETTINGS, SETTINGS, field, value, update_modified=False)
    settings = frappe.get_single(SETTINGS)
    before = [(row.item_group, row.enabled) for row in settings.item_groups]
    previous_scope = tuple(settings.get(field) for field in (
        "sample_size", "minimum_items", "maximum_items", "warehouse_root"))
    settings.sample_size = settings.minimum_items = settings.maximum_items = SAMPLE_SIZE
    settings.warehouse_root = production_root(settings.company).name if settings.company else None
    synchronize_group_rows(settings, get_inventory_item_groups())
    if before != [(row.item_group, row.enabled) for row in settings.item_groups] or previous_scope != (
            settings.sample_size, settings.minimum_items, settings.maximum_items, settings.warehouse_root):
        settings.save(ignore_permissions=True)


def install_monthly_inventory():
    """Targeted deployment for existing v12 sites without unrelated migrations."""
    require_manager()
    for name in ("monthly_inventory_reference", "monthly_inventory_item_group",
                 "monthly_inventory_exclusion", "monthly_inventory_check_row",
                 "monthly_inventory_settings", "monthly_inventory_check"):
        frappe.reload_doc("amf", "doctype", name, force=True)
    setup_monthly_inventory()
    frappe.clear_cache()
    frappe.cache().delete_value("scheduler_events")
