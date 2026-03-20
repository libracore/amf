from amf.amf.utils.stock_entry import _get_or_create_log, update_log_entry

import frappe
from frappe.utils import cint, flt, now_datetime, nowdate, nowtime

DEFAULT_BATCH_VALUATION_WAREHOUSE = "Scrap - AMF21"
DEFAULT_BATCH_VALUATION_ITEM_GROUP = "Valve Seat"
DEFAULT_BATCH_VALUATION_RATE = 20.0
DEFAULT_BATCH_VALUATION_CODE_LENGTH = 6
DEFAULT_RECONCILIATION_ROWS = 100
VALUATION_RATE_TOLERANCE = 0.000001
DEFAULT_BATCH_VALUATION_TARGETS = (
    {"code_prefix": "10", "code_length": 6, "target_rate": 0.5},
    {"code_prefix": "11", "code_length": 6, "target_rate": 0.75},
    {"code_prefix": "2", "code_length": 6, "target_rate": 20.0},
    {"code_prefix": "30", "code_length": 6, "target_rate": 20.75},
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
