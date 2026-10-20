"""FFTest stock-entry orchestration and diagnostics.

The public API in this module is called by the database-backed Web Page
``fftest-stock-entry``.  Keep the whitelisted method names and their response
shape stable: the local FFTest server treats a returned ``{"error": ...}`` as
an execution failure.

One serial value is supplied by the operator.  For P202 bodies, that value is
the finished 5D1000 serial (for example ``P202-O00000070``); its existing
5D0000 source serial (``0070``) is resolved from the database.
"""

import json
from collections import defaultdict

import frappe
from frappe import ValidationError, _
from frappe.utils import cint, cstr, flt, now_datetime

from amf.amf.utils.batch_naming import make_internal_production_batch_id
from amf.amf.utils.stock_entry import get_stock_and_rate_override
from amf.amf.utils.utilities import update_log_entry
from amf.amf.utils.work_order_creation import get_default_bom


COMPANY = "Advanced Microfluidics SA"
MAIN_STOCK_WAREHOUSE = "Main Stock - AMF21"
WIP_WAREHOUSE = "Work In Progress - AMF21"

P202_RAW_ITEM_CODE = "5D0000"
P202_SERIALIZED_ITEM_CODE = "5D1000"
P202_SERIAL_PREFIX = "P202-O"
P202_SERIAL_DIGITS = 8

ACTIVE_WORK_ORDER_STATUSES = ("Not Started", "In Process")
SERIAL_FIELDS = (
    "name",
    "serial_no",
    "item_code",
    "warehouse",
    "batch_no",
    "purchase_document_no",
    "delivery_document_no",
)


class _ExecutionLog:
    """Collect one request's messages without using module-global state."""

    def __init__(self, source_work_order_id):
        self.name = None
        self.messages = []
        try:
            self.name = create_log_entry(
                _("FFTest stock flow started for Work Order {0}.").format(
                    source_work_order_id
                ),
                category="FFTest Stock Entry",
            )
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback(),
                title="Unable to create FFTest execution log",
            )

    def add(self, message):
        message = cstr(message).strip()
        if message:
            self.messages.append(message)
            frappe.logger("fftest_stock_entry").debug(message)

    def flush(self):
        if not self.name or not self.messages:
            return
        try:
            update_log_entry(self.name, "\n".join(self.messages))
            self.messages = []
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback(),
                title="Unable to update FFTest execution log",
            )


def _log(run_log, message):
    if run_log:
        run_log.add(message)


def _build_p202_finished_serial(source_serial_no):
    """Return the 5D1000 serial generated from a numeric 5D0000 serial."""
    source_serial_no = cstr(source_serial_no).strip()
    if (
        not source_serial_no
        or not source_serial_no.isdigit()
        or len(source_serial_no) > P202_SERIAL_DIGITS
    ):
        raise ValidationError(
            _("5D0000 Serial No must contain at most {0} digits.").format(
                P202_SERIAL_DIGITS
            )
        )

    return "{0}{1}".format(
        P202_SERIAL_PREFIX,
        source_serial_no.zfill(P202_SERIAL_DIGITS),
    )


def _validate_p202_finished_serial(finished_serial_no):
    finished_serial_no = cstr(finished_serial_no).strip()
    suffix = finished_serial_no[len(P202_SERIAL_PREFIX) :]
    if (
        not finished_serial_no.startswith(P202_SERIAL_PREFIX)
        or len(suffix) != P202_SERIAL_DIGITS
        or not suffix.isdigit()
    ):
        raise ValidationError(
            _("5D1000 Serial No must use the format {0}########.").format(
                P202_SERIAL_PREFIX
            )
        )
    return finished_serial_no


def _parse_debug_batch_list(batch_no_id):
    """Accept the Web Page's JSON string or its already-decoded list."""
    if not batch_no_id:
        return []
    if isinstance(batch_no_id, str):
        try:
            batch_no_id = json.loads(batch_no_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                _("Invalid batch_list JSON: {0}").format(cstr(exc))
            )
    if not isinstance(batch_no_id, list):
        raise ValidationError(_("batch_list must be a JSON array."))
    return batch_no_id


def _get_work_order(work_order_id, check_permission=False):
    work_order_id = cstr(work_order_id).strip()
    if not work_order_id or not frappe.db.exists("Work Order", work_order_id):
        raise ValidationError(
            _("Work Order {0} does not exist.").format(work_order_id or "")
        )

    work_order = frappe.get_doc("Work Order", work_order_id)
    if check_permission:
        work_order.check_permission("read")
    return work_order


def _get_valid_bom(bom_no):
    if not bom_no or not frappe.db.exists("BOM", bom_no):
        raise ValidationError(_("BOM {0} does not exist.").format(bom_no or ""))

    bom = frappe.get_doc("BOM", bom_no)
    if bom.docstatus != 1 or not cint(bom.is_active):
        raise ValidationError(
            _("BOM {0} must be submitted and active.").format(bom.name)
        )
    return bom


def _validate_work_order_for_one_unit(work_order):
    if work_order.docstatus != 1:
        raise ValidationError(
            _("Work Order {0} must be submitted.").format(work_order.name)
        )
    if flt(work_order.produced_qty) + 1 > flt(work_order.qty):
        raise ValidationError(
            _("Work Order {0} cannot produce another unit.").format(work_order.name)
        )
    _get_valid_bom(work_order.bom_no)


def _get_serial_details(serial_no):
    serial_no = cstr(serial_no).strip()
    if not serial_no:
        return None

    serial = frappe.db.get_value(
        "Serial No",
        serial_no,
        SERIAL_FIELDS,
        as_dict=True,
    )
    if not serial:
        serial = frappe.db.get_value(
            "Serial No",
            {"serial_no": serial_no},
            SERIAL_FIELDS,
            as_dict=True,
        )
    return serial


def _get_p202_source_serial(finished_serial_no):
    """Resolve the existing 5D0000 serial represented by a P202 output serial."""
    finished_serial_no = _validate_p202_finished_serial(finished_serial_no)
    matches = frappe.db.sql(
        """
        SELECT
            name,
            serial_no,
            item_code,
            warehouse,
            batch_no,
            purchase_document_no,
            delivery_document_no
        FROM `tabSerial No`
        WHERE item_code = %s
          AND serial_no REGEXP '^[0-9]+$'
          AND CHAR_LENGTH(serial_no) <= %s
          AND CONCAT(%s, LPAD(serial_no, %s, '0')) = %s
        ORDER BY creation ASC
        """,
        (
            P202_RAW_ITEM_CODE,
            P202_SERIAL_DIGITS,
            P202_SERIAL_PREFIX,
            P202_SERIAL_DIGITS,
            finished_serial_no,
        ),
        as_dict=True,
    )

    if not matches:
        raise ValidationError(
            _(
                "No existing {0} Serial No matches {1}. "
                "Scan a received 5D0000 serial before running the test."
            ).format(P202_RAW_ITEM_CODE, finished_serial_no)
        )
    if len(matches) > 1:
        raise ValidationError(
            _("More than one {0} Serial No maps to {1}: {2}").format(
                P202_RAW_ITEM_CODE,
                finished_serial_no,
                ", ".join(row.name for row in matches),
            )
        )
    return matches[0]


def _lock_serial(serial_no):
    frappe.db.sql(
        "SELECT name FROM `tabSerial No` WHERE name = %s FOR UPDATE",
        (serial_no,),
    )


def _lock_work_order(work_order_id):
    frappe.db.sql(
        "SELECT name FROM `tabWork Order` WHERE name = %s FOR UPDATE",
        (work_order_id,),
    )


def _validate_serial_location(serial_details, item_code, allowed_warehouses):
    if not serial_details:
        raise ValidationError(_("Serial No does not exist."))
    if serial_details.item_code != item_code:
        raise ValidationError(
            _("Serial No {0} belongs to Item {1}, not Item {2}.").format(
                serial_details.name,
                serial_details.item_code,
                item_code,
            )
        )
    if serial_details.warehouse not in allowed_warehouses:
        if serial_details.delivery_document_no:
            raise ValidationError(
                _("Serial No {0} was already consumed by {1}.").format(
                    serial_details.name,
                    serial_details.delivery_document_no,
                )
            )
        raise ValidationError(
            _("Serial No {0} is in Warehouse {1}; expected {2}.").format(
                serial_details.name,
                serial_details.warehouse or _("no warehouse"),
                ", ".join(allowed_warehouses),
            )
        )


def _set_source_serial(row, serial_details, expected_warehouse):
    _validate_serial_location(
        serial_details,
        row.item_code,
        (expected_warehouse,),
    )
    row.serial_no = serial_details.name
    row.manual_source_warehouse_selection = 1
    row.s_warehouse = expected_warehouse

    if cint(frappe.db.get_value("Item", row.item_code, "has_batch_no")):
        if not serial_details.batch_no:
            raise ValidationError(
                _("Serial No {0} has no Batch No.").format(serial_details.name)
            )
        batch = frappe.db.get_value(
            "Batch",
            serial_details.batch_no,
            ["name", "item", "disabled"],
            as_dict=True,
        )
        if not batch or batch.item != row.item_code or cint(batch.disabled):
            raise ValidationError(
                _("Serial No {0} has an invalid Batch {1}.").format(
                    serial_details.name,
                    serial_details.batch_no,
                )
            )
        row.auto_batch_no_generation = 0
        row.batch_no = batch.name


def _work_order_uses_p202_body(work_order_id):
    production_item = frappe.db.get_value(
        "Work Order", work_order_id, "production_item"
    )
    if production_item == P202_SERIALIZED_ITEM_CODE:
        return True
    return bool(
        frappe.db.exists(
            "Work Order Item",
            {
                "parent": work_order_id,
                "item_code": P202_SERIALIZED_ITEM_CODE,
            },
        )
    )


def _serialized_component_codes(work_order_id):
    rows = frappe.db.sql(
        """
        SELECT DISTINCT woi.item_code
        FROM `tabWork Order Item` AS woi
        INNER JOIN `tabItem` AS item ON item.name = woi.item_code
        WHERE woi.parent = %s
          AND item.has_serial_no = 1
        ORDER BY woi.idx ASC
        """,
        (work_order_id,),
        as_dict=True,
    )
    return [row.item_code for row in rows]


def _work_order_has_capacity(work_order, require_transfer_capacity=False):
    if not work_order:
        return False
    if work_order.status not in ACTIVE_WORK_ORDER_STATUSES:
        return False
    if flt(work_order.produced_qty) + 1 > flt(work_order.qty):
        return False
    if require_transfer_capacity:
        return (
            flt(work_order.material_transferred_for_manufacturing) + 1
            <= flt(work_order.qty)
        )
    return True


def _active_work_orders_for_items(item_codes, parent_work_order=None):
    if not item_codes:
        return []

    filters = {
        "docstatus": 1,
        "production_item": ["in", item_codes],
        "status": ["in", list(ACTIVE_WORK_ORDER_STATUSES)],
    }
    if parent_work_order is not None:
        filters["parent_work_order"] = parent_work_order

    rows = frappe.get_all(
        "Work Order",
        filters=filters,
        fields=[
            "name",
            "production_item",
            "status",
            "qty",
            "produced_qty",
            "material_transferred_for_manufacturing",
            "parent_work_order",
        ],
        order_by="creation ASC",
    )
    return [row for row in rows if _work_order_has_capacity(row)]


def _find_serialized_work_orders(
    source_work_order_id,
    create_missing=False,
    run_log=None,
):
    source_work_order = _get_work_order(source_work_order_id)
    item_codes = _serialized_component_codes(source_work_order_id)
    _log(run_log, "Serialized Work Order items: {0}".format(item_codes))

    if not item_codes:
        if cstr(source_work_order.production_item).startswith("5"):
            return [
                {
                    "work_order_name": source_work_order.name,
                    "production_item": source_work_order.production_item,
                }
            ]
        return []

    candidates = _active_work_orders_for_items(
        item_codes,
        parent_work_order=source_work_order_id,
    )
    if not candidates:
        candidates = _active_work_orders_for_items(
            item_codes,
            parent_work_order="",
        )

    if not candidates and create_missing:
        candidates = []
        for item_code in item_codes:
            work_order = create_new_wo(
                item_code=item_code,
                sales_order=source_work_order.sales_order,
                qty=1,
                parent_work_order=source_work_order_id,
                company=source_work_order.company,
                run_log=run_log,
            )
            candidates.append(
                {
                    "name": work_order.name,
                    "production_item": work_order.production_item,
                }
            )

    result = []
    seen = set()
    for candidate in candidates:
        name = candidate.get("work_order_name") or candidate.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(
            {
                "work_order_name": name,
                "production_item": candidate.get("production_item"),
            }
        )
    return result


@frappe.whitelist()
def get_serialized_items_with_existing_work_orders(work_order_id):
    """Return active serialized-component Work Orders without creating records."""
    _get_work_order(work_order_id, check_permission=True)
    return _find_serialized_work_orders(work_order_id, create_missing=False)


def _get_p202_wip_work_order(serial_details):
    """Find the active 5D1000 WO associated with a raw serial already in WIP."""
    if (
        not serial_details
        or serial_details.get("warehouse") != WIP_WAREHOUSE
        or not serial_details.get("purchase_document_no")
    ):
        return None

    work_order_id = frappe.db.get_value(
        "Stock Entry",
        {
            "name": serial_details.purchase_document_no,
            "docstatus": 1,
            "purpose": "Material Transfer for Manufacture",
        },
        "work_order",
    )
    if not work_order_id:
        return None

    work_order = frappe.db.get_value(
        "Work Order",
        work_order_id,
        [
            "name",
            "production_item",
            "status",
            "qty",
            "produced_qty",
            "material_transferred_for_manufacturing",
        ],
        as_dict=True,
    )
    if (
        not work_order
        or work_order.production_item != P202_SERIALIZED_ITEM_CODE
        or not _work_order_has_capacity(work_order)
    ):
        return None
    return {
        "work_order_name": work_order.name,
        "production_item": work_order.production_item,
    }


def _select_p202_work_order_for_main_stock(
    existing_work_orders,
    source_work_order=None,
    run_log=None,
):
    for candidate in existing_work_orders or []:
        name = candidate.get("work_order_name") or candidate.get("name")
        work_order = frappe.db.get_value(
            "Work Order",
            name,
            [
                "name",
                "production_item",
                "status",
                "qty",
                "produced_qty",
                "material_transferred_for_manufacturing",
            ],
            as_dict=True,
        )
        if (
            work_order
            and work_order.production_item == P202_SERIALIZED_ITEM_CODE
            and _work_order_has_capacity(work_order, require_transfer_capacity=True)
        ):
            return {
                "work_order_name": work_order.name,
                "production_item": work_order.production_item,
            }

    parent = _get_work_order(source_work_order) if source_work_order else None
    work_order = create_new_wo(
        item_code=P202_SERIALIZED_ITEM_CODE,
        sales_order=parent.sales_order if parent else "",
        qty=1,
        parent_work_order=parent.name if parent else None,
        company=parent.company if parent else COMPANY,
        run_log=run_log,
    )
    return {
        "work_order_name": work_order.name,
        "production_item": work_order.production_item,
    }


def _batch_stock_quantity(item_code, batch_no, warehouse=MAIN_STOCK_WAREHOUSE):
    return flt(
        frappe.db.sql(
            """
            SELECT COALESCE(SUM(actual_qty), 0)
            FROM `tabStock Ledger Entry`
            WHERE item_code = %s
              AND batch_no = %s
              AND warehouse = %s
              AND is_cancelled = 0
            """,
            (item_code, batch_no, warehouse),
        )[0][0]
    )


def _inspect_batch_inputs(batch_rows):
    results = []
    errors = []
    for index, row in enumerate(batch_rows, start=1):
        if not isinstance(row, dict):
            errors.append(_("Batch row {0} must be an object.").format(index))
            continue

        batch_no = cstr(row.get("batch_no")).strip()
        batch = (
            frappe.db.get_value(
                "Batch",
                batch_no,
                ["name", "item", "disabled"],
                as_dict=True,
            )
            if batch_no
            else None
        )
        result = {
            "input": row,
            "exists": bool(batch),
            "name": batch.name if batch else batch_no,
            "item": batch.item if batch else None,
            "disabled": batch.disabled if batch else None,
            "available_qty": (
                _batch_stock_quantity(batch.item, batch.name) if batch else 0
            ),
        }
        results.append(result)

        if not batch_no:
            errors.append(_("Batch row {0} has no batch_no.").format(index))
        elif not batch:
            errors.append(_("Batch {0} does not exist.").format(batch_no))
        elif cint(batch.disabled):
            errors.append(_("Batch {0} is disabled.").format(batch.name))
        elif result["available_qty"] <= 0:
            errors.append(
                _("Batch {0} has no stock in {1}.").format(
                    batch.name,
                    MAIN_STOCK_WAREHOUSE,
                )
            )
    return results, errors


def _outgoing_item_quantities(stock_entry):
    quantities = defaultdict(float)
    for row in stock_entry.items:
        if row.s_warehouse:
            quantities[row.item_code] += flt(row.transfer_qty or row.qty)
    return quantities


def _build_batch_map(batch_rows, required_quantities):
    batch_map = {}
    for index, row in enumerate(batch_rows, start=1):
        if not isinstance(row, dict):
            raise ValidationError(
                _("Batch row {0} must be an object.").format(index)
            )
        batch_no = cstr(row.get("batch_no")).strip()
        if not batch_no:
            raise ValidationError(
                _("Batch row {0} has no batch_no.").format(index)
            )

        batch = frappe.db.get_value(
            "Batch",
            batch_no,
            ["name", "item", "disabled"],
            as_dict=True,
        )
        if not batch:
            raise ValidationError(_("Batch {0} does not exist.").format(batch_no))
        if cint(batch.disabled):
            raise ValidationError(_("Batch {0} is disabled.").format(batch.name))
        if batch.item not in required_quantities:
            raise ValidationError(
                _("Batch {0} belongs to Item {1}, which is not consumed here.").format(
                    batch.name,
                    batch.item,
                )
            )
        if batch.item in batch_map:
            raise ValidationError(
                _("Only one Batch may be supplied for Item {0}.").format(batch.item)
            )

        available_qty = _batch_stock_quantity(batch.item, batch.name)
        required_qty = flt(required_quantities[batch.item])
        if available_qty + 1e-9 < required_qty:
            raise ValidationError(
                _(
                    "Batch {0} has {1} of Item {2} in {3}; {4} is required."
                ).format(
                    batch.name,
                    available_qty,
                    batch.item,
                    MAIN_STOCK_WAREHOUSE,
                    required_qty,
                )
            )
        batch_map[batch.item] = batch
    return batch_map


def _new_stock_entry(
    work_order,
    purpose,
    from_warehouse,
    to_warehouse,
):
    _validate_work_order_for_one_unit(work_order)

    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = purpose
    stock_entry.work_order = work_order.name
    stock_entry.company = work_order.company or COMPANY
    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order.bom_no
    stock_entry.use_multi_level_bom = 0
    stock_entry.fg_completed_qty = 1
    stock_entry.inspection_required = 0
    stock_entry.from_warehouse = from_warehouse
    stock_entry.to_warehouse = to_warehouse
    stock_entry.project = work_order.project
    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    if not stock_entry.items:
        raise ValidationError(
            _("No Stock Entry items were generated for Work Order {0}.").format(
                work_order.name
            )
        )
    return stock_entry


def _finished_good_row(stock_entry, work_order):
    row = next(
        (
            item
            for item in stock_entry.items
            if item.item_code == work_order.production_item and item.t_warehouse
        ),
        None,
    )
    if not row:
        raise ValidationError(
            _("Finished-good row was not generated for Work Order {0}.").format(
                work_order.name
            )
        )
    return row


def _manufacturing_source_warehouse(work_order):
    if cint(work_order.get("wip_step")):
        return MAIN_STOCK_WAREHOUSE
    return work_order.wip_warehouse or WIP_WAREHOUSE


def _needs_material_transfer(work_order):
    if _manufacturing_source_warehouse(work_order) == MAIN_STOCK_WAREHOUSE:
        return False
    quantity_needed_for_next_unit = min(
        flt(work_order.qty),
        flt(work_order.produced_qty) + 1,
    )
    return (
        flt(work_order.material_transferred_for_manufacturing) + 1e-9
        < quantity_needed_for_next_unit
    )


def _validate_source_tracking(stock_entry):
    """Fail with a useful message before ERPNext's generic tracking error."""
    source_rows = [row for row in stock_entry.items if row.s_warehouse]
    item_codes = list({row.item_code for row in source_rows})
    tracking = {
        row.name: row
        for row in frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]} if item_codes else {"name": ""},
            fields=["name", "has_serial_no", "has_batch_no"],
        )
    }

    missing_serials = sorted(
        {
            row.item_code
            for row in source_rows
            if tracking.get(row.item_code)
            and cint(tracking[row.item_code].has_serial_no)
            and not cstr(row.serial_no).strip()
        }
    )
    missing_batches = sorted(
        {
            row.item_code
            for row in source_rows
            if tracking.get(row.item_code)
            and cint(tracking[row.item_code].has_batch_no)
            and not row.batch_no
        }
    )
    if missing_serials:
        raise ValidationError(
            _("Serial No is required for source Item(s): {0}.").format(
                ", ".join(missing_serials)
            )
        )
    if missing_batches:
        raise ValidationError(
            _("Batch No is required for source Item(s): {0}.").format(
                ", ".join(missing_batches)
            )
        )


def _submit_stock_entry(stock_entry, run_log=None):
    _validate_source_tracking(stock_entry)
    stock_entry.save()
    _log(run_log, "Saving Stock Entry {0}.".format(stock_entry.name))
    stock_entry.submit()
    _log(run_log, "Submitted Stock Entry {0}.".format(stock_entry.name))
    return stock_entry


def start_work_order(work_order_id, source_serials=None, run_log=None):
    """Transfer one unit of a Work Order's materials from Main Stock to WIP."""
    source_serials = source_serials or {}
    work_order = _get_work_order(work_order_id)
    target_warehouse = work_order.wip_warehouse or WIP_WAREHOUSE
    stock_entry = _new_stock_entry(
        work_order,
        purpose="Material Transfer for Manufacture",
        from_warehouse=MAIN_STOCK_WAREHOUSE,
        to_warehouse=target_warehouse,
    )

    assigned_serial_items = set()
    for row in stock_entry.items:
        row.manual_source_warehouse_selection = 1
        row.s_warehouse = MAIN_STOCK_WAREHOUSE
        row.manual_target_warehouse_selection = 1
        row.t_warehouse = target_warehouse

        source_serial_no = source_serials.get(row.item_code)
        if source_serial_no:
            serial_details = _get_serial_details(source_serial_no)
            _set_source_serial(row, serial_details, MAIN_STOCK_WAREHOUSE)
            assigned_serial_items.add(row.item_code)

    missing_items = set(source_serials) - assigned_serial_items
    if missing_items:
        raise ValidationError(
            _("The transfer contains no row for serialized Item(s): {0}.").format(
                ", ".join(sorted(missing_items))
            )
        )

    _log(run_log, "Transferring material for Work Order {0}.".format(work_order_id))
    return _submit_stock_entry(stock_entry, run_log=run_log)


def assign_or_create_batch_for_last_item(
    work_order_id,
    last_item,
    run_log=None,
):
    """Return the Work Order Batch for a batch-tracked output item."""
    if not cint(frappe.db.get_value("Item", last_item.item_code, "has_batch_no")):
        return None

    rows = frappe.get_all(
        "Batch",
        filters={
            "work_order": work_order_id,
            "item": last_item.item_code,
            "disabled": 0,
        },
        fields=["name"],
        order_by="creation ASC",
        limit_page_length=1,
    )
    if rows:
        return rows[0].name

    batch_doc = frappe.new_doc("Batch")
    batch_doc.name = create_batch_name(last_item.item_code)
    batch_doc.batch_id = batch_doc.name
    batch_doc.item = last_item.item_code
    batch_doc.work_order = work_order_id
    batch_doc.insert(ignore_permissions=True)
    _log(
        run_log,
        "Created Batch {0} for Work Order {1}.".format(
            batch_doc.name,
            work_order_id,
        ),
    )
    return batch_doc.name


def _configure_output_rows(stock_entry, work_order, run_log=None):
    for row in stock_entry.items:
        if not row.t_warehouse:
            continue
        row.manual_target_warehouse_selection = 1
        if row.item_code == work_order.production_item:
            row.t_warehouse = MAIN_STOCK_WAREHOUSE
            continue
        if "Scrap" in cstr(row.t_warehouse):
            row.t_warehouse = MAIN_STOCK_WAREHOUSE
            if cint(frappe.db.get_value("Item", row.item_code, "has_batch_no")):
                row.auto_batch_no_generation = 0
                row.batch_no = assign_or_create_batch_for_last_item(
                    work_order.name,
                    row,
                    run_log=run_log,
                )


def _manufacture_work_order(
    work_order_id,
    finished_serial_no,
    source_serial=None,
    output_batch_no=None,
    run_log=None,
):
    work_order = _get_work_order(work_order_id)
    source_warehouse = _manufacturing_source_warehouse(work_order)
    stock_entry = _new_stock_entry(
        work_order,
        purpose="Manufacture",
        from_warehouse=source_warehouse,
        to_warehouse=MAIN_STOCK_WAREHOUSE,
    )

    source_serial_assigned = False
    for row in stock_entry.items:
        if not row.s_warehouse:
            continue
        row.manual_source_warehouse_selection = 1
        row.s_warehouse = source_warehouse
        if source_serial and row.item_code == source_serial.item_code:
            _set_source_serial(row, source_serial, source_warehouse)
            source_serial_assigned = True

    if source_serial and not source_serial_assigned:
        raise ValidationError(
            _("BOM {0} does not consume serialized Item {1}.").format(
                work_order.bom_no,
                source_serial.item_code,
            )
        )

    finished_row = _finished_good_row(stock_entry, work_order)
    if cint(frappe.db.get_value("Item", finished_row.item_code, "has_serial_no")):
        if not finished_serial_no:
            raise ValidationError(_("Serial number is required for the final item."))
        if _get_serial_details(finished_serial_no):
            raise ValidationError(
                _("Serial No {0} already exists.").format(finished_serial_no)
            )
        finished_row.serial_no = finished_serial_no

    finished_row.manual_target_warehouse_selection = 1
    finished_row.t_warehouse = MAIN_STOCK_WAREHOUSE
    finished_row.auto_batch_no_generation = 0
    if cint(frappe.db.get_value("Item", finished_row.item_code, "has_batch_no")):
        if output_batch_no:
            batch = frappe.db.get_value(
                "Batch",
                output_batch_no,
                ["name", "item", "disabled"],
                as_dict=True,
            )
            if (
                not batch
                or batch.item != finished_row.item_code
                or cint(batch.disabled)
            ):
                raise ValidationError(
                    _("Output Batch {0} is invalid for Item {1}.").format(
                        output_batch_no,
                        finished_row.item_code,
                    )
                )
            finished_row.batch_no = batch.name
        else:
            finished_row.batch_no = assign_or_create_batch_for_last_item(
                work_order.name,
                finished_row,
                run_log=run_log,
            )

    _configure_output_rows(stock_entry, work_order, run_log=run_log)
    _log(run_log, "Manufacturing one unit for Work Order {0}.".format(work_order_id))
    return _submit_stock_entry(stock_entry, run_log=run_log)


def _apply_batch_inputs(stock_entry, batch_rows):
    required_quantities = _outgoing_item_quantities(stock_entry)
    batch_map = _build_batch_map(batch_rows, required_quantities)
    applied_items = set()

    for row in stock_entry.items:
        if not row.s_warehouse or row.item_code not in batch_map:
            continue
        batch = batch_map[row.item_code]
        if row.batch_no and row.batch_no != batch.name:
            raise ValidationError(
                _("Serial selection requires Batch {0}, not Batch {1}.").format(
                    row.batch_no,
                    batch.name,
                )
            )
        row.auto_batch_no_generation = 0
        row.batch_no = batch.name
        row.manual_source_warehouse_selection = 1
        row.s_warehouse = MAIN_STOCK_WAREHOUSE
        applied_items.add(row.item_code)

    if set(batch_map) != applied_items:
        raise ValidationError(
            _("One or more supplied Batches could not be assigned to a source row.")
        )


def start_work_order_final(
    work_order_id,
    serial_no_id=None,
    batch_no_id=None,
    run_log=None,
):
    """Manufacture the tested product while consuming its body serial."""
    work_order = _get_work_order(work_order_id)
    serial_details = _get_serial_details(serial_no_id)
    if not serial_details:
        raise ValidationError(
            _("Serial No {0} does not exist and cannot be consumed.").format(
                serial_no_id or ""
            )
        )
    _validate_serial_location(
        serial_details,
        serial_details.item_code,
        (MAIN_STOCK_WAREHOUSE,),
    )

    stock_entry = _new_stock_entry(
        work_order,
        purpose="Manufacture",
        from_warehouse=MAIN_STOCK_WAREHOUSE,
        to_warehouse=MAIN_STOCK_WAREHOUSE,
    )

    serial_row = None
    for row in stock_entry.items:
        if not row.s_warehouse:
            continue
        row.manual_source_warehouse_selection = 1
        row.s_warehouse = MAIN_STOCK_WAREHOUSE
        if row.item_code == serial_details.item_code:
            if serial_row:
                raise ValidationError(
                    _("More than one source row consumes serialized Item {0}.").format(
                        serial_details.item_code
                    )
                )
            _set_source_serial(row, serial_details, MAIN_STOCK_WAREHOUSE)
            serial_row = row

    if not serial_row:
        raise ValidationError(
            _("BOM {0} does not consume the Serial No Item {1}.").format(
                work_order.bom_no,
                serial_details.item_code,
            )
        )

    item_codes = list({row.item_code for row in stock_entry.items if row.s_warehouse})
    tracking = {
        row.name: cint(row.has_serial_no)
        for row in frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]} if item_codes else {"name": ""},
            fields=["name", "has_serial_no"],
        )
    }
    unassigned_serial_items = sorted(
        {
            row.item_code
            for row in stock_entry.items
            if row.s_warehouse
            and tracking.get(row.item_code)
            and not row.serial_no
        }
    )
    if unassigned_serial_items:
        raise ValidationError(
            _(
                "The final BOM has additional serialized component(s) requiring "
                "a Serial No: {0}."
            ).format(", ".join(unassigned_serial_items))
        )

    batch_rows = _parse_debug_batch_list(batch_no_id)
    _apply_batch_inputs(stock_entry, batch_rows)

    finished_row = _finished_good_row(stock_entry, work_order)
    finished_row.manual_target_warehouse_selection = 1
    finished_row.t_warehouse = MAIN_STOCK_WAREHOUSE
    if finished_row.meta.has_field("product_serial_no"):
        finished_row.product_serial_no = serial_no_id
    _configure_output_rows(stock_entry, work_order, run_log=run_log)

    _log(
        run_log,
        "Manufacturing final Item {0} from body Serial No {1}.".format(
            work_order.production_item,
            serial_no_id,
        ),
    )
    return _submit_stock_entry(stock_entry, run_log=run_log)


def _existing_serial_can_feed_source_work_order(serial_details, source_work_order):
    if not serial_details or serial_details.warehouse != MAIN_STOCK_WAREHOUSE:
        return False
    return serial_details.item_code in _serialized_component_codes(source_work_order.name)


def _execute_stock_entry_flow(
    source_work_order_id,
    serial_no_id,
    batch_no_id,
    run_log,
):
    source_work_order = _get_work_order(
        source_work_order_id,
        check_permission=True,
    )
    _validate_work_order_for_one_unit(source_work_order)
    batch_rows = _parse_debug_batch_list(batch_no_id)

    serial_no_id = cstr(serial_no_id).strip()
    if not serial_no_id:
        raise ValidationError(_("A finished body Serial No is required."))

    p202_flow = _work_order_uses_p202_body(source_work_order.name)
    if p202_flow:
        _validate_p202_finished_serial(serial_no_id)

    existing_serial = _get_serial_details(serial_no_id)
    if existing_serial:
        if _existing_serial_can_feed_source_work_order(
            existing_serial,
            source_work_order,
        ):
            _log(
                run_log,
                "Reusing available body Serial No {0} for the final Work Order.".format(
                    existing_serial.name
                ),
            )
            return start_work_order_final(
                source_work_order.name,
                serial_no_id,
                batch_rows,
                run_log=run_log,
            )
        raise ValidationError(
            _("Serial No {0} already exists in {1}.").format(
                existing_serial.name,
                existing_serial.warehouse or _("no warehouse"),
            )
        )

    p202_source_serial = None
    if p202_flow:
        p202_source_serial = _get_p202_source_serial(serial_no_id)
        _lock_serial(p202_source_serial.name)
        p202_source_serial = _get_serial_details(p202_source_serial.name)
        _validate_serial_location(
            p202_source_serial,
            P202_RAW_ITEM_CODE,
            (MAIN_STOCK_WAREHOUSE, WIP_WAREHOUSE),
        )
        _log(
            run_log,
            "Mapped {0} to source Serial No {1} in {2}.".format(
                serial_no_id,
                p202_source_serial.name,
                p202_source_serial.warehouse,
            ),
        )

    spare_production = cint(source_work_order.get("spare_part_production"))
    output_batch_no = source_work_order.get("spare_batch_no") if spare_production else None

    if (
        p202_source_serial
        and p202_source_serial.warehouse == WIP_WAREHOUSE
        and not spare_production
    ):
        target = _get_p202_wip_work_order(p202_source_serial)
        if not target:
            raise ValidationError(
                _(
                    "The WIP movement for Serial No {0} has no active 5D1000 "
                    "Work Order."
                ).format(p202_source_serial.name)
            )
        if (
            source_work_order.production_item == P202_SERIALIZED_ITEM_CODE
            and target["work_order_name"] != source_work_order.name
        ):
            raise ValidationError(
                _("Serial No {0} was transferred for Work Order {1}, not {2}.").format(
                    p202_source_serial.name,
                    target["work_order_name"],
                    source_work_order.name,
                )
            )
    elif spare_production or source_work_order.production_item == P202_SERIALIZED_ITEM_CODE:
        target = {
            "work_order_name": source_work_order.name,
            "production_item": source_work_order.production_item,
        }
    else:
        candidates = _find_serialized_work_orders(
            source_work_order.name,
            create_missing=True,
            run_log=run_log,
        )
        if p202_source_serial:
            target = _select_p202_work_order_for_main_stock(
                candidates,
                source_work_order=source_work_order.name,
                run_log=run_log,
            )
        else:
            target = candidates[0] if candidates else None

    if not target:
        raise ValidationError(
            _("No suitable serialized-component Work Order was found for {0}.").format(
                source_work_order.name
            )
        )

    target_work_order_id = target["work_order_name"]
    _lock_work_order(target_work_order_id)
    target_work_order = _get_work_order(target_work_order_id)
    _validate_work_order_for_one_unit(target_work_order)
    _log(run_log, "Selected target Work Order {0}.".format(target_work_order_id))

    raw_serial_in_wip = (
        p202_source_serial
        and p202_source_serial.warehouse == WIP_WAREHOUSE
    )
    if _needs_material_transfer(target_work_order) and not raw_serial_in_wip:
        source_serials = {}
        if p202_source_serial:
            source_serials[P202_RAW_ITEM_CODE] = p202_source_serial.name
        start_work_order(
            target_work_order.name,
            source_serials=source_serials,
            run_log=run_log,
        )
        if p202_source_serial:
            p202_source_serial = _get_serial_details(p202_source_serial.name)
    elif (
        p202_source_serial
        and p202_source_serial.warehouse == MAIN_STOCK_WAREHOUSE
        and _manufacturing_source_warehouse(target_work_order) != MAIN_STOCK_WAREHOUSE
    ):
        raise ValidationError(
            _(
                "Serial No {0} is still in Main Stock, but Work Order {1} "
                "does not require another material transfer."
            ).format(p202_source_serial.name, target_work_order.name)
        )

    body_stock_entry = _manufacture_work_order(
        target_work_order.name,
        finished_serial_no=serial_no_id,
        source_serial=p202_source_serial,
        output_batch_no=output_batch_no,
        run_log=run_log,
    )

    if not spare_production and target_work_order.name != source_work_order.name:
        start_work_order_final(
            source_work_order.name,
            serial_no_id=serial_no_id,
            batch_no_id=batch_rows,
            run_log=run_log,
        )
    return body_stock_entry


@frappe.whitelist()
def make_stock_entry(source_work_order_id, serial_no_id=None, batch_no_id=None):
    """Create and submit the Stock Entries required by one FFTest result."""
    run_log = _ExecutionLog(source_work_order_id)
    run_log.add(
        "Inputs: work_order={0}, serial={1}, batches={2}".format(
            source_work_order_id,
            serial_no_id,
            batch_no_id,
        )
    )
    try:
        result = _execute_stock_entry_flow(
            source_work_order_id,
            serial_no_id,
            batch_no_id,
            run_log,
        )
        run_log.add("FFTest stock flow completed successfully.")
        run_log.flush()
        return result
    except Exception as exc:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title="FFTest stock-entry flow failed",
        )
        run_log.add("ERROR: {0}".format(cstr(exc)))
        run_log.flush()
        return {
            "error": cstr(exc),
            "log_id": run_log.name,
        }


def _work_order_snapshot(work_order):
    fields = (
        "name",
        "production_item",
        "bom_no",
        "status",
        "docstatus",
        "qty",
        "produced_qty",
        "material_transferred_for_manufacturing",
        "wip_step",
        "wip_warehouse",
        "fg_warehouse",
        "spare_part_production",
        "parent_work_order",
    )
    return {field: work_order.get(field) for field in fields}


def _bom_snapshot(bom_no):
    bom = frappe.db.get_value(
        "BOM",
        bom_no,
        ["name", "item", "quantity", "is_active", "docstatus"],
        as_dict=True,
    )
    if not bom:
        return None

    items = frappe.get_all(
        "BOM Item",
        filters={"parent": bom_no},
        fields=["idx", "item_code", "qty", "stock_uom"],
        order_by="idx ASC",
    )
    item_codes = [row.item_code for row in items]
    tracking = {
        row.name: row
        for row in frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]} if item_codes else {"name": ""},
            fields=["name", "has_serial_no", "has_batch_no"],
        )
    }
    return {
        "name": bom.name,
        "item": bom.item,
        "quantity": bom.quantity,
        "is_active": bom.is_active,
        "docstatus": bom.docstatus,
        "items": [
            {
                "item_code": row.item_code,
                "qty": row.qty,
                "stock_uom": row.stock_uom,
                "has_serial_no": cint(
                    tracking.get(row.item_code).has_serial_no
                    if tracking.get(row.item_code)
                    else 0
                ),
                "has_batch_no": cint(
                    tracking.get(row.item_code).has_batch_no
                    if tracking.get(row.item_code)
                    else 0
                ),
            }
            for row in items
        ],
    }


def _add_report_step(
    report,
    label,
    status="ok",
    doctype=None,
    name=None,
    details=None,
):
    report["steps"].append(
        {
            "label": label,
            "status": status,
            "doctype": doctype,
            "name": name,
            "details": details or {},
        }
    )


def _report_error(report, message):
    report["errors"].append(cstr(message))


def _report_warning(report, message):
    report["warnings"].append(cstr(message))


def _debug_target_work_order(source_work_order, source_serial):
    if source_serial and source_serial.warehouse == WIP_WAREHOUSE:
        return _get_p202_wip_work_order(source_serial)
    if source_work_order.production_item == P202_SERIALIZED_ITEM_CODE:
        return {
            "work_order_name": source_work_order.name,
            "production_item": source_work_order.production_item,
        }

    candidates = _find_serialized_work_orders(
        source_work_order.name,
        create_missing=False,
    )
    for candidate in candidates:
        if candidate["production_item"] != P202_SERIALIZED_ITEM_CODE:
            continue
        work_order = frappe.db.get_value(
            "Work Order",
            candidate["work_order_name"],
            [
                "status",
                "qty",
                "produced_qty",
                "material_transferred_for_manufacturing",
            ],
            as_dict=True,
        )
        if _work_order_has_capacity(work_order, require_transfer_capacity=True):
            return candidate
    return None


@frappe.whitelist()
def debug_stock_entry_flow(source_work_order_id, serial_no_id=None, batch_no_id=None):
    """Return a read-only preview of the DocTypes used by the FFTest flow."""
    if frappe.session.user == "Guest":
        raise frappe.PermissionError(
            _("Login is required to use the FFTest debug tool.")
        )

    report = {
        "mode": "read_only",
        "inputs": {
            "source_work_order_id": source_work_order_id,
            "serial_no_id": serial_no_id,
            "batch_no_id": batch_no_id,
        },
        "ok": False,
        "can_execute": bool(frappe.has_permission("Stock Entry", "create")),
        "steps": [],
        "errors": [],
        "warnings": [],
        "planned_documents": [],
        "related_stock_entries": [],
    }

    try:
        source_work_order = _get_work_order(
            source_work_order_id,
            check_permission=True,
        )
    except Exception as exc:
        _report_error(report, exc)
        _add_report_step(
            report,
            "Source Work Order",
            "error",
            "Work Order",
            source_work_order_id,
        )
        return report

    report["source_work_order"] = _work_order_snapshot(source_work_order)
    source_wo_ok = (
        source_work_order.docstatus == 1
        and flt(source_work_order.produced_qty) + 1 <= flt(source_work_order.qty)
    )
    _add_report_step(
        report,
        "Source Work Order",
        "ok" if source_wo_ok else "error",
        "Work Order",
        source_work_order.name,
        {
            "production_item": source_work_order.production_item,
            "status": source_work_order.status,
            "qty": source_work_order.qty,
            "produced_qty": source_work_order.produced_qty,
        },
    )
    if source_work_order.docstatus != 1:
        _report_error(report, _("Source Work Order must be submitted."))
    if flt(source_work_order.produced_qty) + 1 > flt(source_work_order.qty):
        _report_error(report, _("Source Work Order cannot produce another unit."))

    source_bom = _bom_snapshot(source_work_order.bom_no)
    report["source_bom"] = source_bom
    source_bom_ok = bool(
        source_bom
        and source_bom["docstatus"] == 1
        and cint(source_bom["is_active"])
    )
    _add_report_step(
        report,
        "Source BOM",
        "ok" if source_bom_ok else "error",
        "BOM",
        source_work_order.bom_no,
        {"component_count": len(source_bom["items"]) if source_bom else 0},
    )
    if not source_bom_ok:
        _report_error(report, _("Source BOM must exist, be submitted and active."))

    try:
        batch_rows = _parse_debug_batch_list(batch_no_id)
        report["batches"], batch_errors = _inspect_batch_inputs(batch_rows)
        supplied_batch_items = {
            row["item"]
            for row in report["batches"]
            if row.get("exists") and row.get("item")
        }
        required_batch_items = {
            row["item_code"]
            for row in (source_bom["items"] if source_bom else [])
            if row["has_batch_no"] and not row["has_serial_no"]
        }
        missing_batch_items = sorted(required_batch_items - supplied_batch_items)
        if missing_batch_items:
            batch_errors.append(
                _("Batch selection is required for source Item(s): {0}.").format(
                    ", ".join(missing_batch_items)
                )
            )
        for error in batch_errors:
            _report_error(report, error)
        _add_report_step(
            report,
            "Batch inputs",
            "ok" if not batch_errors else "error",
            details={"count": len(batch_rows)},
        )
    except ValidationError as exc:
        batch_rows = []
        report["batches"] = []
        _report_error(report, exc)
        _add_report_step(report, "Batch inputs", "error")

    serial_no_id = cstr(serial_no_id).strip()
    p202_flow = _work_order_uses_p202_body(source_work_order.name)
    serial_flow = {
        "is_p202_flow": p202_flow,
        "finished_serial": serial_no_id,
        "action": None,
    }
    report["serial_flow"] = serial_flow

    existing_serial = _get_serial_details(serial_no_id)
    source_serial = None
    target = None

    if not serial_no_id:
        _report_error(report, _("A finished body Serial No is required."))
        _add_report_step(report, "Body Serial No", "error", "Serial No")
    elif p202_flow:
        try:
            _validate_p202_finished_serial(serial_no_id)
            _add_report_step(
                report,
                "5D1000 serial pattern",
                "ok",
                "Serial No",
                serial_no_id,
            )
        except ValidationError as exc:
            _report_error(report, exc)
            _add_report_step(
                report,
                "5D1000 serial pattern",
                "error",
                "Serial No",
                serial_no_id,
            )

    if existing_serial:
        serial_flow["existing_finished_serial"] = dict(existing_serial)
        if _existing_serial_can_feed_source_work_order(
            existing_serial,
            source_work_order,
        ):
            serial_flow["action"] = "reuse_existing_serialized_body"
            _add_report_step(
                report,
                "Existing serialized body",
                "ok",
                "Serial No",
                existing_serial.name,
                {
                    "item_code": existing_serial.item_code,
                    "warehouse": existing_serial.warehouse,
                },
            )
        else:
            _report_error(
                report,
                _("Existing Serial No {0} cannot feed this Work Order.").format(
                    existing_serial.name
                ),
            )
            _add_report_step(
                report,
                "Existing serialized body",
                "error",
                "Serial No",
                existing_serial.name,
                {
                    "item_code": existing_serial.item_code,
                    "warehouse": existing_serial.warehouse,
                },
            )
    elif p202_flow and serial_no_id:
        try:
            source_serial = _get_p202_source_serial(serial_no_id)
            serial_flow["source_serial"] = dict(source_serial)
            serial_flow["action"] = "manufacture_5D1000"
            location_ok = source_serial.warehouse in (
                MAIN_STOCK_WAREHOUSE,
                WIP_WAREHOUSE,
            )
            _add_report_step(
                report,
                "Mapped 5D0000 serial",
                "ok" if location_ok else "error",
                "Serial No",
                source_serial.name,
                {
                    "warehouse": source_serial.warehouse,
                    "batch_no": source_serial.batch_no,
                },
            )
            if not location_ok:
                _report_error(
                    report,
                    _("Mapped Serial No must be in Main Stock or WIP."),
                )

            source_batch = (
                frappe.db.get_value(
                    "Batch",
                    source_serial.batch_no,
                    ["name", "item", "disabled", "work_order"],
                    as_dict=True,
                )
                if source_serial.batch_no
                else None
            )
            serial_flow["source_batch"] = dict(source_batch) if source_batch else None
            batch_ok = bool(
                source_batch
                and source_batch.item == P202_RAW_ITEM_CODE
                and not cint(source_batch.disabled)
            )
            _add_report_step(
                report,
                "Mapped 5D0000 Batch",
                "ok" if batch_ok else "error",
                "Batch",
                source_serial.batch_no,
                dict(source_batch) if source_batch else {},
            )
            if not batch_ok:
                _report_error(report, _("Mapped 5D0000 Batch is missing or invalid."))

            target = _debug_target_work_order(source_work_order, source_serial)
            if (
                target
                and source_work_order.production_item == P202_SERIALIZED_ITEM_CODE
                and target["work_order_name"] != source_work_order.name
            ):
                _report_error(
                    report,
                    _("Mapped Serial No was transferred for Work Order {0}, not {1}.").format(
                        target["work_order_name"],
                        source_work_order.name,
                    ),
                )
            if not target and source_serial.warehouse == MAIN_STOCK_WAREHOUSE:
                serial_flow["target_work_order_action"] = "create_5D1000_work_order"
                _report_warning(
                    report,
                    _("No available 5D1000 Work Order exists; execution will create one."),
                )
            elif not target:
                _report_error(
                    report,
                    _("The WIP serial has no active 5D1000 Work Order."),
                )
        except ValidationError as exc:
            _report_error(report, exc)
            _add_report_step(
                report,
                "Mapped 5D0000 serial",
                "error",
                "Serial No",
            )
    elif not existing_serial and serial_no_id:
        serial_flow["action"] = "manufacture_serialized_body"
        candidates = _find_serialized_work_orders(
            source_work_order.name,
            create_missing=False,
        )
        target = candidates[0] if candidates else None
        if not target:
            _report_warning(
                report,
                _("No serialized-component Work Order exists; execution will create one."),
            )

    if target:
        serial_flow["target_work_order"] = target
        target_doc = _get_work_order(target["work_order_name"])
        report["target_work_order"] = _work_order_snapshot(target_doc)
        target_ok = (
            target_doc.docstatus == 1
            and flt(target_doc.produced_qty) + 1 <= flt(target_doc.qty)
        )
        _add_report_step(
            report,
            "Serialized-body Work Order",
            "ok" if target_ok else "error",
            "Work Order",
            target_doc.name,
            {
                "production_item": target_doc.production_item,
                "status": target_doc.status,
                "qty": target_doc.qty,
                "produced_qty": target_doc.produced_qty,
                "transferred_qty": target_doc.material_transferred_for_manufacturing,
            },
        )
        if not target_ok:
            _report_error(report, _("Target Work Order cannot produce another unit."))

        target_bom = _bom_snapshot(target_doc.bom_no)
        report["target_bom"] = target_bom
        target_bom_ok = bool(
            target_bom
            and target_bom["docstatus"] == 1
            and cint(target_bom["is_active"])
        )
        _add_report_step(
            report,
            "Serialized-body BOM",
            "ok" if target_bom_ok else "error",
            "BOM",
            target_doc.bom_no,
            {"component_count": len(target_bom["items"]) if target_bom else 0},
        )
        if not target_bom_ok:
            _report_error(report, _("Target BOM must be submitted and active."))

    if source_serial and not existing_serial:
        planned_target = target["work_order_name"] if target else "new Work Order"
        if source_serial.warehouse == MAIN_STOCK_WAREHOUSE:
            report["planned_documents"].append(
                {
                    "doctype": "Stock Entry",
                    "purpose": "Material Transfer for Manufacture",
                    "work_order": planned_target,
                    "serial_no": source_serial.name,
                    "batch_no": source_serial.batch_no,
                }
            )
        report["planned_documents"].append(
            {
                "doctype": "Stock Entry",
                "purpose": "Manufacture",
                "work_order": planned_target,
                "consume_item": P202_RAW_ITEM_CODE,
                "consume_serial": source_serial.name,
                "produce_item": P202_SERIALIZED_ITEM_CODE,
                "produce_serial": serial_no_id,
            }
        )
    elif not existing_serial and serial_no_id:
        report["planned_documents"].append(
            {
                "doctype": "Stock Entry",
                "purpose": "Manufacture",
                "work_order": target["work_order_name"] if target else "new Work Order",
                "produce_serial": serial_no_id,
            }
        )

    target_name = target["work_order_name"] if target else None
    if existing_serial or (target_name and target_name != source_work_order.name):
        report["planned_documents"].append(
            {
                "doctype": "Stock Entry",
                "purpose": "Manufacture",
                "work_order": source_work_order.name,
                "consume_serial": serial_no_id,
                "produce_item": source_work_order.production_item,
            }
        )

    related_work_orders = [source_work_order.name]
    if target_name and target_name not in related_work_orders:
        related_work_orders.append(target_name)
    report["related_stock_entries"] = [
        dict(row)
        for row in frappe.get_all(
            "Stock Entry",
            filters={"work_order": ["in", related_work_orders]},
            fields=[
                "name",
                "work_order",
                "purpose",
                "docstatus",
                "posting_date",
                "posting_time",
            ],
            order_by="creation DESC",
            limit_page_length=20,
        )
    ]
    _add_report_step(
        report,
        "Related Stock Entries",
        "ok",
        "Stock Entry",
        details={"count": len(report["related_stock_entries"])},
    )

    report["ok"] = not report["errors"]
    return report


def create_new_wo(
    item_code="520100",
    sales_order="",
    qty=1,
    parent_work_order=None,
    company=None,
    run_log=None,
):
    """Create and submit a one-item Work Order for a serialized component."""
    bom_no = get_default_bom(item_code)
    _get_valid_bom(bom_no)

    work_order = frappe.new_doc("Work Order")
    work_order.production_item = item_code
    work_order.bom_no = bom_no
    work_order.qty = flt(qty)
    work_order.company = company or COMPANY
    work_order.sales_order = sales_order or ""
    work_order.fg_warehouse = MAIN_STOCK_WAREHOUSE
    if work_order.meta.has_field("parent_work_order"):
        work_order.parent_work_order = parent_work_order
    if work_order.meta.has_field("simple_description"):
        work_order.simple_description = (
            "Auto-generated serialized-component Work Order from FFTest."
        )

    work_order.insert()
    if hasattr(work_order, "set_work_order_operations"):
        work_order.set_work_order_operations()
        work_order.save()
    work_order.submit()
    _log(
        run_log,
        "Created Work Order {0} for Item {1}.".format(
            work_order.name,
            item_code,
        ),
    )
    return work_order


def create_batch_name(item_code=None):
    """Generate an internal production Batch name."""
    return make_internal_production_batch_id()


def update_rate_and_availability_ste(stock_entry_doc, method=None):
    """Compatibility hook for the custom Stock Entry rate calculation."""
    get_stock_and_rate_override(stock_entry_doc, method=method)


def create_log_entry(message, category=None):
    """Create an FFTest Log Entry and return its name."""
    log_doc = frappe.get_doc(
        {
            "doctype": "Log Entry",
            "timestamp": now_datetime(),
            "category": category,
            "message": cstr(message),
            "reference_name": "FFTest Stock Entry: {0}".format(now_datetime()),
        }
    )
    log_doc.insert(ignore_permissions=True)
    # Preserve the start record even when the later stock transaction rolls back.
    frappe.db.commit()
    return log_doc.name


@frappe.whitelist()
def fetch_sn(product_id):
    """Return the next numeric Serial No suggestion for an Item."""
    product_id = cstr(product_id).strip()
    if not product_id or not frappe.db.exists("Item", product_id):
        raise ValidationError(_("Item {0} does not exist.").format(product_id))
    frappe.get_doc("Item", product_id).check_permission("read")

    highest_serial = frappe.db.sql(
        """
        SELECT MAX(CAST(serial_no AS UNSIGNED))
        FROM `tabSerial No`
        WHERE item_code = %s
          AND serial_no REGEXP '^[0-9]+$'
        """,
        (product_id,),
    )[0][0]
    return {"sn": cstr(cint(highest_serial) + 1)}


@frappe.whitelist()
def get_test_info(input_value):
    """Return client, motor, valve-head and syringe references as CSV."""
    input_value = cstr(input_value).strip()
    if not input_value:
        return "N/A,N/A,N/A,N/A"

    if frappe.db.exists("Work Order", input_value):
        work_order = _get_work_order(input_value, check_permission=True)
        item_code = work_order.production_item
        client_name = work_order.get("custo_name") or "N/A"
    else:
        item_code = input_value
        client_name = "N/A"

    if not frappe.db.exists("Item", item_code):
        return "N/A,N/A,N/A,N/A"
    item = frappe.get_doc("Item", item_code)
    item.check_permission("read")

    if item.item_type == "Finished Good":
        if not item.default_bom or not frappe.db.exists("BOM", item.default_bom):
            return "{0},N/A,N/A,N/A".format(client_name)

        references = {
            "motor": "N/A",
            "valve_head": "N/A",
            "syringe": "N/A",
        }
        for bom_item in frappe.get_all(
            "BOM Item",
            filters={"parent": item.default_bom},
            fields=["item_code"],
            order_by="idx ASC",
        ):
            reference = frappe.db.get_value(
                "Item",
                bom_item.item_code,
                "reference_code",
            ) or "N/A"
            if bom_item.item_code.startswith("5"):
                references["motor"] = reference
            elif bom_item.item_code.startswith("3"):
                references["valve_head"] = reference
            elif bom_item.item_code.startswith("70"):
                references["syringe"] = reference
        return "{0},{1},{2},{3}".format(
            client_name,
            references["motor"],
            references["valve_head"],
            references["syringe"],
        )

    if item.item_group == "Valve Head":
        valve_head = item.get("reference_code") or "N/A"
        return "{0},N/A,{1},N/A".format(
            "SPARE" if client_name == "N/A" else client_name,
            valve_head,
        )
    return "N/A,N/A,N/A,N/A"
