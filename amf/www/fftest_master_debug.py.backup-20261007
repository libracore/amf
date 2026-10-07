import json
import frappe
from frappe import _, ValidationError
from frappe.utils import cstr, flt, now_datetime
from amf.amf.utils.work_order_creation import get_default_bom
from amf.amf.utils.utilities import update_log_entry
from amf.amf.utils.stock_entry import get_stock_and_rate_override
from amf.amf.utils.batch_naming import make_internal_production_batch_id


P202_RAW_ITEM_CODE = "5D0000"
P202_SERIALIZED_ITEM_CODE = "5D1000"
P202_SERIAL_PREFIX = "P202-O"
P202_SERIAL_DIGITS = 8
MAIN_STOCK_WAREHOUSE = "Main Stock - AMF21"
WIP_WAREHOUSE = "Work In Progress - AMF21"


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
    expected_length = len(P202_SERIAL_PREFIX) + P202_SERIAL_DIGITS
    suffix = finished_serial_no[len(P202_SERIAL_PREFIX):]
    if (
        not finished_serial_no.startswith(P202_SERIAL_PREFIX)
        or len(finished_serial_no) != expected_length
        or not suffix.isdigit()
    ):
        raise ValidationError(
            _("5D1000 Serial No must use the format {0}########.").format(
                P202_SERIAL_PREFIX
            )
        )
    return finished_serial_no


def _get_serial_details(serial_no):
    return frappe.db.get_value(
        "Serial No",
        serial_no,
        [
            "name",
            "serial_no",
            "item_code",
            "warehouse",
            "batch_no",
            "purchase_document_no",
            "delivery_document_no",
        ],
        as_dict=True,
    )


def _get_p202_source_serial(finished_serial_no):
    """Resolve the existing 5D0000 serial whose padded value forms 5D1000."""
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
    if frappe.db.get_value("Item", row.item_code, "has_batch_no") == 1:
        if not serial_details.batch_no:
            raise ValidationError(
                _("Serial No {0} has no Batch No.").format(serial_details.name)
            )
        row.auto_batch_no_generation = 0
        row.batch_no = serial_details.batch_no


def _get_p202_wip_work_order(serial_details):
    """Return the active 5D1000 WO that received this 5D0000 serial into WIP."""
    if (
        not serial_details
        or serial_details.get("warehouse") != WIP_WAREHOUSE
        or not serial_details.get("purchase_document_no")
    ):
        return None

    work_order_id = frappe.db.get_value(
        "Stock Entry",
        {
            "name": serial_details.get("purchase_document_no"),
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
        ["name", "production_item", "status", "qty", "produced_qty"],
        as_dict=True,
    )
    if (
        not work_order
        or work_order.production_item != P202_SERIALIZED_ITEM_CODE
        or work_order.status not in ("Not Started", "In Process")
        or flt(work_order.produced_qty) >= flt(work_order.qty)
    ):
        return None

    return {
        "work_order_name": work_order.name,
        "production_item": work_order.production_item,
    }


def _select_p202_work_order_for_main_stock(existing_work_orders):
    """Select a 5D1000 WO that can still receive one mapped 5D0000 serial."""
    for candidate in existing_work_orders or []:
        work_order = frappe.db.get_value(
            "Work Order",
            candidate["work_order_name"],
            [
                "name",
                "production_item",
                "qty",
                "produced_qty",
                "material_transferred_for_manufacturing",
            ],
            as_dict=True,
        )
        if (
            work_order
            and work_order.production_item == P202_SERIALIZED_ITEM_CODE
            and flt(work_order.produced_qty) < flt(work_order.qty)
            and flt(work_order.material_transferred_for_manufacturing)
            < flt(work_order.qty)
        ):
            return {
                "work_order_name": work_order.name,
                "production_item": work_order.production_item,
            }

    work_order = create_new_wo(P202_SERIALIZED_ITEM_CODE)
    return {
        "work_order_name": work_order.name,
        "production_item": work_order.production_item,
    }


def _parse_debug_batch_list(batch_no_id):
    if not batch_no_id:
        return []
    if isinstance(batch_no_id, str):
        try:
            batch_no_id = json.loads(batch_no_id)
        except Exception as e:
            raise ValidationError(_("Invalid batch_list JSON: {0}").format(str(e)))
    if not isinstance(batch_no_id, list):
        raise ValidationError(_("batch_list must be a JSON array."))
    return batch_no_id


@frappe.whitelist()
def debug_stock_entry_flow(source_work_order_id, serial_no_id=None, batch_no_id=None):
    """Build a read-only report of the FFTest DocType and Stock Entry flow."""
    if frappe.session.user == "Guest":
        raise frappe.PermissionError(_("Login is required to use the FFTest debug tool."))

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

    def add_step(label, status="ok", doctype=None, name=None, details=None):
        report["steps"].append({
            "label": label,
            "status": status,
            "doctype": doctype,
            "name": name,
            "details": details or {},
        })

    def add_error(message):
        report["errors"].append(cstr(message))

    def add_warning(message):
        report["warnings"].append(cstr(message))

    work_order = frappe.db.get_value(
        "Work Order",
        source_work_order_id,
        [
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
        ],
        as_dict=True,
    )
    if not work_order:
        add_error(_("Work Order {0} does not exist.").format(source_work_order_id))
        add_step("Source Work Order", "error", "Work Order", source_work_order_id)
        return report

    work_order_doc = frappe.get_doc("Work Order", source_work_order_id)
    work_order_doc.check_permission("read")
    report["source_work_order"] = dict(work_order)
    add_step(
        "Source Work Order",
        "ok" if work_order.docstatus == 1 else "warning",
        "Work Order",
        work_order.name,
        {
            "production_item": work_order.production_item,
            "status": work_order.status,
            "qty": work_order.qty,
            "produced_qty": work_order.produced_qty,
        },
    )
    if work_order.docstatus != 1:
        add_error(_("Source Work Order must be submitted."))
    if flt(work_order.produced_qty) >= flt(work_order.qty):
        add_error(_("Source Work Order has no remaining quantity to produce."))

    if not work_order.bom_no or not frappe.db.exists("BOM", work_order.bom_no):
        add_error(_("BOM {0} does not exist.").format(work_order.bom_no or ""))
        add_step("Source BOM", "error", "BOM", work_order.bom_no)
        return report

    bom = frappe.db.get_value(
        "BOM",
        work_order.bom_no,
        ["name", "item", "quantity", "is_active", "docstatus"],
        as_dict=True,
    )
    bom_items = frappe.get_all(
        "BOM Item",
        filters={"parent": work_order.bom_no},
        fields=["idx", "item_code", "qty", "stock_uom"],
        order_by="idx asc",
    )
    item_codes = [row.item_code for row in bom_items]
    item_tracking_rows = frappe.get_all(
        "Item",
        filters={"name": ["in", item_codes]} if item_codes else {"name": ""},
        fields=["name", "has_serial_no", "has_batch_no"],
    )
    tracking_by_item = {row.name: row for row in item_tracking_rows}
    report["source_bom"] = {
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
                "has_serial_no": (
                    tracking_by_item.get(row.item_code).has_serial_no
                    if tracking_by_item.get(row.item_code)
                    else 0
                ),
                "has_batch_no": (
                    tracking_by_item.get(row.item_code).has_batch_no
                    if tracking_by_item.get(row.item_code)
                    else 0
                ),
            }
            for row in bom_items
        ],
    }
    add_step(
        "Source BOM",
        "ok" if bom.docstatus == 1 and bom.is_active else "error",
        "BOM",
        bom.name,
        {"item": bom.item, "component_count": len(bom_items)},
    )
    if bom.docstatus != 1 or not bom.is_active:
        add_error(_("Source BOM must be submitted and active."))

    try:
        batch_rows = _parse_debug_batch_list(batch_no_id)
    except ValidationError as e:
        batch_rows = []
        add_error(str(e))
    report["batches"] = []
    for batch_row in batch_rows:
        batch_no = batch_row.get("batch_no") if isinstance(batch_row, dict) else None
        batch = frappe.db.get_value(
            "Batch",
            batch_no,
            ["name", "item", "disabled"],
            as_dict=True,
        ) if batch_no else None
        batch_result = {
            "input": batch_row,
            "exists": bool(batch),
            "name": batch.name if batch else batch_no,
            "item": batch.item if batch else None,
            "disabled": batch.disabled if batch else None,
        }
        report["batches"].append(batch_result)
        if not batch:
            add_error(_("Batch {0} does not exist.").format(batch_no or ""))
        elif batch.disabled:
            add_error(_("Batch {0} is disabled.").format(batch.name))
    add_step(
        "Batch inputs",
        "ok" if len(report["batches"]) == len(batch_rows) else "error",
        details={"count": len(batch_rows)},
    )

    p202_flow = _work_order_uses_p202_body(source_work_order_id)
    report["serial_flow"] = {
        "is_p202_flow": p202_flow,
        "finished_serial": serial_no_id,
        "action": None,
    }
    existing_finished_serial = _get_serial_details(serial_no_id) if serial_no_id else None
    target_work_order = None
    source_serial = None

    if p202_flow:
        try:
            _validate_p202_finished_serial(serial_no_id)
            add_step(
                "5D1000 serial pattern",
                "ok",
                "Serial No",
                serial_no_id,
            )
        except ValidationError as e:
            add_error(str(e))
            add_step("5D1000 serial pattern", "error", "Serial No", serial_no_id)

        if existing_finished_serial:
            report["serial_flow"]["existing_finished_serial"] = dict(
                existing_finished_serial
            )
            if (
                existing_finished_serial.item_code == P202_SERIALIZED_ITEM_CODE
                and existing_finished_serial.warehouse == MAIN_STOCK_WAREHOUSE
            ):
                report["serial_flow"]["action"] = "reuse_existing_5D1000"
                add_step(
                    "Existing serialized body",
                    "ok",
                    "Serial No",
                    existing_finished_serial.name,
                    {"warehouse": existing_finished_serial.warehouse},
                )
            else:
                add_error(
                    _("Existing serial {0} is not an available 5D1000 in Main Stock.").format(
                        existing_finished_serial.name
                    )
                )
                add_step(
                    "Existing serialized body",
                    "error",
                    "Serial No",
                    existing_finished_serial.name,
                    {
                        "item_code": existing_finished_serial.item_code,
                        "warehouse": existing_finished_serial.warehouse,
                        "delivery_document_no": existing_finished_serial.delivery_document_no,
                    },
                )
        elif serial_no_id:
            try:
                source_serial = _get_p202_source_serial(serial_no_id)
                report["serial_flow"]["source_serial"] = dict(source_serial)
                report["serial_flow"]["action"] = "manufacture_5D1000"
                location_status = (
                    "ok"
                    if source_serial.warehouse in (MAIN_STOCK_WAREHOUSE, WIP_WAREHOUSE)
                    else "error"
                )
                add_step(
                    "Mapped 5D0000 serial",
                    location_status,
                    "Serial No",
                    source_serial.name,
                    {
                        "warehouse": source_serial.warehouse,
                        "batch_no": source_serial.batch_no,
                    },
                )
                source_batch = frappe.db.get_value(
                    "Batch",
                    source_serial.batch_no,
                    ["name", "item", "disabled", "work_order"],
                    as_dict=True,
                ) if source_serial.batch_no else None
                report["serial_flow"]["source_batch"] = (
                    dict(source_batch) if source_batch else None
                )
                if not source_batch:
                    add_error(
                        _("Mapped Serial No {0} has no valid Batch.").format(
                            source_serial.name
                        )
                    )
                    add_step("Mapped 5D0000 Batch", "error", "Batch")
                else:
                    batch_status = (
                        "ok"
                        if source_batch.item == P202_RAW_ITEM_CODE
                        and not source_batch.disabled
                        else "error"
                    )
                    add_step(
                        "Mapped 5D0000 Batch",
                        batch_status,
                        "Batch",
                        source_batch.name,
                        {
                            "item": source_batch.item,
                            "disabled": source_batch.disabled,
                            "work_order": source_batch.work_order,
                        },
                    )
                    if source_batch.item != P202_RAW_ITEM_CODE:
                        add_error(
                            _("Batch {0} belongs to Item {1}, not 5D0000.").format(
                                source_batch.name,
                                source_batch.item,
                            )
                        )
                    if source_batch.disabled:
                        add_error(_("Batch {0} is disabled.").format(source_batch.name))
                if location_status == "error":
                    add_error(
                        _("Mapped 5D0000 serial is in {0}; it must be in Main Stock or WIP.").format(
                            source_serial.warehouse or _("no warehouse")
                        )
                    )
            except ValidationError as e:
                add_error(str(e))
                add_step("Mapped 5D0000 serial", "error", "Serial No")

        if source_serial and source_serial.warehouse == WIP_WAREHOUSE:
            target_work_order = _get_p202_wip_work_order(source_serial)
        elif source_serial and source_serial.warehouse == MAIN_STOCK_WAREHOUSE:
            candidates = frappe.get_all(
                "Work Order",
                filters={
                    "production_item": P202_SERIALIZED_ITEM_CODE,
                    "status": ["in", ["Not Started", "In Process"]],
                },
                fields=[
                    "name",
                    "production_item",
                    "status",
                    "qty",
                    "produced_qty",
                    "material_transferred_for_manufacturing",
                    "parent_work_order",
                ],
                order_by="creation asc",
            )
            report["serial_flow"]["candidate_body_work_orders"] = [
                dict(candidate) for candidate in candidates
            ]
            for candidate in candidates:
                if (
                    flt(candidate.produced_qty) < flt(candidate.qty)
                    and flt(candidate.material_transferred_for_manufacturing)
                    < flt(candidate.qty)
                ):
                    target_work_order = {
                        "work_order_name": candidate.name,
                        "production_item": candidate.production_item,
                    }
                    break

        if source_serial and not target_work_order:
            if source_serial.warehouse == MAIN_STOCK_WAREHOUSE:
                add_warning(_("No transferable 5D1000 Work Order exists; production would create one."))
                report["serial_flow"]["target_work_order_action"] = "create_5D1000_work_order"
            elif source_serial.warehouse == WIP_WAREHOUSE:
                add_error(_("The WIP movement for the mapped 5D0000 serial has no active 5D1000 Work Order."))

        if target_work_order:
            report["serial_flow"]["target_work_order"] = target_work_order
            target_work_order_details = frappe.db.get_value(
                "Work Order",
                target_work_order["work_order_name"],
                [
                    "name",
                    "production_item",
                    "bom_no",
                    "status",
                    "docstatus",
                    "qty",
                    "produced_qty",
                    "material_transferred_for_manufacturing",
                    "wip_warehouse",
                    "fg_warehouse",
                    "parent_work_order",
                ],
                as_dict=True,
            )
            report["target_work_order"] = dict(target_work_order_details)
            add_step(
                "5D1000 Work Order",
                "ok" if target_work_order_details.docstatus == 1 else "error",
                "Work Order",
                target_work_order["work_order_name"],
                {
                    "status": target_work_order_details.status,
                    "qty": target_work_order_details.qty,
                    "produced_qty": target_work_order_details.produced_qty,
                    "transferred_qty": target_work_order_details.material_transferred_for_manufacturing,
                },
            )
            target_bom = frappe.db.get_value(
                "BOM",
                target_work_order_details.bom_no,
                ["name", "item", "quantity", "is_active", "docstatus"],
                as_dict=True,
            )
            target_bom_items = frappe.get_all(
                "BOM Item",
                filters={"parent": target_work_order_details.bom_no},
                fields=["idx", "item_code", "qty", "stock_uom"],
                order_by="idx asc",
            )
            report["target_bom"] = {
                "name": target_bom.name if target_bom else target_work_order_details.bom_no,
                "item": target_bom.item if target_bom else None,
                "quantity": target_bom.quantity if target_bom else None,
                "is_active": target_bom.is_active if target_bom else None,
                "docstatus": target_bom.docstatus if target_bom else None,
                "items": [dict(row) for row in target_bom_items],
            }
            target_bom_ok = bool(
                target_bom and target_bom.docstatus == 1 and target_bom.is_active
            )
            add_step(
                "5D1000 BOM",
                "ok" if target_bom_ok else "error",
                "BOM",
                target_work_order_details.bom_no,
                {"component_count": len(target_bom_items)},
            )
            if not target_bom_ok:
                add_error(_("The 5D1000 Work Order BOM is not submitted and active."))
    else:
        if existing_finished_serial:
            add_error(
                _("Serial No {0} already exists in {1}.").format(
                    existing_finished_serial.name,
                    existing_finished_serial.purchase_document_no or _("the database"),
                )
            )
        add_step(
            "Standard serialized-body flow",
            "ok" if serial_no_id and not existing_finished_serial else "error",
            "Serial No",
            serial_no_id,
        )

    if p202_flow and not existing_finished_serial and source_serial:
        if source_serial.warehouse == MAIN_STOCK_WAREHOUSE:
            report["planned_documents"].append({
                "doctype": "Stock Entry",
                "purpose": "Material Transfer for Manufacture",
                "work_order": (
                    target_work_order["work_order_name"]
                    if target_work_order
                    else "new 5D1000 Work Order"
                ),
                "serial_no": source_serial.name,
                "batch_no": source_serial.batch_no,
            })
        report["planned_documents"].append({
            "doctype": "Stock Entry",
            "purpose": "Manufacture",
            "work_order": (
                target_work_order["work_order_name"]
                if target_work_order
                else "new 5D1000 Work Order"
            ),
            "consume_item": P202_RAW_ITEM_CODE,
            "consume_serial": source_serial.name,
            "produce_item": P202_SERIALIZED_ITEM_CODE,
            "produce_serial": serial_no_id,
        })
    if not work_order.production_item.startswith("5"):
        report["planned_documents"].append({
            "doctype": "Stock Entry",
            "purpose": "Manufacture",
            "work_order": work_order.name,
            "consume_serial": serial_no_id,
            "produce_item": work_order.production_item,
        })

    related_work_orders = [work_order.name]
    if target_work_order:
        related_work_orders.append(target_work_order["work_order_name"])
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
            order_by="creation desc",
            limit_page_length=20,
        )
    ]
    add_step(
        "Related Stock Entries",
        "ok",
        "Stock Entry",
        details={"count": len(report["related_stock_entries"])},
    )

    report["ok"] = not report["errors"]
    return report


@frappe.whitelist()
def make_stock_entry(source_work_order_id, serial_no_id=None, batch_no_id=None):
    """
    Creates and submits a 'Manufacture' Stock Entry for the first suitable Work Order 
    found via 'get_serialized_items_with_existing_work_orders(source_work_order_id)'.
    Optionally associates a serial number with the final item. For a P202-O/5D1000
    body, the single finished serial input is reverse-mapped to the existing numeric
    5D0000 serial (0070 -> P202-O00000070) and its Batch No is read from the database.

    :param source_work_order_id: The Work Order from which to find item codes.
    :param serial_no_id: (Optional) Finished body serial supplied by FFTest.
    :return: A submitted Stock Entry doc or an error dict.
    """
    # Create a new Log Entry (global log_id is set within create_log_entry).
    create_log_entry("DEBUG: Entered make_stock_entry()")
    update_log_entry(
        log_id, f"DEBUG: source_work_order_id={source_work_order_id}, serial_no_id={serial_no_id}, batch_no_id={batch_no_id}")

    logger = frappe.logger("api", True)
    logger.info(
        f"make_stock_entry called with Work Order: {source_work_order_id}, Serial No: {serial_no_id}, and Batch No: {batch_no_id}")

    source_production_item = frappe.db.get_value(
        "Work Order", source_work_order_id, "production_item"
    )
    p202_flow = bool(serial_no_id) and _work_order_uses_p202_body(
        source_work_order_id
    )
    p202_source_serial = None

    try:
        if serial_no_id:
            update_log_entry(
                log_id, "DEBUG: First sanity check on serial_no existence..."
            )

        existing_serial = _get_serial_details(serial_no_id) if serial_no_id else None
        if p202_flow:
            _validate_p202_finished_serial(serial_no_id)

        if existing_serial:
            if (
                p202_flow
                and existing_serial.item_code == P202_SERIALIZED_ITEM_CODE
                and source_production_item != P202_SERIALIZED_ITEM_CODE
            ):
                _validate_serial_location(
                    existing_serial,
                    P202_SERIALIZED_ITEM_CODE,
                    (MAIN_STOCK_WAREHOUSE,),
                )
                update_log_entry(
                    log_id,
                    "DEBUG: Existing 5D1000 serial is available. "
                    "Skipping 5D1000 manufacture and consuming it in the final Work Order.",
                )
                return start_work_order_final(
                    source_work_order_id,
                    serial_no_id,
                    batch_no_id,
                )

            purchase_doc = existing_serial.purchase_document_no
            update_log_entry(
                log_id, f"DEBUG: Serial No already exists: {purchase_doc}"
            )
            return {"error": f"Serial No already exists: {purchase_doc}."}

        if p202_flow:
            p202_source_serial = _get_p202_source_serial(serial_no_id)
            _validate_serial_location(
                p202_source_serial,
                P202_RAW_ITEM_CODE,
                (MAIN_STOCK_WAREHOUSE, WIP_WAREHOUSE),
            )
            update_log_entry(
                log_id,
                "DEBUG: Resolved {0} to existing {1} serial {2} in {3}.".format(
                    serial_no_id,
                    P202_RAW_ITEM_CODE,
                    p202_source_serial.name,
                    p202_source_serial.warehouse,
                ),
            )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title="Serial validation error in make_stock_entry",
            message=frappe.get_traceback(),
        )
        update_log_entry(log_id, f"DEBUG: Serial validation error: {str(e)}")
        return {"error": str(e)}


    # 1) Find candidate Work Orders that match items from the given source Work Order
    update_log_entry(
        log_id, "DEBUG: Calling get_serialized_items_with_existing_work_orders() ...")
    p202_wip_work_order = _get_p202_wip_work_order(p202_source_serial)
    if p202_wip_work_order:
        matching_wos = [p202_wip_work_order]
        update_log_entry(
            log_id,
            "DEBUG: Selected Work Order {0} from the mapped serial's WIP transfer.".format(
                p202_wip_work_order["work_order_name"]
            ),
        )
    elif source_production_item == P202_SERIALIZED_ITEM_CODE:
        matching_wos = [{
            "work_order_name": source_work_order_id,
            "production_item": source_production_item,
        }]
    else:
        matching_wos = get_serialized_items_with_existing_work_orders(
            source_work_order_id)
    if (
        p202_source_serial
        and p202_source_serial.warehouse == MAIN_STOCK_WAREHOUSE
        and source_production_item != P202_SERIALIZED_ITEM_CODE
    ):
        matching_wos = [
            _select_p202_work_order_for_main_stock(matching_wos)
        ]
        update_log_entry(
            log_id,
            "DEBUG: Selected transferable 5D1000 Work Order {0} for source serial {1}.".format(
                matching_wos[0]["work_order_name"],
                p202_source_serial.name,
            ),
        )
    logger.info(f"Found matching Work Orders: {matching_wos}")
    update_log_entry(log_id, f"DEBUG: matching_wos returned: {matching_wos}")

    spare_prod = frappe.db.get_value("Work Order", source_work_order_id, "spare_part_production")
    
    # 2) Select the first matched Work Order to proceed (if any exist)
    if not matching_wos:
        if not spare_prod:
            update_log_entry(
                log_id, "DEBUG: No suitable Work Order found. Returning error dict.")
            msg = _("DEBUG: No suitable Work Order found. Returning error dict.")
            logger.error(msg)
            return {"error": f"No suitable Work Order found from {source_work_order_id}."}
    
    if spare_prod:
        target_wo_id = source_work_order_id
        spare_batch_no = frappe.db.get_value("Work Order", source_work_order_id, "spare_batch_no")
    else:
        target_wo_id = matching_wos[0]["work_order_name"]
    update_log_entry(log_id, f"DEBUG: Chosen target_wo_id: {target_wo_id}")

    # 3) If needed, start the Work Order (moves materials to WIP) if status is 'Not Started'
    current_status = frappe.db.get_value("Work Order", target_wo_id, "status")
    update_log_entry(
        log_id, f"DEBUG: Current Work Order status: {current_status}")
    transfer_qty = frappe.db.get_value(
        "Work Order", target_wo_id, "material_transferred_for_manufacturing"
    )
    work_order_qty = frappe.db.get_value("Work Order", target_wo_id, "qty")
    needs_transfer = current_status == "Not Started" or transfer_qty != work_order_qty
    try:
        if p202_source_serial and p202_source_serial.warehouse == WIP_WAREHOUSE:
            update_log_entry(
                log_id,
                "DEBUG: Mapped 5D0000 serial is already in WIP; "
                "skipping an additional material transfer.",
            )
        elif needs_transfer:
            update_log_entry(
                log_id, "DEBUG: Work Order needs material. Calling start_work_order() ...")
            source_serials = None
            if p202_source_serial:
                source_serials = {
                    P202_RAW_ITEM_CODE: p202_source_serial.name,
                }
            start_work_order(target_wo_id, source_serials=source_serials)
            if p202_source_serial:
                p202_source_serial = _get_serial_details(p202_source_serial.name)
        elif p202_source_serial:
            raise ValidationError(
                _(
                    "Mapped Serial No {0} is still in Main Stock, but Work Order {1} "
                    "has already received its full material quantity."
                ).format(p202_source_serial.name, target_wo_id)
            )
        else:
            update_log_entry(
                log_id,
                "DEBUG: Work Order already In Process or another status, "
                "skipping start_work_order().",
            )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title="Material transfer error in make_stock_entry",
            message=frappe.get_traceback(),
        )
        update_log_entry(log_id, f"DEBUG: Material transfer error: {str(e)}")
        return {"error": str(e)}

    try:
        update_log_entry(
            log_id, "DEBUG: Entering try block in make_stock_entry() ...")

        # 4) Validate the target Work Order existence
        if not frappe.db.exists("Work Order", target_wo_id):
            msg = _("Work Order does not exist.")
            logger.error(msg)
            update_log_entry(log_id, f"DEBUG: {msg}")
            raise ValidationError(msg)

        work_order_doc = frappe.get_doc("Work Order", target_wo_id)
        update_log_entry(
            log_id, f"DEBUG: Retrieved work_order_doc: {work_order_doc.name}")

        # 5) Validate that there's enough quantity left to produce
        remaining_qty = work_order_doc.qty - work_order_doc.produced_qty
        update_log_entry(
            log_id, f"DEBUG: Work Order remaining_qty: {remaining_qty}")
        if remaining_qty <= 0:
            msg = _("Work Order cannot produce additional quantity.")
            logger.error(msg)
            update_log_entry(log_id, f"DEBUG: {msg}")
            raise ValidationError(msg)

        # 6) Determine the WIP warehouse logic
        if not work_order_doc.wip_step:
            wip_warehouse = "Work In Progress - AMF21"
        else:
            wip_warehouse = "Main Stock - AMF21"
        update_log_entry(log_id, f"DEBUG: Using wip_warehouse={wip_warehouse}")

        # 7) Create and configure the Stock Entry for manufacturing
        update_log_entry(
            log_id, "DEBUG: Creating new Stock Entry (Manufacture).")
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.purpose = 'Manufacture'
        stock_entry.work_order = target_wo_id
        stock_entry.company = work_order_doc.company
        stock_entry.from_bom = 1
        stock_entry.bom_no = work_order_doc.bom_no
        stock_entry.use_multi_level_bom = 0
        stock_entry.fg_completed_qty = 1  # Hard-coded to produce 1 unit

        # Validate BOM existence
        if not frappe.db.exists("BOM", work_order_doc.bom_no):
            msg = _("BOM does not exist for the Work Order.")
            logger.error(msg)
            update_log_entry(log_id, f"DEBUG: {msg}")
            raise ValidationError(msg)

        stock_entry.inspection_required = 0
        stock_entry.from_warehouse = wip_warehouse
        stock_entry.to_warehouse = "Main Stock - AMF21"
        stock_entry.project = work_order_doc.project

        # 8) Configure the Stock Entry items from BOM
        update_log_entry(
            log_id, "DEBUG: Setting stock entry type and getting items from BOM.")
        stock_entry.set_stock_entry_type()
        stock_entry.get_items()

        # Calculate quantities from the BOM
        update_log_entry(
            log_id, f"DEBUG: Retrieving BOM doc: {stock_entry.bom_no}")
        bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
        required_qty_map = {
            item.item_code: item.qty * stock_entry.fg_completed_qty
            for item in bom_doc.items
        }
        update_log_entry(
            log_id, f"DEBUG: required_qty_map based on BOM: {required_qty_map}")

        # Update item lines
        for se_item in stock_entry.items:
            update_log_entry(
                log_id, f"DEBUG: Processing stock entry item: {se_item.item_code}")
            if se_item.item_code in required_qty_map:
                se_item.qty = flt(required_qty_map[se_item.item_code])
                se_item.transfer_qty = flt(
                    se_item.qty * se_item.conversion_factor)
                se_item.manual_source_warehouse_selection = 1
                if not work_order_doc.wip_step:
                    se_item.s_warehouse = "Work In Progress - AMF21"
                else:
                    se_item.s_warehouse = "Main Stock - AMF21"
                if (
                    p202_source_serial
                    and se_item.item_code == P202_RAW_ITEM_CODE
                ):
                    _set_source_serial(
                        se_item,
                        p202_source_serial,
                        se_item.s_warehouse,
                    )
                    update_log_entry(
                        log_id,
                        "DEBUG: Assigned existing source serial {0} and batch {1} "
                        "to {2}.".format(
                            p202_source_serial.name,
                            p202_source_serial.batch_no,
                            se_item.item_code,
                        ),
                    )
                update_log_entry(
                    log_id,
                    f"DEBUG: Updated item qty={se_item.qty}, s_warehouse={se_item.s_warehouse}"
                )

        # 9) Attach the provided serial to the actual finished-good row.
        if stock_entry.items:
            last_item = next(
                (
                    row
                    for row in stock_entry.items
                    if row.item_code == work_order_doc.production_item
                    and row.t_warehouse
                ),
                None,
            )
            if not last_item:
                raise ValidationError(
                    _("Finished-good row was not found in the Stock Entry.")
                )
            update_log_entry(
                log_id, f"DEBUG: Checking if last_item {last_item.item_code} is serialized...")
            if frappe.db.get_value("Item", last_item.item_code, "has_serial_no") == 1:
                update_log_entry(log_id, "DEBUG: Item is serialized.")
                if not serial_no_id:
                    msg = _("Serial number is required for the final item.")
                    logger.error(msg)
                    update_log_entry(log_id, f"DEBUG: {msg}")
                    raise ValidationError(msg)

                # Ensure that this serial doesn't already exist for the same item
                existing_serial = frappe.db.exists(
                    {
                        "doctype": "Serial No",
                        "serial_no": serial_no_id,
                        "item_code": last_item.item_code
                    }
                )
                if existing_serial:
                    msg = _("The specified Serial No already exists for this item.")
                    logger.error(msg)
                    update_log_entry(log_id, f"DEBUG: {msg}")
                    raise ValidationError(msg)

                last_item.serial_no = serial_no_id
                last_item.manual_target_warehouse_selection = 1
                last_item.t_warehouse = "Main Stock - AMF21"
                update_log_entry(
                    log_id, f"DEBUG: Assigned serial_no {serial_no_id} to last item.")

            # Batch handling (if item has_batch_no = 1)
            update_log_entry(
                log_id, "DEBUG: Checking if last_item has batch-tracking...")
            last_item.auto_batch_no_generation = 0
            if not spare_prod:
                last_item.batch_no = assign_or_create_batch_for_last_item(
                    target_wo_id, last_item)
                update_log_entry(
                    log_id, f"DEBUG: last_item.batch_no set to {last_item.batch_no}")
            else:
                if frappe.db.get_value("Item", last_item.item_code, "has_batch_no") == 1:
                    update_log_entry(log_id, "DEBUG: Item is batchable with auto WO batch no.")
                    print("spare_batch_no:", spare_batch_no)
                    last_item.batch_no = spare_batch_no
                    update_log_entry(
                        log_id, f"DEBUG: last_item.batch_no set to {last_item.batch_no}")

        # 10) Save and submit the Stock Entry
        stock_entry.save()
        update_log_entry(
            log_id, f"DEBUG: Saving Stock Entry doc {stock_entry.name}...")
        
        
        # already called in before_save hook
        # # Update rate and availability
        # update_log_entry(
        #     log_id, "DEBUG: Calling update_rate_and_availability_ste()...")
        # update_rate_and_availability_ste(stock_entry, None)

        update_log_entry(log_id, "DEBUG: Submitting the Stock Entry...")
        stock_entry.submit()
        logger.info(
            f"Successfully created and submitted Stock Entry {stock_entry.name}."
        )
        update_log_entry(
            log_id, f"DEBUG: Stock Entry submitted successfully: {stock_entry.name}")

        item_to_manuf = frappe.db.get_value("Work Order", source_work_order_id, 'production_item')
        update_log_entry(
            log_id, f"DEBUG: Item to manuf from Source OF: {item_to_manuf}")
        if not spare_prod:
            if not item_to_manuf.startswith('5'):
                start_work_order_final(source_work_order_id, serial_no_id, batch_no_id)

        return stock_entry

    except ValidationError as ve:
        frappe.db.rollback()
        frappe.log_error(
            title="Validation Error in make_stock_entry",
            message=frappe.get_traceback()
        )
        update_log_entry(
            log_id, "DEBUG: Caught ValidationError in make_stock_entry()")
        update_log_entry(log_id, f"DEBUG: ValidationError message: {str(ve)}")
        return {"error": str(ve)}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title="Unexpected Error in make_stock_entry",
            message=frappe.get_traceback()
        )
        update_log_entry(
            log_id, "DEBUG: Caught general Exception in make_stock_entry()")
        update_log_entry(log_id, f"DEBUG: Exception message: {str(e)}")
        return {"error": str(e)}


def start_work_order(work_order_id, source_serials=None):
    """
    Moves materials from 'Main Stock - AMF21' to 'Work In Progress - AMF21'
    for the specified Work Order to transition it from Not Started to In Process.
    """
    update_log_entry(log_id, "DEBUG: Entered start_work_order()")
    update_log_entry(log_id, f"DEBUG: work_order_id={work_order_id}")
    source_serials = source_serials or {}

    work_order_doc = frappe.get_doc("Work Order", work_order_id)
    update_log_entry(
        log_id, f"DEBUG: Retrieved work_order_doc: {work_order_doc.name}")

    # Create a 'Material Transfer for Manufacture' Stock Entry
    update_log_entry(
        log_id, "DEBUG: Creating 'Material Transfer for Manufacture' Stock Entry.")
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = 'Material Transfer for Manufacture'
    stock_entry.work_order = work_order_id
    stock_entry.company = "Advanced Microfluidics SA"
    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order_doc.bom_no
    stock_entry.use_multi_level_bom = 0
    stock_entry.fg_completed_qty = 1  # Hard-coded for 1 unit

    # Validate BOM
    if not frappe.db.exists("BOM", work_order_doc.bom_no):
        msg = _("BOM does not exist for this Work Order.")
        update_log_entry(log_id, f"DEBUG: {msg}")
        raise ValidationError(msg)

    update_log_entry(
        log_id, "DEBUG: Setting stock entry type and getting items from BOM.")
    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    # Calculate and set BOM item quantities
    update_log_entry(
        log_id, f"DEBUG: Retrieving BOM doc for start_work_order: {stock_entry.bom_no}")
    bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
    required_qty_map = {
        item.item_code: item.qty * stock_entry.fg_completed_qty
        for item in bom_doc.items
    }
    update_log_entry(
        log_id, f"DEBUG: required_qty_map in start_work_order: {required_qty_map}")

    for se_item in stock_entry.items:
        if se_item.item_code in required_qty_map:
            se_item.qty = flt(required_qty_map[se_item.item_code])
            se_item.transfer_qty = flt(se_item.qty * se_item.conversion_factor)
            source_serial_no = source_serials.get(se_item.item_code)
            if source_serial_no:
                serial_details = _get_serial_details(source_serial_no)
                _set_source_serial(
                    se_item,
                    serial_details,
                    MAIN_STOCK_WAREHOUSE,
                )
                update_log_entry(
                    log_id,
                    "DEBUG: Transferring source serial {0}, batch {1}, for {2}.".format(
                        serial_details.name,
                        serial_details.batch_no,
                        se_item.item_code,
                    ),
                )
            update_log_entry(
                log_id,
                f"DEBUG: Updated item {se_item.item_code} qty={se_item.qty}"
            )

    # Move from Main to WIP
    stock_entry.inspection_required = 0
    stock_entry.from_warehouse = MAIN_STOCK_WAREHOUSE
    stock_entry.to_warehouse = WIP_WAREHOUSE
    stock_entry.project = work_order_doc.project
    stock_entry.save()

    update_log_entry(
        log_id, f"DEBUG: Saving and submitting start_work_order Stock Entry: {stock_entry.name}")

    #already called in before_save hook
    # # Update valuation and availability
    # update_log_entry(
    #     log_id, "DEBUG: Calling update_rate_and_availability_ste() from start_work_order()...")
    # update_rate_and_availability_ste(stock_entry, None)
    stock_entry.submit()
    update_log_entry(log_id, "DEBUG: Material Transfer Stock Entry submitted.")

def start_work_order_final(work_order_id, serial_no_id=None, batch_no_id=None):
    """
    Moves materials from 'Main Stock - AMF21' to 'Main Stock - AMF21' 
    for the specified Work Order, with the Stock Entry purpose set to 'Manufacture'.

    Steps Implemented:
      1. Validate the Work Order + BOM
      2. Create Stock Entry (purpose = 'Manufacture')
      3. Pull items from BOM (stock_entry.get_items()), update BOM-based qty
      4. For each row in batch_no_id (if present):
         - fetch item_code from 'Batch'
         - run the SQL query joining `tabStock Ledger Entry` + `tabBin`
         - gather results with item_code, warehouse, and a non-zero qty_after_transaction
      5. In the for-loop of stock_entry.items, if se_item.item_code matches,
         update se_item.s_warehouse (or create new lines) with the retrieved warehouse,
         set se_item.batch_no, and set the correct qty if desired
      6. Assign serial_no only to the serialized component matching serial_no_id
      7. On the finished-good row, set product_serial_no = serial_no_id
      8. Save, update rate/availability, and submit
    """

    update_log_entry(log_id, "DEBUG: Entered start_work_order_final()")
    update_log_entry(
        log_id, f"DEBUG: work_order_id={work_order_id}, serial_no_id={serial_no_id}, batch_no_id={batch_no_id}"
    )

    # 1) Fetch and validate the Work Order
    work_order_doc = frappe.get_doc("Work Order", work_order_id)
    update_log_entry(log_id, f"DEBUG: Retrieved work_order_doc: {work_order_doc.name}")

    if not frappe.db.exists("BOM", work_order_doc.bom_no):
        msg = _("BOM does not exist for this Work Order.")
        update_log_entry(log_id, f"DEBUG: {msg}")
        raise ValidationError(msg)

    serial_details = _get_serial_details(serial_no_id)
    if not serial_details:
        raise ValidationError(
            _("Serial No {0} does not exist and cannot be consumed.").format(
                serial_no_id
            )
        )

    # 2) Create Stock Entry (purpose = 'Manufacture')
    update_log_entry(log_id, "DEBUG: Creating 'Manufacture' Stock Entry.")
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.purpose = 'Manufacture'
    stock_entry.work_order = work_order_id
    stock_entry.company = "Advanced Microfluidics SA"
    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order_doc.bom_no
    stock_entry.use_multi_level_bom = 0
    stock_entry.fg_completed_qty = 1  # Hard-coded for 1 unit, adjust if needed
    stock_entry.inspection_required = 0
    stock_entry.from_warehouse = MAIN_STOCK_WAREHOUSE
    stock_entry.to_warehouse = MAIN_STOCK_WAREHOUSE
    stock_entry.project = work_order_doc.project

    # 3) Pull items from BOM + recalc qty
    update_log_entry(log_id, "DEBUG: Setting stock entry type and getting items from BOM.")
    stock_entry.set_stock_entry_type()
    stock_entry.get_items()

    update_log_entry(log_id, f"DEBUG: Retrieving BOM doc: {stock_entry.bom_no}")
    bom_doc = frappe.get_doc("BOM", stock_entry.bom_no)
    required_qty_map = {
        item.item_code: item.qty * stock_entry.fg_completed_qty
        for item in bom_doc.items
    }
    update_log_entry(
        log_id, f"DEBUG: required_qty_map in start_work_order_final => {required_qty_map}"
    )

    # 4) For each row in batch_no_id, fetch item_code from 'Batch', run SQL
    #    We'll accumulate a list of dict like:
    #    {"item_code": ..., "warehouse": ..., "batch_no": ..., "qty": ...}
    #    If batch_no_id is not given, no special batch logic is done.
    batch_map = {}  # will hold the final combined info

    if batch_no_id:
        # parse JSON if needed
        if isinstance(batch_no_id, str):
            try:
                batch_no_id = json.loads(batch_no_id)
            except Exception as e:
                raise ValidationError(f"Invalid batch_no_id JSON: {str(e)}")

        if not isinstance(batch_no_id, list):
            raise ValidationError("batch_no_id must be a list of dicts with batch_no, etc.")

        update_log_entry(log_id, "DEBUG: Handling batch_no_id logic ...")

        for row in batch_no_id:
            bn = row.get("batch_no")
            if not bn:
                update_log_entry(log_id, "DEBUG: Skipping row missing 'batch_no'.")
                continue

            # --- 1) Fetch item_code for that batch ---
            item_code = frappe.db.get_value("Batch", bn, "item")
            if not item_code:
                update_log_entry(log_id, f"DEBUG: No item_code found for Batch {bn}, skipping.")
                continue

            # --- 2) Query current quantity and warehouse from tabBin ---
            query = """
                SELECT
                    sle.item_code,
                    sle.warehouse,
                    sle.qty_after_transaction AS qty
                FROM `tabStock Ledger Entry` AS sle
                JOIN `tabBin` AS bin
                    ON bin.item_code   = sle.item_code
                    AND bin.warehouse  = sle.warehouse
                    AND bin.actual_qty >= sle.actual_qty
                    AND bin.actual_qty > 0
                WHERE sle.batch_no = %(batch_no)s
                  AND sle.item_code = %(item_code)s
                  AND sle.warehouse = "Main Stock - AMF21"
                  AND sle.qty_after_transaction != 0
                GROUP BY sle.item_code, sle.warehouse
                LIMIT 1
            """
            query_vals = {"item_code": item_code, "batch_no": bn}
            result = frappe.db.sql(query, query_vals, as_dict=True)

            if not result:
                update_log_entry(log_id, f"DEBUG: No valid stock found for batch={bn}, item={item_code}")
                continue

            r = result[0]

            # --- 3) Append this batch info for later use ---
            batch_map[item_code] = {
                "item_code": r["item_code"],
                "warehouse": r["warehouse"],
                "batch_no": bn,
                "qty": flt(r["qty"])
            }

            update_log_entry(
                log_id,
                f"DEBUG: Found warehouse={r['warehouse']} qty={r['qty']} for item_code={r['item_code']} batch={bn}"
            )

    for se_item in stock_entry.items:
        item_code = se_item.item_code
        print (item_code)
        # 5a) If BOM says we need X quantity for this item, set it
        if item_code in required_qty_map:
            se_item.qty = flt(required_qty_map[item_code])
            se_item.transfer_qty = flt(se_item.qty * se_item.conversion_factor)
            update_log_entry(
                log_id, f"DEBUG: Updated item {item_code} qty={se_item.qty}"
            )

        # 5b) Set source defaults only on outgoing rows.
        is_finished_good = (
            item_code == work_order_doc.production_item
            and bool(se_item.t_warehouse)
        )
        if not is_finished_good:
            se_item.manual_source_warehouse_selection = 1
            se_item.s_warehouse = MAIN_STOCK_WAREHOUSE
        se_item.auto_batch_no_generation = 0

        # 5c) Assign the supplied serial only to its matching source Item.
        has_serial = frappe.db.get_value("Item", se_item.item_code, "has_serial_no")
        if has_serial == 1 and not is_finished_good:
            if serial_details.item_code != se_item.item_code:
                raise ValidationError(
                    _(
                        "Serial No {0} belongs to Item {1}; a separate serial is "
                        "required for serialized component {2}."
                    ).format(
                        serial_no_id,
                        serial_details.item_code,
                        se_item.item_code,
                    )
                )
            _set_source_serial(
                se_item,
                serial_details,
                MAIN_STOCK_WAREHOUSE,
            )
            update_log_entry(
                log_id, f"DEBUG: Set serial_no={serial_no_id} on {se_item.item_code} for warehouse {se_item.s_warehouse}"
            )

        # Store the tested body serial on the actual finished-good row.
        if is_finished_good:
            se_item.manual_target_warehouse_selection = 1
            se_item.t_warehouse = MAIN_STOCK_WAREHOUSE
            se_item.product_serial_no = serial_no_id
            update_log_entry(
                log_id,
                f"DEBUG: Set product_serial_no={serial_no_id} on finished row {se_item.item_code}."
            )

        # 5d) If we have a batch row for this item_code, let's handle them
        batch_row = batch_map.get(item_code)
        if batch_row:
            #se_item.manual_source_warehouse_selection = 1
            se_item.s_warehouse = batch_row["warehouse"]
            #se_item.auto_batch_no_generation = 0
            se_item.batch_no = batch_row["batch_no"]
            update_log_entry(
                log_id,
                f"DEBUG: Linked batch {batch_row['batch_no']} from {batch_row['warehouse']} for item {item_code}"
            )
        
        # 5e) If target warehouse is a Scrap warehouse → handle batch dynamically
        elif se_item.t_warehouse and "Scrap" in se_item.t_warehouse:
            se_item.manual_target_warehouse_selection = 1
            se_item.t_warehouse = "Main Stock - AMF21"
            has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")
            if has_batch == 1:
                query = """
                    SELECT
                        sle.batch_no,
                        sle.warehouse,
                        SUM(sle.actual_qty) AS qty
                    FROM `tabStock Ledger Entry` AS sle
                    WHERE sle.item_code = %(item_code)s
                    AND sle.warehouse = "Main Stock - AMF21"
                    AND sle.is_cancelled = 0
                    AND sle.batch_no IS NOT NULL
                    GROUP BY sle.batch_no, sle.warehouse
                    HAVING qty > 0
                    ORDER BY qty DESC
                    LIMIT 1
                """
                res = frappe.db.sql(query, {"item_code": item_code}, as_dict=True)
                if res:
                    r = res[0]
                    se_item.s_warehouse = r["warehouse"]
                    se_item.batch_no = r["batch_no"]
                    update_log_entry(
                        log_id,
                        f"DEBUG: Scrap item {item_code} → using batch {r['batch_no']} ({r['qty']} units in {r['warehouse']})"
                    )
                else:
                    update_log_entry(log_id, f"DEBUG: Scrap item {item_code} has no available batch in Main Stock.")
        else:
            update_log_entry(log_id, f"DEBUG: No batch info found for item {item_code}, defaulting warehouses if needed.")

    # 6) Save, update rate/availability, and submit
    print("stock_entry")
    stock_entry.save()
    update_log_entry(log_id, f"DEBUG: Saving Stock Entry {stock_entry.name} ...")

    #already called in before_save hook
    # update_log_entry(log_id, "DEBUG: Calling update_rate_and_availability_ste() from start_work_order_final()...")
    # update_rate_and_availability_ste(stock_entry, None)

    update_log_entry(log_id, "DEBUG: Submitting Stock Entry...")
    stock_entry.submit()
    update_log_entry(log_id, "DEBUG: Material Transfer Stock Entry submitted.")

    return stock_entry

def create_new_wo(item_code='520100', sales_order="", qty=1):
    update_log_entry(log_id, "DEBUG: Entered create_new_wo()")
    update_log_entry(
        log_id, f"DEBUG: item_code={item_code}, sales_order={sales_order}, qty={qty}")

    # Make a single Work Order for the given item
    bom_no = get_default_bom(item_code)
    update_log_entry(log_id, f"DEBUG: get_default_bom returned: {bom_no}")

    work_order = frappe.get_doc(dict(
        doctype='Work Order',
        production_item=item_code,
        bom_no=bom_no,
        qty=qty,
        company='Advanced Microfluidics SA',
        sales_order=sales_order,
        fg_warehouse='Main Stock - AMF21',
        simple_description='Auto-generated Work Order from non-available stock via FFTest.'
    )).insert()

    update_log_entry(
        log_id, "DEBUG: New Work Order inserted. Setting operations...")
    work_order.set_work_order_operations()
    work_order.save()
    work_order.submit()
    update_log_entry(
        log_id, f"DEBUG: Work Order created and submitted: {work_order.name}")

    return work_order


@frappe.whitelist()
def get_serialized_items_with_existing_work_orders(work_order_id):
    """
    1. Finds which item codes from 'Work Order Item' for a given work_order_id
       have has_serial_no=1 (joined from 'Item').
    2. Retrieves all existing Work Orders that have those item codes 
       as 'production_item', are either 'Not Started' or 'In Process', 
       and match 'parent_work_order'=work_order_id (if that's your desired filter).
    3. Returns a list of dicts: [{ "work_order_name": ..., "production_item": ... }, ...]
    """
    update_log_entry(
        log_id, "DEBUG: Entered get_serialized_items_with_existing_work_orders()")
    update_log_entry(log_id, f"DEBUG: work_order_id={work_order_id}")

    # Step 1: SQL join to get all distinct item_codes with has_serial_no=1
    sql_query = """
        SELECT DISTINCT w.item_code
        FROM `tabWork Order Item` AS w
        INNER JOIN `tabItem` AS i ON i.item_code = w.item_code
        WHERE w.parent = %s
          AND i.has_serial_no = 1
    """
    results = frappe.db.sql(sql_query, (work_order_id,), as_dict=True)
    item_codes = [row["item_code"] for row in results]
    update_log_entry(
        log_id, f"DEBUG: item_codes with has_serial_no=1: {item_codes}")

    # If no serialized items found, return early
    if not item_codes:
        update_log_entry(
            log_id, "DEBUG: No serialized items found. Checking current WO.")
        item_to_manuf = frappe.db.get_value("Work Order", work_order_id, 'production_item')
        if item_to_manuf.startswith('5'):
            update_log_entry(
            log_id, "DEBUG: Current WO is already a 5XXXXX production item WO. Returning current WO.")
            return [{"work_order_name": work_order_id, "production_item": item_to_manuf}]
        else:
            update_log_entry(
            log_id, "DEBUG: After check, no wo found. Something is wrong. Call assistance.")
            return []

    # Step 2: Get existing Work Orders that produce these item codes,
    #         are 'Not Started' or 'In Process',
    #         and (optionally) have 'parent_work_order' == work_order_id
    update_log_entry(
        log_id, "DEBUG: Searching for existing Work Orders with these item_codes.")
    wo_filters = {
        "production_item": ["in", item_codes],
        "status": ["in", ["Not Started", "In Process"]],
        "parent_work_order": work_order_id
    }

    existing_work_orders = frappe.get_all(
        "Work Order",
        filters=wo_filters,
        fields=["name", "production_item"],
        order_by="creation asc",
    )
    update_log_entry(
        log_id, f"DEBUG: existing_work_orders found: {existing_work_orders}")

    if not existing_work_orders:
        update_log_entry(
            log_id, "DEBUG: No matching existing WOs found. Attempting secondary lookup.")
        # 1) Attempt a second lookup with different filters
        secondary_wos = frappe.get_all(
            "Work Order",
            filters={
                "production_item": ["in", item_codes],
                "status": ["in", ["Not Started", "In Process"]],
                "sales_order": "",
                "parent_work_order": "",
            },
            fields=["name", "production_item"],
            order_by="creation asc",
        )
        update_log_entry(
            log_id, f"DEBUG: secondary_wos found: {secondary_wos}")

        if secondary_wos:
            existing_work_orders = secondary_wos
        else:
            # 2) If still empty, create new Work Orders for each item_code
            update_log_entry(
                log_id, "DEBUG: Still no WOs found. Creating new WOs for each serialized item code.")
            newly_created_wos = []
            for code in item_codes:
                update_log_entry(
                    log_id, f"DEBUG: Creating new WO for item_code={code}")
                wo_doc = create_new_wo(code)
                newly_created_wos.append({
                    "name": wo_doc.name,
                    "production_item": wo_doc.production_item
                })
            existing_work_orders = newly_created_wos

    # Step 3: De-duplicate without losing the deterministic query order.
    update_log_entry(log_id, "DEBUG: Building ordered unique Work Order list...")
    seen_work_orders = set()
    final_result = []
    for work_order in existing_work_orders:
        work_order_name = work_order["name"]
        if work_order_name in seen_work_orders:
            continue
        seen_work_orders.add(work_order_name)
        final_result.append({
            "work_order_name": work_order_name,
            "production_item": work_order["production_item"],
        })
    update_log_entry(
        log_id, f"DEBUG: get_serialized_items_with_existing_work_orders final_result: {final_result}")
    return final_result


def assign_or_create_batch_for_last_item(work_order_id, last_item):
    """
    If the last_item's item_code has_batch_no = 1, try to find an existing Batch with
    matching Work Order and Item. Otherwise create a new Batch. Returns the batch name or None.
    """
    update_log_entry(
        log_id, "DEBUG: Entered assign_or_create_batch_for_last_item()")
    update_log_entry(
        log_id, f"DEBUG: work_order_id={work_order_id}, last_item={last_item.item_code}")

    logger = frappe.logger()
    logger.info("assign_or_create_batch_for_last_item called.")

    # Check if the item is batch-tracked
    has_batch_no = frappe.db.get_value(
        "Item", last_item.item_code, "has_batch_no")
    update_log_entry(
        log_id, f"DEBUG: has_batch_no for {last_item.item_code} => {has_batch_no}")
    if has_batch_no == 1:
        # Attempt to find an existing batch for this item + Work Order
        existing_batch_name = frappe.db.get_value(
            "Batch",
            filters={"work_order": work_order_id, "item": last_item.item_code},
            fieldname="name"
        )
        if existing_batch_name:
            logger.info(
                f"Found existing batch {existing_batch_name} for Work Order {work_order_id}."
            )
            update_log_entry(
                log_id, f"DEBUG: Found existing batch {existing_batch_name}")
            return existing_batch_name

        # Otherwise create a new batch
        logger.info(f"No batch found for {work_order_id}; creating a new one.")
        update_log_entry(log_id, "DEBUG: Creating a new Batch doc...")
        work_order_doc = frappe.get_doc("Work Order", work_order_id)

        batch_doc = frappe.new_doc("Batch")
        batch_doc.name = create_batch_name(last_item.item_code)
        batch_doc.batch_id = batch_doc.name
        batch_doc.item = last_item.item_code
        batch_doc.work_order = work_order_id
        batch_doc.insert(ignore_permissions=True)
        update_log_entry(log_id, f"DEBUG: New batch created: {batch_doc.name}")
        return batch_doc.name

    # If not batch-tracked
    logger.info("Item is not batch-tracked. Returning None.")
    update_log_entry(
        log_id, "DEBUG: Item is not batch-tracked, returning None.")
    return None


def create_batch_name(item_code):
    """
    Generate an internal production batch name.
    """
    return make_internal_production_batch_id()


def update_rate_and_availability_ste(stock_entry_doc, method):
    """
    Recomputes stock rate and availability for the given Stock Entry doc.
    :param stock_entry_doc: A Stock Entry document to update.
    :param method: Unused standard Frappe hook param.
    """
    update_log_entry(
        log_id, "DEBUG: Entered update_rate_and_availability_ste()")
    logger = frappe.logger()
    logger.info("update_rate_and_availability_ste called.")

    update_log_entry(
        log_id, f"DEBUG: Calling get_stock_and_rate() on {stock_entry_doc.name} ...")
    get_stock_and_rate_override(stock_entry_doc, log_id=log_id)
    update_log_entry(log_id, "DEBUG: Completed get_stock_and_rate().")


def create_log_entry(message, category=None):
    """ 
    Create a new Log Entry and store its name in global log_id for subsequent update_log_entry calls. 
    """
    import datetime  # If not already imported at top-level
    log_doc = frappe.get_doc({
        "doctype": "Log Entry",
        "timestamp": datetime.datetime.now(),
        "category": category,
        "message": message,
        "reference_name": f"FFTest Stock Entry: {now_datetime()}"
    })
    log_doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # Store name in a global variable so subsequent calls to update_log_entry() can reference it.
    global log_id
    log_id = log_doc.name

    # Replace print(...) with an update_log_entry about the newly created log entry
    update_log_entry(log_id, f"DEBUG: Created new log entry with ID: {log_id}")
    return None

@frappe.whitelist()
def fetch_sn(product_id):
    """
    1) Finds the highest serial number for the given product_id.
    2) Increments that serial by 1.
    3) Returns the new serial.
    """
    # Example: Suppose your doctype is "Item Serial"
    # and it stores a field called "serial_no" (as an int) plus "product_id".
    # 
    # Step A: Query for the maximum serial_no belonging to product_id:
    print("product_id:",product_id)
    highest_sn = frappe.db.sql("""
        SELECT MAX(serial_no)
        FROM `tabSerial No`
        WHERE item_code = %s
    """, (product_id,), as_list=True)
    print("highest_sn:",highest_sn)
    # highest_sn is a list of lists, e.g. [[123]] or [[None]] if no rows
    if highest_sn and highest_sn[0][0] is not None:
        last_sn = int(highest_sn[0][0])
    else:
        # If not found, define a default. E.g. 999 or 1000
        last_sn = 0

    # Step B: increment
    new_sn = last_sn + 1
    print("new_sn:",new_sn)
    # Return the new_sn in a JSON-friendly format:
    return {"sn": str(new_sn)}



@frappe.whitelist()
def get_test_info(input_value):
    """
    function that returns all the necessary info for finding corresponding test
    1) receives an input value (workorder id or item code)
    2) returns a string with: client name, motor code, valve head code, syringe code
    """
    print("input_value:",input_value)
    if input_value.startswith('OF'):
        work_order_doc = frappe.get_doc("Work Order", input_value)
        item_code = work_order_doc.production_item
        item = frappe.get_doc("Item", item_code)
        client_name = work_order_doc.custo_name
        print("client_name:",client_name)
    else:
        if not (frappe.db.exists("Item", {"item_code": input_value})):
            print("Item does not exist")
            return "N/A,N/A,N/A,N/A"
        item = frappe.get_doc("Item", input_value)
        client_name = "N/A"
        print("client_name:",client_name)
    
    if item.item_type == "Finished Good":
        print("item.item_type: Finished Good")
        bom = frappe.get_doc("BOM", item.default_bom)
        motor_name = None
        valve_head_name = None
        syringe_name = None
        for bom_item in bom.items:
            if bom_item.item_code.startswith('5'):
                motor_name = frappe.db.get_value("Item", bom_item.item_code, "reference_code")
            if bom_item.item_code.startswith('3'):
                valve_head_name = frappe.db.get_value("Item", bom_item.item_code, "reference_code")
            if bom_item.item_code.startswith('70'):
                syringe_name = frappe.db.get_value("Item", bom_item.item_code, "reference_code")
        if syringe_name is None:
            syringe_name = "N/A"
        return f"{client_name},{motor_name},{valve_head_name},{syringe_name}"

    elif item.item_group == "Valve Head":
        if client_name == "N/A":
            client_name = "SPARE"
        valve_head_name = frappe.db.get_value("Item", item.item_code, "reference_code")
        return f"{client_name},N/A,{valve_head_name},N/A"
    
    else :
        print(item.item_type)
        return "N/A,N/A,N/A,N/A"
