from amf.amf.utils.stock_entry import (
    _get_or_create_log,
    _rebuild_stock_entry_ledgers,
    _set_batch_disabled_state,
    update_log_entry,
)

import frappe
from frappe.utils import cint, cstr, flt, now_datetime, nowdate, nowtime

DEFAULT_BATCH_VALUATION_WAREHOUSE = "Scrap - AMF21"
DEFAULT_BATCH_VALUATION_ITEM_GROUP = "Valve Seat"
DEFAULT_BATCH_VALUATION_RATE = 20.0
DEFAULT_BATCH_VALUATION_CODE_LENGTH = 6
DEFAULT_RECONCILIATION_ROWS = 100
VALUATION_RATE_TOLERANCE = 0.000001
DEFAULT_SCRAP_DEVALUATION_STOCK_ENTRY_FROM_DATE = "2025-01-01"
DEFAULT_SCRAP_DEVALUATION_TARGETS = (
    {"code_prefix": "10", "target_rate": 0.01},
    {"code_prefix": "11", "target_rate": 0.01},
    {"code_prefix": "20", "target_rate": 1.0},
    {"code_prefix": "21", "target_rate": 1.0},
)
DEFAULT_BATCH_VALUATION_TARGETS = (
    {"code_prefix": "10", "code_length": 6, "target_rate": 0.01},
    {"code_prefix": "11", "code_length": 6, "target_rate": 0.01},
    {"code_prefix": "20", "code_length": 6, "target_rate": 1.0},
    {"code_prefix": "21", "code_length": 6, "target_rate": 1.0},
)
SALES_EMAIL_RECIPIENTS = [
    "sales@amf.ch",
    "alexandre.ringwald@amf.ch",
]
NEW_SALES_ITEMS_LOOKBACK_DAYS = 7


@frappe.whitelist()
def update_all_item_valuation_rates_enq():
    """Queue the Item master valuation refresh in the long worker."""
    _enqueue_long_job("amf.amf.utils.item_mgt.update_all_item_valuation_rates")
    return None


@frappe.whitelist()
def update_all_item_valuation_rates():
    """
    Update Item.valuation_rate from the default BOM cost first and the latest
    purchase invoice rate as a fallback.
    """
    log_context = frappe._dict(
        {
            "doctype": "Item",
            "name": "Valuation Rate Process Run on {0}".format(now_datetime()),
        }
    )
    log_id = _get_or_create_log(log_context)

    items = frappe.get_all(
        "Item",
        fields=["name", "item_name", "valuation_rate"],
        filters={"disabled": 0},
    )
    updated_items = []
    skipped_items = []

    for item_data in items:
        new_rate, source = _resolve_item_valuation_rate(item_data.name)
        update_log_entry(
            log_id,
            (
                "[{0}] Item {1}: source={2}, candidate_rate={3}<br>".format(
                    now_datetime(), item_data.name, source or "none", new_rate
                )
            ),
        )

        if new_rate <= 0 or flt(item_data.valuation_rate) == flt(new_rate):
            skipped_items.append(
                {
                    "item": item_data.name,
                    "reason": (
                        "No source rate found or valuation rate is already up to date."
                    ),
                }
            )
            continue

        try:
            item_doc = frappe.get_doc("Item", item_data.name)
            item_doc.valuation_rate = new_rate
            item_doc.save(ignore_permissions=True)
            updated_items.append(
                {"item": item_doc.name, "rate": new_rate, "source": source}
            )
            update_log_entry(
                log_id,
                "[{0}] Item {1}: valuation_rate updated to {2}<br>".format(
                    now_datetime(), item_doc.name, new_rate
                ),
            )
        except Exception as exc:
            frappe.log_error(
                "Error saving item {0}: {1}".format(item_data.name, exc),
                "Valuation Rate Update Error",
            )

    frappe.db.commit()

    update_log_entry(
        log_id,
        (
            "[{0}] Valuation Rate Update Complete.<br>"
            "Updated {1} items.<br>"
            "Skipped {2} items.<br>"
        ).format(now_datetime(), len(updated_items), len(skipped_items)),
    )


@frappe.whitelist()
def enqueue_batch_valuation_rate_reconciliation(
    target_rate=DEFAULT_BATCH_VALUATION_RATE,
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    item_group=DEFAULT_BATCH_VALUATION_ITEM_GROUP,
    dry_run=0,
    max_rows_per_reconciliation=DEFAULT_RECONCILIATION_ROWS,
):
    """Queue the legacy item-group-based stock valuation reconciliation."""
    _enqueue_long_job(
        "amf.amf.utils.item_mgt.reconcile_batch_valuation_rate",
        target_rate=target_rate,
        warehouse=warehouse,
        item_group=item_group,
        dry_run=cint(dry_run),
        max_rows_per_reconciliation=max_rows_per_reconciliation,
    )
    return None


@frappe.whitelist()
def enqueue_batch_valuation_rate_by_code_prefix(
    target_rate,
    code_prefix,
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    code_length=DEFAULT_BATCH_VALUATION_CODE_LENGTH,
    dry_run=0,
    max_rows_per_reconciliation=DEFAULT_RECONCILIATION_ROWS,
):
    """Queue the code-prefix-based stock valuation reconciliation."""
    _enqueue_long_job(
        "amf.amf.utils.item_mgt.reconcile_batch_valuation_rate_by_code_prefix",
        target_rate=target_rate,
        code_prefix=code_prefix,
        warehouse=warehouse,
        code_length=code_length,
        dry_run=cint(dry_run),
        max_rows_per_reconciliation=max_rows_per_reconciliation,
    )
    return None


@frappe.whitelist()
def enqueue_configured_scrap_batch_valuation_reconciliation(
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    dry_run=0,
    max_rows_per_reconciliation=DEFAULT_RECONCILIATION_ROWS,
):
    """Queue the configured scrap reconciliation rules as a single background job."""
    _enqueue_long_job(
        "amf.amf.utils.item_mgt.reconcile_configured_scrap_batch_valuation_reconciliation",
        warehouse=warehouse,
        dry_run=cint(dry_run),
        max_rows_per_reconciliation=max_rows_per_reconciliation,
    )
    return None


@frappe.whitelist()
def enqueue_repair_scrap_valuation_from_default_bom(
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    company=None,
    as_of_date=None,
    as_of_time="23:59:59",
    stock_entry_from_date=DEFAULT_SCRAP_DEVALUATION_STOCK_ENTRY_FROM_DATE,
    item_code=None,
    dry_run=1,
    allow_negative_stock=1,
    update_item_master=0,
):
    """Queue the direct Stock Entry based scrap devaluation repair."""
    _enqueue_long_job(
        "amf.amf.utils.item_mgt.repair_scrap_valuation_from_default_bom",
        warehouse=warehouse,
        company=company,
        as_of_date=as_of_date,
        as_of_time=as_of_time,
        stock_entry_from_date=stock_entry_from_date,
        item_code=item_code,
        dry_run=cint(dry_run),
        allow_negative_stock=cint(allow_negative_stock),
        update_item_master=cint(update_item_master),
    )
    return None


@frappe.whitelist()
def repair_scrap_valuation_from_default_bom(
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    company=None,
    as_of_date=None,
    as_of_time="23:59:59",
    stock_entry_from_date=DEFAULT_SCRAP_DEVALUATION_STOCK_ENTRY_FROM_DATE,
    item_code=None,
    dry_run=1,
    allow_negative_stock=1,
    update_item_master=0,
):
    """
    Devalue scrap stock by editing the submitted Stock Entry rows directly.

    No Stock Reconciliation is created. For every matching item with positive
    balance in the scrap warehouse, incoming Stock Entry rows into the scrap
    warehouse are repriced from the configured item-code prefix rules. The
    affected Stock Entries are then reposted so SLE, Bin and GL are rebuilt
    from the corrected source document.
    """
    frappe.only_for(("System Manager", "Stock Manager", "Accounts Manager"))

    dry_run = cint(dry_run)
    allow_negative_stock = cint(allow_negative_stock)
    update_item_master = 0
    as_of_date = as_of_date or nowdate()
    as_of_time = as_of_time or "23:59:59"
    stock_entry_from_date = stock_entry_from_date or DEFAULT_SCRAP_DEVALUATION_STOCK_ENTRY_FROM_DATE
    company = company or frappe.db.get_value("Warehouse", warehouse, "company")

    if not warehouse:
        frappe.throw("Warehouse is required.")
    if not frappe.db.exists("Warehouse", warehouse):
        frappe.throw("Warehouse {0} does not exist.".format(warehouse))
    if not company:
        frappe.throw("Company could not be resolved for warehouse {0}.".format(warehouse))

    log_id = _create_direct_scrap_valuation_log(
        warehouse=warehouse,
        company=company,
        as_of_date=as_of_date,
        as_of_time=as_of_time,
        stock_entry_from_date=stock_entry_from_date,
        item_code=item_code,
        dry_run=dry_run,
    )

    targets = _get_scrap_devaluation_targets(
        warehouse=warehouse,
        company=company,
        as_of_date=as_of_date,
        as_of_time=as_of_time,
        item_code=item_code,
    )
    plan = _build_scrap_devaluation_plan(
        targets=targets,
        warehouse=warehouse,
        company=company,
        as_of_date=as_of_date,
        as_of_time=as_of_time,
        stock_entry_from_date=stock_entry_from_date,
    )

    summary = {
        "log_id": log_id,
        "warehouse": warehouse,
        "company": company,
        "as_of_date": as_of_date,
        "as_of_time": as_of_time,
        "stock_entry_from_date": stock_entry_from_date,
        "item_code": item_code,
        "dry_run": bool(dry_run),
        "allow_negative_stock": bool(allow_negative_stock),
        "update_item_master": bool(update_item_master),
        "valuation_rules": DEFAULT_SCRAP_DEVALUATION_TARGETS,
        "target_balance_count": len(targets),
        "target_item_count": len({row.item_code for row in targets}),
        "rows_examined": plan["rows_examined"],
        "rows_to_update": len(plan["rows_to_update"]),
        "stock_entries_to_rebuild": len(plan["stock_entries"]),
        "item_master_updates": len(plan["item_master_updates"]),
        "disabled_batches_to_temporarily_enable": len(plan["disabled_batches"]),
        "missing_batch_rows_temporarily_allowed": len(
            plan["missing_batch_rows_for_rebuild"]
        ),
        "serial_numbers_temporarily_seeded": len(plan["serial_numbers_for_rebuild"]),
        "blocked_rows": plan["blocked_rows"],
        "sample_rows": plan["rows_to_update"][:20],
        "rebuilt_stock_entries": [],
        "updated_items": [],
    }

    update_log_entry(
        log_id,
        (
            "[{0}] Prepared direct scrap devaluation repair: "
            "{1} balance row(s), {2} Stock Entry Detail row(s), "
            "{3} Stock Entry document(s), dry_run={4}.<br>"
        ).format(
            now_datetime(),
            summary["target_balance_count"],
            summary["rows_to_update"],
            summary["stock_entries_to_rebuild"],
            dry_run,
        ),
    )

    if dry_run or (
        not plan["rows_to_update"]
        and not (update_item_master and plan["item_master_updates"])
    ):
        return summary

    _apply_scrap_devaluation_plan(
        plan=plan,
        summary=summary,
        log_id=log_id,
        allow_negative_stock=allow_negative_stock,
        update_item_master=update_item_master,
    )
    return summary


@frappe.whitelist()
def reconcile_batch_valuation_rate(
    target_rate=DEFAULT_BATCH_VALUATION_RATE,
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    item_group=DEFAULT_BATCH_VALUATION_ITEM_GROUP,
    dry_run=0,
    max_rows_per_reconciliation=DEFAULT_RECONCILIATION_ROWS,
):
    """
    Reconcile scrap stock valuation for one Item Group.

    This is the legacy selector kept for backward compatibility. It still
    delegates to the shared reconciliation runner, which applies the current
    posting context from `_get_posting_context()`.
    """
    target_rate = _validate_target_rate(target_rate)
    batch_rows, skipped_at_target = _get_batch_rows_by_item_group(
        warehouse=warehouse,
        item_group=item_group,
        target_rate=target_rate,
    )
    return _run_batch_valuation_reconciliation(
        batch_rows=batch_rows,
        skipped_at_target=skipped_at_target,
        warehouse=warehouse,
        target_rate=target_rate,
        scope_label="item-group {0}".format(item_group),
        scope_summary={"item_group": item_group},
        dry_run=dry_run,
        max_rows_per_reconciliation=max_rows_per_reconciliation,
    )


@frappe.whitelist()
def reconcile_batch_valuation_rate_by_code_prefix(
    target_rate,
    code_prefix,
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    code_length=DEFAULT_BATCH_VALUATION_CODE_LENGTH,
    dry_run=0,
    max_rows_per_reconciliation=DEFAULT_RECONCILIATION_ROWS,
):
    """
    Reconcile scrap stock valuation for one item-code prefix rule.

    Only item codes with the requested prefix and exact code length are
    selected. Matching stock rows are evaluated against the historical posting
    context returned by `_get_posting_context()`.
    """
    target_rate = _validate_target_rate(target_rate)
    code_length = cint(code_length)
    if not code_prefix:
        frappe.throw("Code prefix is required.")
    if code_length <= 0:
        frappe.throw("Code length must be greater than zero.")

    batch_rows, skipped_at_target = _get_batch_rows_by_code_prefix(
        warehouse=warehouse,
        code_prefix=code_prefix,
        code_length=code_length,
        target_rate=target_rate,
    )
    return _run_batch_valuation_reconciliation(
        batch_rows=batch_rows,
        skipped_at_target=skipped_at_target,
        warehouse=warehouse,
        target_rate=target_rate,
        scope_label=_format_code_rule_label(code_prefix, code_length),
        scope_summary={
            "code_prefix": code_prefix,
            "code_length": code_length,
        },
        dry_run=dry_run,
        max_rows_per_reconciliation=max_rows_per_reconciliation,
    )


@frappe.whitelist()
def reconcile_configured_scrap_batch_valuation_reconciliation(
    warehouse=DEFAULT_BATCH_VALUATION_WAREHOUSE,
    dry_run=0,
    max_rows_per_reconciliation=DEFAULT_RECONCILIATION_ROWS,
):
    """
    Run the configured code-prefix reconciliation rules one after another.

    The return payload aggregates the individual summaries so production runs
    can be audited from a single response.
    """
    dry_run = cint(dry_run)
    max_rows_per_reconciliation = cint(max_rows_per_reconciliation)
    summary = {
        "warehouse": warehouse,
        "dry_run": bool(dry_run),
        "group_summaries": [],
        "reconciliations": [],
    }

    for rule in DEFAULT_BATCH_VALUATION_TARGETS:
        group_summary = reconcile_batch_valuation_rate_by_code_prefix(
            target_rate=rule["target_rate"],
            code_prefix=rule["code_prefix"],
            warehouse=warehouse,
            code_length=rule["code_length"],
            dry_run=dry_run,
            max_rows_per_reconciliation=max_rows_per_reconciliation,
        )
        summary["group_summaries"].append(group_summary)
        summary["reconciliations"].extend(group_summary.get("reconciliations", []))

    return summary


@frappe.whitelist()
def send_sales_email():
    """
    Send an email about new sales items and sales items missing item prices.
    """
    missing_price_items = _get_sales_items_missing_prices()
    new_sales_items = _get_recent_sales_items(NEW_SALES_ITEMS_LOOKBACK_DAYS)

    message_parts = []
    if new_sales_items:
        message_parts.append(
            """
            <p>The following new sales items have been created in the last {days} days:</p>
            {items}
            <p>Please review and set item prices as necessary.</p>
            """.format(
                days=NEW_SALES_ITEMS_LOOKBACK_DAYS,
                items=_build_item_list_html(new_sales_items),
            )
        )

    if missing_price_items:
        message_parts.append(
            """
            <p>The following sales items are missing item prices:</p>
            {items}
            <p>Please update the item prices accordingly.</p>
            """.format(items=_build_item_list_html(missing_price_items))
        )

    if not message_parts:
        return

    frappe.sendmail(
        recipients=SALES_EMAIL_RECIPIENTS,
        subject="Sales Items Price Update Notification",
        message="".join(message_parts),
    )


def _enqueue_long_job(method, **kwargs):
    """Send a method to the long queue with the standard timeout used here."""
    frappe.enqueue(method, queue="long", timeout=15000, **kwargs)


def _validate_target_rate(target_rate):
    """Normalize a target valuation rate and reject negative values."""
    target_rate = flt(target_rate)
    if target_rate < 0:
        frappe.throw("Target valuation rate cannot be negative.")
    return target_rate


def _resolve_item_valuation_rate(item_code):
    """
    Resolve an Item master valuation rate from the supported source priority.

    Order:
    1. Default BOM total cost
    2. Latest submitted Purchase Invoice Item rate
    """
    bom_cost = _get_default_bom_cost(item_code)
    if bom_cost:
        return bom_cost, "default_bom"

    last_purchase_rate = _get_last_purchase_rate(item_code)
    if last_purchase_rate:
        return last_purchase_rate, "last_purchase_invoice"

    return 0.0, None


def _get_default_bom_cost(item_code):
    """Return the total cost of the default BOM for one item, if it exists."""
    default_bom = frappe.db.get_value(
        "BOM", {"item": item_code, "is_default": 1}, "name"
    )
    if not default_bom:
        return 0.0

    try:
        return flt(
            frappe.db.get_value("BOM", {"name": default_bom}, "total_cost") or 0.0
        )
    except Exception as exc:
        frappe.log_error(
            "Error calculating BOM cost for {0}: {1}".format(item_code, exc),
            "Valuation Rate Update Error",
        )
        return 0.0


def _get_last_purchase_rate(item_code):
    """Return the latest submitted purchase rate for one item."""
    last_purchase_rate = frappe.db.get_all(
        "Purchase Invoice Item",
        filters={"item_code": item_code, "docstatus": 1},
        fields=["rate"],
        order_by="creation desc",
        limit=1,
    )
    if not last_purchase_rate:
        return 0.0

    return flt(last_purchase_rate[0].rate)


def _create_direct_scrap_valuation_log(
    warehouse,
    company,
    as_of_date,
    as_of_time,
    stock_entry_from_date,
    item_code,
    dry_run,
):
    log_context = frappe._dict(
        {
            "doctype": "Stock Entry",
            "name": "Direct scrap devaluation repair {0} / {1}".format(
                warehouse, now_datetime()
            ),
        }
    )
    log_id = _get_or_create_log(log_context)
    update_log_entry(
        log_id,
        (
            "[{0}] Started direct scrap devaluation repair for warehouse={1}, "
            "company={2}, as_of={3} {4}, stock_entry_from_date={5}, "
            "item_code={6}, dry_run={7}.<br>"
        ).format(
            now_datetime(),
            warehouse,
            company,
            as_of_date,
            as_of_time,
            stock_entry_from_date,
            item_code or "",
            dry_run,
        ),
    )
    return log_id


def _get_scrap_devaluation_targets(
    warehouse, company, as_of_date, as_of_time, item_code=None
):
    item_condition = ""
    params = {
        "warehouse": warehouse,
        "company": company,
        "as_of_date": as_of_date,
        "as_of_time": as_of_time,
    }
    if item_code:
        item_condition = "AND sle.item_code = %(item_code)s"
        params["item_code"] = item_code

    prefix_conditions = []
    for idx, rule in enumerate(DEFAULT_SCRAP_DEVALUATION_TARGETS):
        key = "devaluation_prefix_{0}".format(idx)
        prefix_conditions.append("sle.item_code LIKE %({0})s".format(key))
        params[key] = "{0}%".format(rule["code_prefix"])

    rows = frappe.db.sql(
        """
        SELECT
            sle.item_code,
            item.item_name,
            IFNULL(sle.batch_no, '') AS batch_no,
            IFNULL(batch.disabled, 0) AS batch_disabled,
            SUM(sle.actual_qty) AS balance_qty
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` item
            ON item.name = sle.item_code
        LEFT JOIN `tabBatch` batch
            ON batch.name = sle.batch_no
        WHERE sle.warehouse = %(warehouse)s
          AND sle.company = %(company)s
          AND IFNULL(sle.is_cancelled, 'No') = 'No'
          AND item.disabled = 0
          AND ({prefix_condition})
          AND TIMESTAMP(sle.posting_date, sle.posting_time) <= TIMESTAMP(%(as_of_date)s, %(as_of_time)s)
          {item_condition}
        GROUP BY
            sle.item_code,
            item.item_name,
            IFNULL(sle.batch_no, ''),
            IFNULL(batch.disabled, 0)
        HAVING balance_qty > 0
        ORDER BY sle.item_code, IFNULL(sle.batch_no, '')
        """.format(
            prefix_condition=" OR ".join(prefix_conditions),
            item_condition=item_condition,
        ),
        params,
        as_dict=True,
    )

    targets = []
    for row in rows:
        rule = _get_scrap_devaluation_rule_for_item(row.item_code)
        if not rule:
            continue

        row.target_rate = flt(rule["target_rate"])
        row.valuation_rule = "{0}* -> {1}".format(
            rule["code_prefix"],
            row.target_rate,
        )
        targets.append(row)

    return targets


def _get_scrap_devaluation_rule_for_item(item_code):
    item_code = cstr(item_code)
    for rule in DEFAULT_SCRAP_DEVALUATION_TARGETS:
        if item_code.startswith(rule["code_prefix"]):
            return rule

    return None


def _build_scrap_devaluation_plan(
    targets, warehouse, company, as_of_date, as_of_time, stock_entry_from_date
):
    target_by_key = {
        (row.item_code, row.batch_no or ""): row
        for row in targets
    }
    target_item_codes = sorted({row.item_code for row in targets})
    rows = _get_scrap_devaluation_stock_entry_rows(
        target_item_codes=target_item_codes,
        warehouse=warehouse,
        company=company,
        as_of_date=as_of_date,
        as_of_time=as_of_time,
        stock_entry_from_date=stock_entry_from_date,
    )

    plan = {
        "rows_examined": len(rows),
        "rows_to_update": [],
        "stock_entries": [],
        "item_master_updates": [],
        "disabled_batches": [],
        "missing_batch_rows_for_rebuild": [],
        "serial_numbers_for_rebuild": [],
        "blocked_rows": [],
        "rows_by_stock_entry": {},
        "target_by_item": {},
    }
    stock_entry_names = set()
    disabled_batches = set()

    for target in targets:
        plan["target_by_item"][target.item_code] = {
            "item_code": target.item_code,
            "item_name": target.item_name,
            "valuation_rule": target.valuation_rule,
            "target_rate": flt(target.target_rate),
        }
        if target.batch_no and cint(target.batch_disabled):
            disabled_batches.add(target.batch_no)

    for row in rows:
        key = (row.item_code, row.batch_no or "")
        target = target_by_key.get(key)
        if not target:
            continue

        target_rate = flt(target.target_rate)
        if not flt(row.transfer_qty):
            plan["blocked_rows"].append(
                {
                    "row": row.name,
                    "stock_entry": row.parent,
                    "item_code": row.item_code,
                    "reason": "transfer_qty is zero",
                }
            )
            continue

        expected_amount = flt(row.transfer_qty) * target_rate
        current_amount = flt(row.amount)
        current_rate = flt(row.valuation_rate)
        if (
            abs(current_rate - target_rate) <= VALUATION_RATE_TOLERANCE
            and abs(current_amount - expected_amount) <= VALUATION_RATE_TOLERANCE
        ):
            continue

        row_plan = {
            "row": row.name,
            "stock_entry": row.parent,
            "posting_date": row.posting_date,
            "posting_time": row.posting_time,
            "purpose": row.purpose,
            "item_code": row.item_code,
            "item_name": target.item_name,
            "batch_no": row.batch_no or "",
            "batch_disabled": cint(row.batch_disabled),
            "valuation_rule": target.valuation_rule,
            "balance_qty": flt(target.balance_qty),
            "transfer_qty": flt(row.transfer_qty),
            "old_basic_rate": flt(row.basic_rate),
            "old_valuation_rate": current_rate,
            "old_amount": current_amount,
            "target_rate": target_rate,
            "target_amount": expected_amount,
            "s_warehouse": row.s_warehouse,
            "t_warehouse": row.t_warehouse,
        }
        plan["rows_to_update"].append(row_plan)
        plan["rows_by_stock_entry"].setdefault(row.parent, []).append(row_plan)
        stock_entry_names.add(row.parent)

        if row.batch_no and cint(row.batch_disabled):
            disabled_batches.add(row.batch_no)

    plan["stock_entries"] = _sort_stock_entries_for_rebuild(stock_entry_names)
    plan["disabled_batches"] = sorted(disabled_batches)
    plan["missing_batch_rows_for_rebuild"] = _get_missing_batch_rows_for_rebuild(
        plan["stock_entries"]
    )
    plan["serial_numbers_for_rebuild"] = _get_serial_numbers_for_rebuild(
        plan["stock_entries"]
    )
    plan["item_master_updates"] = []
    return plan


def _get_scrap_devaluation_stock_entry_rows(
    target_item_codes,
    warehouse,
    company,
    as_of_date,
    as_of_time,
    stock_entry_from_date,
):
    if not target_item_codes:
        return []

    item_codes_sql = ", ".join(
        [frappe.db.escape(item_code) for item_code in target_item_codes]
    )
    from_date_condition = ""
    params = {
        "company": company,
        "warehouse": warehouse,
        "as_of_date": as_of_date,
        "as_of_time": as_of_time,
    }
    if stock_entry_from_date:
        from_date_condition = "AND se.posting_date >= %(stock_entry_from_date)s"
        params["stock_entry_from_date"] = stock_entry_from_date

    return frappe.db.sql(
        """
        SELECT
            sed.name,
            sed.parent,
            sed.item_code,
            IFNULL(sed.batch_no, '') AS batch_no,
            IFNULL(batch.disabled, 0) AS batch_disabled,
            sed.s_warehouse,
            sed.t_warehouse,
            sed.transfer_qty,
            sed.basic_rate,
            sed.basic_amount,
            sed.additional_cost,
            sed.amount,
            sed.valuation_rate,
            se.purpose,
            se.posting_date,
            se.posting_time
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se
            ON se.name = sed.parent
        LEFT JOIN `tabBatch` batch
            ON batch.name = sed.batch_no
        WHERE se.docstatus = 1
          AND se.company = %(company)s
          AND sed.t_warehouse = %(warehouse)s
          AND sed.item_code IN ({item_codes_sql})
          {from_date_condition}
          AND TIMESTAMP(se.posting_date, se.posting_time) <= TIMESTAMP(%(as_of_date)s, %(as_of_time)s)
        ORDER BY
            se.posting_date,
            se.posting_time,
            se.creation,
            se.name,
            sed.idx
        """.format(
            item_codes_sql=item_codes_sql,
            from_date_condition=from_date_condition,
        ),
        params,
        as_dict=True,
    )


def _sort_stock_entries_for_rebuild(stock_entry_names):
    if not stock_entry_names:
        return []

    return [
        row.name
        for row in frappe.db.sql(
            """
            SELECT name
            FROM `tabStock Entry`
            WHERE name IN ({stock_entries})
            ORDER BY posting_date, posting_time, creation, name
            """.format(
                stock_entries=", ".join(
                    [frappe.db.escape(name) for name in stock_entry_names]
                )
            ),
            as_dict=True,
        )
    ]


def _get_item_master_valuation_updates(target_by_item):
    updates = []
    for item_code, target in sorted(target_by_item.items()):
        current_rate = flt(frappe.db.get_value("Item", item_code, "valuation_rate"))
        target_rate = flt(target["target_rate"])
        if abs(current_rate - target_rate) <= VALUATION_RATE_TOLERANCE:
            continue

        updates.append(
            {
                "item_code": item_code,
                "item_name": target["item_name"],
                "valuation_rule": target.get("valuation_rule"),
                "old_valuation_rate": current_rate,
                "target_rate": target_rate,
            }
        )
    return updates


def _get_missing_batch_rows_for_rebuild(stock_entry_names):
    """
    Return submitted Stock Entry rows that violate today's batch master setting.

    Some old Stock Entry rows were submitted without batch numbers before the
    Item was made batch-controlled. Reposting such vouchers should preserve the
    historical shape instead of inventing a batch or changing the Item master.
    """
    if not stock_entry_names:
        return []

    return frappe.db.sql(
        """
        SELECT
            sed.name AS row,
            sed.parent AS stock_entry,
            sed.item_code,
            item.item_name
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se
            ON se.name = sed.parent
        INNER JOIN `tabItem` item
            ON item.name = sed.item_code
        WHERE sed.parent IN ({stock_entries})
          AND se.docstatus = 1
          AND item.has_batch_no = 1
          AND IFNULL(sed.batch_no, '') = ''
          AND (
              IFNULL(sed.s_warehouse, '') != ''
              OR IFNULL(sed.t_warehouse, '') != ''
          )
        ORDER BY sed.parent, sed.idx
        """.format(
            stock_entries=", ".join(
                [frappe.db.escape(name) for name in stock_entry_names]
            )
        ),
        as_dict=True,
    )


def _get_serial_numbers_for_rebuild(stock_entry_names):
    if not stock_entry_names:
        return []

    rows = frappe.db.sql(
        """
        SELECT sed.serial_no
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se
            ON se.name = sed.parent
        WHERE sed.parent IN ({stock_entries})
          AND se.docstatus = 1
          AND IFNULL(sed.serial_no, '') != ''
        ORDER BY sed.parent, sed.idx
        """.format(
            stock_entries=", ".join(
                [frappe.db.escape(name) for name in stock_entry_names]
            )
        ),
        as_dict=True,
    )

    serial_nos = set()
    for row in rows:
        for serial_no in _split_serial_numbers(row.serial_no):
            serial_nos.add(serial_no)

    return sorted(serial_nos)


def _apply_scrap_devaluation_plan(
    plan, summary, log_id, allow_negative_stock, update_item_master
):
    existing_allow_negative_stock = frappe.db.get_value(
        "Stock Settings", None, "allow_negative_stock"
    )
    restore_stock_ledger_validation = None

    try:
        frappe.db.sql("set innodb_lock_wait_timeout = 300")
        if allow_negative_stock:
            frappe.db.set_value(
                "Stock Settings",
                None,
                "allow_negative_stock",
                1,
                update_modified=False,
            )

        if plan["disabled_batches"]:
            _set_batch_disabled_state(plan["disabled_batches"], 0)

        restore_stock_ledger_validation = _allow_historical_missing_batch_rows(
            plan["missing_batch_rows_for_rebuild"]
        )

        for stock_entry_name in plan["stock_entries"]:
            stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
            _apply_scrap_valuation_rows_to_stock_entry(
                stock_entry=stock_entry,
                row_plans=plan["rows_by_stock_entry"].get(stock_entry_name, []),
            )
            stock_entry.modified = frappe.utils.now()
            stock_entry.modified_by = frappe.session.user
            stock_entry.db_update()
            for row in stock_entry.items:
                row.db_update()

        if update_item_master:
            for item_update in plan["item_master_updates"]:
                frappe.db.set_value(
                    "Item",
                    item_update["item_code"],
                    "valuation_rate",
                    item_update["target_rate"],
                    update_modified=True,
                )
                summary["updated_items"].append(item_update["item_code"])

        for stock_entry_name in plan["stock_entries"]:
            stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
            serial_state = _seed_serial_numbers_for_stock_entry_rebuild(stock_entry)
            try:
                ledger_result = _rebuild_stock_entry_ledgers(
                    stock_entry,
                    allow_negative_stock=allow_negative_stock,
                )
            finally:
                _restore_serial_numbers_after_stock_entry_rebuild(serial_state)

            summary["rebuilt_stock_entries"].append(
                {
                    "stock_entry": stock_entry_name,
                    "ledger_result": ledger_result,
                }
            )
            frappe.clear_document_cache("Stock Entry", stock_entry_name)
            update_log_entry(
                log_id,
                "[{0}] Rebuilt Stock Entry {1}.<br>".format(
                    now_datetime(), stock_entry_name
                ),
            )

        if restore_stock_ledger_validation:
            restore_stock_ledger_validation()
            restore_stock_ledger_validation = None

        if plan["disabled_batches"]:
            _set_batch_disabled_state(plan["disabled_batches"], 1)

        if allow_negative_stock:
            frappe.db.set_value(
                "Stock Settings",
                None,
                "allow_negative_stock",
                existing_allow_negative_stock,
                update_modified=False,
            )

        frappe.db.commit()
        update_log_entry(
            log_id,
            "[{0}] Direct scrap devaluation repair completed.<br>".format(
                now_datetime()
            ),
        )
    except Exception:
        if restore_stock_ledger_validation:
            restore_stock_ledger_validation()
        frappe.db.rollback()
        if plan["disabled_batches"]:
            _set_batch_disabled_state(plan["disabled_batches"], 1)
        if allow_negative_stock:
            frappe.db.set_value(
                "Stock Settings",
                None,
                "allow_negative_stock",
                existing_allow_negative_stock,
                update_modified=False,
            )
        frappe.db.commit()
        raise


SERIAL_NO_REBUILD_STATE_FIELDS = (
    "item_code",
    "warehouse",
    "batch_no",
    "location",
    "company",
    "supplier",
    "supplier_name",
    "sales_order",
    "purchase_document_type",
    "purchase_document_no",
    "purchase_date",
    "purchase_time",
    "purchase_rate",
    "delivery_document_type",
    "delivery_document_no",
    "delivery_date",
    "delivery_time",
    "customer",
    "customer_name",
    "sales_invoice",
    "warranty_expiry_date",
    "maintenance_status",
)


def _seed_serial_numbers_for_stock_entry_rebuild(stock_entry):
    from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

    serial_state = {}
    for row in stock_entry.items:
        if not row.serial_no:
            continue

        seed_warehouse = row.s_warehouse or None
        for serial_no in get_serial_nos(row.serial_no):
            if not frappe.db.exists("Serial No", serial_no):
                continue

            if serial_no not in serial_state:
                serial_state[serial_no] = frappe.db.get_value(
                    "Serial No",
                    serial_no,
                    SERIAL_NO_REBUILD_STATE_FIELDS,
                    as_dict=True,
                )

            frappe.db.set_value(
                "Serial No",
                serial_no,
                "item_code",
                row.item_code,
                update_modified=False,
            )
            frappe.db.set_value(
                "Serial No",
                serial_no,
                "warehouse",
                seed_warehouse,
                update_modified=False,
            )
            frappe.db.set_value(
                "Serial No",
                serial_no,
                "batch_no",
                row.batch_no,
                update_modified=False,
            )
            frappe.db.set_value(
                "Serial No",
                serial_no,
                "company",
                stock_entry.company,
                update_modified=False,
            )
            frappe.clear_document_cache("Serial No", serial_no)

    return serial_state


def _restore_serial_numbers_after_stock_entry_rebuild(serial_state):
    for serial_no, state in (serial_state or {}).items():
        if not state:
            continue

        for fieldname in SERIAL_NO_REBUILD_STATE_FIELDS:
            frappe.db.set_value(
                "Serial No",
                serial_no,
                fieldname,
                state.get(fieldname),
                update_modified=False,
            )
        frappe.clear_document_cache("Serial No", serial_no)


def _split_serial_numbers(serial_no_value):
    return [
        serial_no.strip()
        for serial_no in cstr(serial_no_value).replace(",", "\n").splitlines()
        if serial_no.strip()
    ]


def _allow_historical_missing_batch_rows(missing_batch_rows):
    allowed_rows = {row.row for row in (missing_batch_rows or [])}
    if not allowed_rows:
        return None

    from erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry import (
        StockLedgerEntry,
    )

    original_validate_item = StockLedgerEntry.validate_item

    def validate_item_allowing_historical_missing_batch(self):
        try:
            return original_validate_item(self)
        except frappe.ValidationError as exc:
            if (
                self.voucher_type == "Stock Entry"
                and self.voucher_detail_no in allowed_rows
                and not cstr(self.batch_no).strip()
                and "Batch number is mandatory" in cstr(exc)
            ):
                return
            raise

    StockLedgerEntry.validate_item = validate_item_allowing_historical_missing_batch

    def restore():
        StockLedgerEntry.validate_item = original_validate_item

    return restore


def _apply_scrap_valuation_rows_to_stock_entry(stock_entry, row_plans):
    row_plan_by_name = {row_plan["row"]: row_plan for row_plan in row_plans}
    if not row_plan_by_name:
        return

    for row in stock_entry.items:
        row_plan = row_plan_by_name.get(row.name)
        if not row_plan:
            continue

        _set_stock_entry_detail_target_valuation(
            row,
            row_plan["target_rate"],
        )

    _rebalance_stock_entry_finished_goods_if_possible(stock_entry, row_plan_by_name)
    _recalculate_stock_entry_value_totals(stock_entry)


def _set_stock_entry_detail_target_valuation(row, target_rate):
    transfer_qty = flt(row.transfer_qty)
    if not transfer_qty:
        frappe.throw("Stock Entry Detail {0} has zero transfer_qty.".format(row.name))

    amount_precision = _get_doc_precision(row, "amount")
    basic_amount_precision = _get_doc_precision(row, "basic_amount")
    basic_rate_precision = _get_doc_precision(row, "basic_rate")
    valuation_rate_precision = _get_doc_precision(row, "valuation_rate")

    amount = flt(transfer_qty * flt(target_rate), amount_precision)
    basic_amount = flt(amount - flt(row.additional_cost), basic_amount_precision)
    basic_rate = flt(basic_amount / transfer_qty, basic_rate_precision)
    if basic_rate < -VALUATION_RATE_TOLERANCE:
        frappe.throw(
            "Stock Entry Detail {0} cannot be set to valuation rate {1} "
            "because additional cost is higher than the target amount.".format(
                row.name, target_rate
            )
        )

    row.basic_amount = basic_amount if abs(basic_amount) > VALUATION_RATE_TOLERANCE else 0
    row.basic_rate = basic_rate if abs(basic_rate) > VALUATION_RATE_TOLERANCE else 0
    row.amount = amount
    row.valuation_rate = flt(target_rate, valuation_rate_precision)


def _rebalance_stock_entry_finished_goods_if_possible(stock_entry, changed_rows):
    if stock_entry.purpose not in ("Manufacture", "Repack"):
        return

    changed_row_names = set(changed_rows)
    finished_good_rows = [
        row
        for row in stock_entry.items
        if row.t_warehouse and row.name not in changed_row_names
    ]
    if len(finished_good_rows) != 1:
        return

    finished_good = finished_good_rows[0]
    outgoing_amount = sum(
        flt(row.amount)
        for row in stock_entry.items
        if row.s_warehouse and not row.t_warehouse
    )
    other_incoming_amount = sum(
        flt(row.amount)
        for row in stock_entry.items
        if row.t_warehouse and row.name != finished_good.name
    )
    target_amount = flt(outgoing_amount - other_incoming_amount)
    if target_amount < -VALUATION_RATE_TOLERANCE:
        return

    _set_stock_entry_detail_target_amount(finished_good, max(target_amount, 0.0))


def _set_stock_entry_detail_target_amount(row, target_amount):
    transfer_qty = flt(row.transfer_qty)
    if not transfer_qty:
        return

    amount_precision = _get_doc_precision(row, "amount")
    basic_amount_precision = _get_doc_precision(row, "basic_amount")
    basic_rate_precision = _get_doc_precision(row, "basic_rate")
    valuation_rate_precision = _get_doc_precision(row, "valuation_rate")

    row.amount = flt(target_amount, amount_precision)
    row.basic_amount = flt(
        flt(row.amount) - flt(row.additional_cost),
        basic_amount_precision,
    )
    row.basic_rate = flt(row.basic_amount / transfer_qty, basic_rate_precision)
    row.valuation_rate = flt(row.amount / transfer_qty, valuation_rate_precision)


def _recalculate_stock_entry_value_totals(stock_entry):
    stock_entry.total_incoming_value = sum(
        flt(row.amount) for row in stock_entry.items if row.t_warehouse
    )
    stock_entry.total_outgoing_value = sum(
        flt(row.amount) for row in stock_entry.items if row.s_warehouse
    )
    stock_entry.value_difference = (
        flt(stock_entry.total_incoming_value) - flt(stock_entry.total_outgoing_value)
    )

    stock_entry.total_amount = None
    if stock_entry.purpose not in ("Manufacture", "Repack"):
        stock_entry.total_amount = sum(flt(row.amount) for row in stock_entry.items)


def _get_doc_precision(doc, fieldname, default=6):
    try:
        return doc.precision(fieldname)
    except Exception:
        return cint(frappe.db.get_default("float_precision")) or default


def _run_batch_valuation_reconciliation(
    batch_rows,
    skipped_at_target,
    warehouse,
    target_rate,
    scope_label,
    scope_summary,
    dry_run,
    max_rows_per_reconciliation,
):
    """
    Execute the shared Stock Reconciliation flow for a prepared batch-row set.

    This helper is the main production path used by both selector styles:
    Item Group and item-code prefix. It is responsible for logging, summary
    generation, chunking, document creation, submission, and commits.
    """
    dry_run = cint(dry_run)
    max_rows_per_reconciliation = cint(max_rows_per_reconciliation)
    posting_date, posting_time = _get_posting_context()

    log_id = _create_reconciliation_log(
        warehouse=warehouse,
        scope_label=scope_label,
        target_rate=target_rate,
        posting_date=posting_date,
        posting_time=posting_time,
        dry_run=dry_run,
    )
    company, expense_account, cost_center = _get_stock_reconciliation_defaults(
        warehouse
    )

    summary = {
        "log_id": log_id,
        "warehouse": warehouse,
        "target_rate": target_rate,
        "posting_date": posting_date,
        "posting_time": posting_time,
        "dry_run": bool(dry_run),
        "company": company,
        "expense_account": expense_account,
        "cost_center": cost_center,
        "items_count": len({row.item_code for row in batch_rows}),
        "batch_count": len(batch_rows),
        "skipped_batches_already_at_target": skipped_at_target,
        "reconciliations": [],
    }
    summary.update(scope_summary)

    if not batch_rows:
        update_log_entry(
            log_id,
            "[{0}] Nothing to reconcile. All matching batches are already at the target rate.<br>".format(
                now_datetime()
            ),
        )
        return summary

    row_chunks = _chunk_batch_rows(batch_rows, max_rows_per_reconciliation)
    update_log_entry(
        log_id,
        (
            "[{0}] Prepared {1} batch row(s) across {2} item(s) in {3} reconciliation document(s).<br>"
        ).format(
            now_datetime(),
            len(batch_rows),
            summary["items_count"],
            len(row_chunks),
        ),
    )

    if dry_run:
        return summary

    for chunk_index, chunk in enumerate(row_chunks, 1):
        # Each chunk becomes one Stock Reconciliation document. The chunking
        # logic keeps all batches of a given item together so valuation math is
        # not split across separate stock repost operations.
        reconciliation = _build_batch_valuation_reconciliation(
            batch_rows=chunk,
            warehouse=warehouse,
            company=company,
            expense_account=expense_account,
            cost_center=cost_center,
            posting_date=posting_date,
            posting_time=posting_time,
            target_rate=target_rate,
        )
        reconciliation.flags.ignore_permissions = True
        reconciliation.insert(ignore_permissions=True)
        # Submit synchronously so this worker controls ordering and logging of
        # the stock repost side effects for each chunk.
        reconciliation._submit()
        frappe.db.commit()

        item_codes = sorted({row.item_code for row in chunk})
        summary["reconciliations"].append(reconciliation.name)
        update_log_entry(
            log_id,
            (
                "[{0}] Submitted Stock Reconciliation {1} ({2}/{3}) with {4} batch row(s) for item(s): {5}<br>"
            ).format(
                now_datetime(),
                reconciliation.name,
                chunk_index,
                len(row_chunks),
                len(chunk),
                ", ".join(item_codes),
            ),
        )

    update_log_entry(
        log_id,
        "[{0}] Batch valuation reconciliation completed. Submitted {1} Stock Reconciliation document(s).<br>".format(
            now_datetime(), len(summary["reconciliations"])
        ),
    )
    return summary


def _create_reconciliation_log(
    warehouse, scope_label, target_rate, posting_date, posting_time, dry_run
):
    """Create or reuse the Log Entry used to trace one reconciliation run."""
    log_context = frappe._dict(
        {
            "doctype": "Stock Reconciliation",
            "name": "Batch valuation reconciliation {0} / {1} / {2}".format(
                warehouse, scope_label, now_datetime()
            ),
        }
    )
    log_id = _get_or_create_log(log_context)
    update_log_entry(
        log_id,
        (
            "[{0}] Started batch valuation reconciliation for warehouse={1}, scope={2}, "
            "target_rate={3}, posting_date={4}, posting_time={5}, dry_run={6}<br>"
        ).format(
            now_datetime(),
            warehouse,
            scope_label,
            target_rate,
            posting_date,
            posting_time,
            dry_run,
        ),
    )
    return log_id


def _get_posting_context():
    """
    Return the posting date and time to be stamped on generated Stock Reconciliations.

    Production note:
    The row selectors also consume this helper, so changing this timestamp
    changes both the document posting datetime and the historical stock state
    used to decide which scrap batches are reconciled.
    """
    return "2025-12-31", "23:59:59"


def _get_stock_reconciliation_defaults(warehouse):
    """
    Resolve the Company, stock adjustment account, and cost center for a warehouse.

    The function fails fast because Stock Reconciliation submission cannot
    proceed safely when these accounting defaults are missing.
    """
    company = frappe.db.get_value("Warehouse", warehouse, "company")
    if not company:
        frappe.throw("Warehouse {0} is missing a company.".format(warehouse))

    company_defaults = frappe.db.get_value(
        "Company",
        company,
        ["stock_adjustment_account", "cost_center"],
        as_dict=True,
    )
    expense_account = company_defaults.get("stock_adjustment_account")
    cost_center = company_defaults.get("cost_center")

    if not expense_account:
        frappe.throw(
            "Company {0} is missing Stock Adjustment Account.".format(company)
        )
    if not cost_center:
        frappe.throw("Company {0} is missing default Cost Center.".format(company))

    return company, expense_account, cost_center


def _get_batch_rows_by_item_group(warehouse, item_group, target_rate):
    """
    Collect candidate batch rows for one Item Group under the posting context.

    This is the legacy selector. Filtering by target rate is done after the row
    set is loaded so the same comparison logic is shared with prefix rules.
    """
    group_bounds = frappe.db.get_value(
        "Item Group", item_group, ["lft", "rgt"], as_dict=True
    )
    if not group_bounds:
        frappe.throw("Item Group {0} was not found.".format(item_group))

    batch_rows = _fetch_batch_rows(
        warehouse=warehouse,
        extra_joins="""
        INNER JOIN `tabItem Group` item_group
            ON item_group.name = item.item_group
        """,
        extra_conditions="""
          AND item_group.lft >= %(group_lft)s
          AND item_group.rgt <= %(group_rgt)s
        """,
        params={
            "group_lft": group_bounds.lft,
            "group_rgt": group_bounds.rgt,
        },
    )
    return _filter_batch_rows_by_target_rate(batch_rows, target_rate)


def _get_batch_rows_by_code_prefix(warehouse, code_prefix, code_length, target_rate):
    """
    Collect candidate batch rows for one code-prefix rule under the posting context.

    Example:
    `code_prefix='10', code_length=6` matches codes like `100123`.
    """
    batch_rows = _fetch_batch_rows(
        warehouse=warehouse,
        extra_conditions="""
          AND sle.item_code LIKE %(like_pattern)s
          AND CHAR_LENGTH(sle.item_code) = %(code_length)s
        """,
        params={
            "like_pattern": "{0}%".format(code_prefix),
            "code_length": code_length,
        },
    )
    return _filter_batch_rows_by_target_rate(batch_rows, target_rate)


def _fetch_batch_rows(warehouse, extra_joins="", extra_conditions="", params=None):
    """
    Fetch historical scrap batch balances from Stock Ledger Entry.

    Important:
    This function intentionally does not read `tabBin`. `Bin` is a current-state
    snapshot and would be incorrect for backdated Stock Reconciliations. The
    query therefore aggregates only SLE rows up to `_get_posting_context()`.
    """
    posting_date, posting_time = _get_posting_context()
    query_params = {"warehouse": warehouse}
    if params:
        query_params.update(params)
    query_params.update(
        {
            "posting_date": posting_date,
            "posting_time": posting_time,
        }
    )

    batch_rows = frappe.db.sql(
        """
        SELECT
            sle.item_code,
            item.item_name,
            sle.batch_no,
            SUM(sle.actual_qty) AS qty
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabItem` item
            ON item.name = sle.item_code
        {extra_joins}
        WHERE sle.warehouse = %(warehouse)s
          AND IFNULL(sle.batch_no, '') != ''
          AND IFNULL(sle.is_cancelled, 'No') = 'No'
          AND TIMESTAMP(sle.posting_date, sle.posting_time) <= TIMESTAMP(%(posting_date)s, %(posting_time)s)
          AND item.disabled = 0
          AND item.has_batch_no = 1
        {extra_conditions}
        GROUP BY
            sle.item_code,
            item.item_name,
            sle.batch_no
        HAVING qty > 0
        ORDER BY sle.item_code, sle.batch_no
        """.format(
            extra_joins=extra_joins or "",
            extra_conditions=extra_conditions or "",
        ),
        query_params,
        as_dict=True,
    )

    # The comparison rate must reflect the same historical cutoff as the
    # quantity query above, otherwise the reconciliation can mix past stock
    # levels with present-day valuation rates.
    valuation_rate_map = _get_historical_valuation_rate_map(
        item_codes=sorted({row.item_code for row in batch_rows}),
        warehouse=warehouse,
        posting_date=posting_date,
        posting_time=posting_time,
    )

    for row in batch_rows:
        row.current_valuation_rate = flt(valuation_rate_map.get(row.item_code))

    return batch_rows


def _get_historical_valuation_rate_map(
    item_codes, warehouse, posting_date, posting_time
):
    """
    Resolve the last valuation rate per item at the requested historical cutoff.

    The lookup is warehouse-specific because ERPNext valuation can diverge by
    warehouse over time.
    """
    if not item_codes:
        return {}

    from erpnext.stock.stock_ledger import get_previous_sle

    valuation_rate_map = {}
    for item_code in item_codes:
        previous_sle = get_previous_sle(
            {
                "item_code": item_code,
                "warehouse": warehouse,
                "posting_date": posting_date,
                "posting_time": posting_time,
            }
        )
        valuation_rate_map[item_code] = flt(previous_sle.get("valuation_rate"))

    return valuation_rate_map


def _filter_batch_rows_by_target_rate(batch_rows, target_rate):
    """
    Split fetched batch rows into actionable rows and already-correct rows.

    A small tolerance is used to avoid posting pointless reconciliations caused
    by floating-point representation noise.
    """
    eligible_rows = []
    skipped_at_target = 0

    for row in batch_rows:
        row.qty = flt(row.qty)
        row.current_valuation_rate = flt(row.current_valuation_rate)
        if abs(row.current_valuation_rate - target_rate) <= VALUATION_RATE_TOLERANCE:
            skipped_at_target += 1
            continue
        eligible_rows.append(row)

    return eligible_rows, skipped_at_target


def _chunk_batch_rows(batch_rows, max_rows_per_reconciliation):
    """
    Split batch rows into reconciliation-sized chunks without splitting an item.

    Keeping all rows of the same item together avoids valuation drift caused by
    multiple back-to-back reconciliations on the same item and warehouse.
    """
    if not batch_rows:
        return []

    if max_rows_per_reconciliation <= 0:
        return [batch_rows]

    grouped_rows = []
    current_group = []
    current_item_code = None

    for row in batch_rows:
        if row.item_code != current_item_code:
            if current_group:
                grouped_rows.append(current_group)
            current_group = [row]
            current_item_code = row.item_code
        else:
            current_group.append(row)

    if current_group:
        grouped_rows.append(current_group)

    chunks = []
    current_chunk = []
    current_size = 0

    for item_rows in grouped_rows:
        item_row_count = len(item_rows)
        if (
            current_chunk
            and current_size + item_row_count > max_rows_per_reconciliation
        ):
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

        current_chunk.extend(item_rows)
        current_size += item_row_count

        if item_row_count >= max_rows_per_reconciliation:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _build_batch_valuation_reconciliation(
    batch_rows,
    warehouse,
    company,
    expense_account,
    cost_center,
    posting_date,
    posting_time,
    target_rate,
):
    """
    Build one Stock Reconciliation document from a prepared batch-row chunk.

    The document is prefilled with current quantity, current valuation rate,
    current amount, and amount difference so ERPNext can skip its slower
    row-by-row "remove items with no change" recomputation path.
    """
    reconciliation = frappe.new_doc("Stock Reconciliation")
    reconciliation.company = company
    reconciliation.posting_date = posting_date
    reconciliation.posting_time = posting_time
    reconciliation.set_posting_time = 1
    reconciliation.expense_account = expense_account
    reconciliation.cost_center = cost_center
    reconciliation.ignore_remove_items_with_no_change = 1

    difference_amount = 0.0
    for row in batch_rows:
        qty = flt(row.qty)
        current_rate = flt(row.current_valuation_rate)
        current_amount = qty * current_rate
        target_amount = qty * target_rate
        amount_difference = target_amount - current_amount
        difference_amount += amount_difference

        reconciliation.append(
            "items",
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "warehouse": warehouse,
                "qty": qty,
                "valuation_rate": target_rate,
                "batch_no": row.batch_no,
                "current_qty": qty,
                "current_valuation_rate": current_rate,
                "current_amount": current_amount,
                "quantity_difference": 0,
                "amount_difference": amount_difference,
            },
        )

    reconciliation.difference_amount = difference_amount
    return reconciliation


def _format_code_rule_label(code_prefix, code_length):
    """Render a readable label such as `code-prefix 10xxxx` for logs."""
    return "code-prefix {0}{1}".format(
        code_prefix, "x" * max(code_length - len(code_prefix), 0)
    )


def _get_sales_items_missing_prices():
    """Return active sales items that do not have any Item Price record."""
    missing_price_items = []
    sales_items = frappe.get_all(
        "Item",
        filters={"is_sales_item": 1, "disabled": 0},
        fields=["name", "item_name"],
    )

    for item in sales_items:
        if not frappe.db.exists("Item Price", {"item_code": item.name}):
            missing_price_items.append(item)

    return missing_price_items


def _get_recent_sales_items(lookback_days):
    """Return active sales items created within the configured lookback window."""
    return frappe.get_all(
        "Item",
        filters={
            "is_sales_item": 1,
            "disabled": 0,
            "creation": [">", frappe.utils.add_days(nowdate(), -lookback_days)],
        },
        fields=["name", "item_name"],
    )


def _build_item_list_html(items):
    """Render an HTML bullet list used in the outbound sales notification email."""
    if not items:
        return ""

    item_list_html = "<ul>"
    for item in items:
        item_list_html += "<li>{0} ({1})</li>".format(item.item_name, item.name)
    item_list_html += "</ul>"
    return item_list_html
