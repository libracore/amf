"""Independent backend for the duplicated Production Tracking / Planning page.

The original production_tracking module and saved reports are never changed.
Writes use Document.save so Work Order validation and existing hooks still run.
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import cint, cstr, getdate, get_datetime, nowdate


REPORT_NAMES = ("Plug à usiner...", "Valve Seat à usiner...")
PAGE_ROUTE = "production-tracking-planning"
EXPECTED_DATE = "expected_delivery_date_"
EDITABLE_TYPES = {"Data", "Link", "Attach", "Select", "Date", "Datetime",
                  "Int", "Float", "Currency", "Percent", "Check", "Text", "Small Text", "Long Text"}


def _require_access(doctype="Work Order", permission="read"):
    if frappe.session.user == "Guest" or not frappe.has_permission(doctype, permission):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def _reports():
    _require_access()
    reports = []
    for name in REPORT_NAMES:
        report = frappe.get_doc("Report", name)
        if not report.is_permitted():
            frappe.throw(_("Not permitted to access report {0}").format(name), frappe.PermissionError)
        if report.disabled or report.report_type != "Report Builder" or report.ref_doctype != "Work Order":
            frappe.throw(_("Report {0} must be an enabled Work Order Report Builder report.").format(name))
        config = frappe.parse_json(report.json or "{}")
        if config.get("group_by"):
            frappe.throw(_("Grouped reports cannot be edited as individual Work Orders."))
        reports.append((name, config))
    return reports


def _has_field_access(df, permission):
    if not df or not cint(df.permlevel) or frappe.session.user == "Administrator":
        return True
    roles = frappe.get_roles()
    return any(p.role in roles and p.permlevel == df.permlevel and p.get(permission)
               for p in frappe.get_meta("Work Order").permissions)


def _columns(reports):
    meta = frappe.get_meta("Work Order")
    columns = []
    seen = set()
    for report_name, config in reports:
        for fieldname, doctype in config.get("fields", []):
            df = meta.get_field(fieldname)
            if doctype != "Work Order" or (not df and fieldname not in ("name", "docstatus")):
                frappe.throw(_("Unsupported column in report {0}: {1}").format(report_name, fieldname))
            if fieldname in seen:
                continue
            seen.add(fieldname)
            reason = ""
            if fieldname in ("name", "docstatus"):
                reason = _("Managed by the Work Order lifecycle")
            elif df.read_only or df.fieldtype not in EDITABLE_TYPES:
                reason = _("Calculated or fetched from the linked Item")
            elif not _has_field_access(df, "write"):
                reason = _("No permission to edit this field")
            columns.append({
                "fieldname": fieldname,
                "label": _(df.label) if df else (_("ID") if fieldname == "name" else _("Document Status")),
                "fieldtype": df.fieldtype if df else ("Int" if fieldname == "docstatus" else "Data"),
                "options": df.options if df else None,
                "reqd": cint(df.reqd) if df else 0,
                "editable": not bool(reason),
                "reason": reason,
                "readable": _has_field_access(df, "read"),
                "allow_on_submit": cint(df.allow_on_submit) if df else 0,
                "width": max(100, min(420, cint(config.get("column_widths", {}).get(fieldname)) or 150)),
            })
    if EXPECTED_DATE not in seen:
        frappe.throw(_("The machining reports must include Expected Date."))
    return columns


def _report_rows(config, columns, name=None):
    filters = list(config.get("filters") or [])
    if name:
        filters.append(["Work Order", "name", "=", name])
    fields = [c["fieldname"] for c in columns if c["readable"]]
    fields += ["name", "modified", "docstatus", "owner"]
    fields += [df.fieldname for df in frappe.get_meta("Work Order").get_link_fields()]
    return frappe.get_list("Work Order", fields=list(dict.fromkeys(fields)), filters=filters,
                           order_by="`tabWork Order`.`{0}` asc, `tabWork Order`.`name` asc".format(EXPECTED_DATE),
                           limit_page_length=0)


def _serialize_row(row, columns):
    permission_values = {key: value for key, value in row.items() if not key.startswith("_")}
    permission_values["doctype"] = "Work Order"
    permission_doc = frappe.get_doc(permission_values)
    can_write = bool(frappe.has_permission("Work Order", "write", doc=permission_doc))
    if cint(row.docstatus) == 1:
        can_write = can_write and bool(frappe.has_permission("Work Order", "submit", doc=permission_doc))
    editable_fields = [c["fieldname"] for c in columns if c["editable"] and can_write
                       and (cint(row.docstatus) == 0 or
                            (cint(row.docstatus) == 1 and c["allow_on_submit"]))]
    values = {c["fieldname"]: row.get(c["fieldname"]) if c["readable"] else None for c in columns}
    values.update({"name": row.name, "_modified": cstr(row.modified),
                   "_reports": row.get("_reports", []), "_editable_fields": editable_fields})
    return values


@frappe.whitelist()
def get_machining_planning():
    reports = _reports()
    columns = _columns(reports)
    rows = {}
    counts = {}
    for name, config in reports:
        source_rows = _report_rows(config, columns)
        counts[name] = len(source_rows)
        for row in source_rows:
            if row.name not in rows:
                rows[row.name] = row
                row["_reports"] = []
            rows[row.name]["_reports"].append(name)
    ordered = sorted(rows.values(), key=lambda row: (not bool(row.get(EXPECTED_DATE)),
                     cstr(row.get(EXPECTED_DATE)), row.name))
    return {"columns": columns, "rows": [_serialize_row(row, columns) for row in ordered],
            "reports": list(REPORT_NAMES), "counts": counts, "total": len(ordered)}


def _validate_value(column, value):
    fieldtype = column["fieldtype"]
    if value is None or value == "":
        if column["reqd"]:
            frappe.throw(_("{0} is required").format(column["label"]))
        return None if fieldtype in ("Date", "Datetime") else (0 if fieldtype in ("Int", "Float", "Check") else "")
    if isinstance(value, (dict, list, bool)):
        frappe.throw(_("Invalid value for {0}").format(column["label"]))
    if fieldtype in ("Int", "Float", "Currency", "Percent", "Check"):
        try:
            number = Decimal(cstr(value))
            if not number.is_finite() or (fieldtype in ("Int", "Check") and number != number.to_integral_value()):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            frappe.throw(_("{0} must be a valid number").format(column["label"]))
        return int(number) if fieldtype in ("Int", "Check") else float(number)
    if fieldtype == "Date":
        try:
            date = getdate(value)
            if cstr(date) != cstr(value):
                raise ValueError
            return date
        except (ValueError, TypeError):
            frappe.throw(_("{0} must use YYYY-MM-DD").format(column["label"]))
    if fieldtype == "Select" and value not in (column.get("options") or "").split("\n"):
        frappe.throw(_("Invalid option for {0}").format(column["label"]))
    return cstr(value)


def _change_item(doc, item_code):
    """Mirror Desk item selection, including its dependent BOM and fields."""
    item = frappe.get_doc("Item", item_code)
    item.check_permission("read")
    boms = frappe.get_list("BOM", filters={"item": item_code, "is_active": 1,
                           "is_default": 1, "docstatus": 1}, fields=["name"], limit_page_length=1)
    if not boms:
        frappe.throw(_("This Item has no accessible active default BOM. Select its BOM in the Work Order form."))
    doc.production_item = item.name
    doc.bom_no = boms[0].name
    for target, source in (("item_name", "item_name"), ("rd_code", "reference_code"),
                           ("description", "description"), ("stock_uom", "stock_uom"), ("image", "image")):
        doc.set(target, item.get(source))
    doc.get_items_and_operations_from_bom()


@frappe.whitelist(methods=["POST"])
def save_machining_work_order(name, changes, modified):
    reports = _reports()
    columns = _columns(reports)
    changes = frappe.parse_json(changes) if isinstance(changes, str) else changes
    if not isinstance(changes, dict) or not changes:
        frappe.throw(_("No changes to save"))
    frappe.db.sql("select name from `tabWork Order` where name=%s for update", (name,))
    doc = frappe.get_doc("Work Order", name)
    doc.check_permission("read")
    doc.check_permission("write")
    if not modified or get_datetime(modified) != get_datetime(doc.modified):
        frappe.throw(_("This Work Order was changed by another user. Reload the planning before saving."),
                     frappe.TimestampMismatchError)
    if not any(_report_rows(config, columns, name) for _, config in reports):
        frappe.throw(_("This Work Order is no longer in the machining reports. Reload the planning."))
    row = frappe._dict(doc.as_dict())
    allowed = _serialize_row(row, columns)["_editable_fields"]
    column_map = {c["fieldname"]: c for c in columns}
    for fieldname, value in changes.items():
        if fieldname not in allowed:
            frappe.throw(_("Field {0} cannot be edited on this Work Order.").format(fieldname), frappe.PermissionError)
        doc.set(fieldname, _validate_value(column_map[fieldname], value))
    if "production_item" in changes and doc.production_item != row.production_item:
        _change_item(doc, doc.production_item)
    elif "qty" in changes:
        doc.set_work_order_operations()
    doc.save()
    doc.reload()
    return {"name": doc.name, "modified": cstr(doc.modified)}


# Duplicated overview methods; no calls into the master page's Python module.
@frappe.whitelist()
def get_work_orders():
    _require_access()
    common = ["name", "production_item", "item_name", "progress"]
    ongoing = frappe.get_list("Work Order", filters={"status": "In Process", "production_item": ["not like", "5_100_"]}, fields=common, limit_page_length=0)
    upcoming = frappe.get_list("Work Order", filters={"docstatus": 1, "status": "Not Started", "production_item": ["not like", "5_100_"]}, fields=common, limit_page_length=0)
    for wo in ongoing + upcoming:
        wo.operation_type = "Assemblage"
        wo.timer_info = get_timer_info(wo.name)
    drafts = frappe.get_list("Work Order", filters={"docstatus": 0, "status": "Draft", "priority": ["<=", 5]}, fields=common, limit_page_length=0)
    for wo in drafts:
        wo.item_group = frappe.db.get_value("Item", wo.production_item, "item_group")
        wo.operation_type = find_operation_type(wo)
        if wo.operation_type == "Usinage":
            wo.timer_info = {"status": None, "operators": ""}
            (ongoing if wo.progress in ("Fabrication", "QC") else upcoming).append(wo)
    return {"ongoing": ongoing, "upcoming": upcoming}


def find_operation_type(work_order):
    code = cstr(work_order.production_item)
    return "Usinage" if len(code) == 6 and code.startswith(("10", "20")) and cstr(work_order.item_group).lower() in ("plug", "valve seat") else "Assemblage"


def get_timer_info(work_order):
    if not frappe.has_permission("Timer Production", "read"):
        return {"status": None, "operators": None}
    timers = frappe.get_list("Timer Production", filters={"work_order": work_order,
        "status": ["in", ["IN PROCESS", "PAUSED"]]}, fields=["status", "assigned_operators"],
        order_by="modified desc", limit_page_length=1)
    return {"status": timers[0].status, "operators": timers[0].assigned_operators} if timers else {"status": None, "operators": None}


@frappe.whitelist()
def get_shipments():
    _require_access("Sales Order")
    today = getdate(nowdate())
    monday = today - timedelta(days=today.weekday())
    shipments = frappe.get_list("Sales Order", filters={"delivery_date": ["between", [monday, monday + timedelta(days=6)]], "docstatus": 1}, fields=["name", "customer_name", "delivery_date"], order_by="delivery_date asc", limit_page_length=0)
    delivered_orders = set()
    if shipments and frappe.has_permission("Delivery Note", "read"):
        sales_orders = [so.name for so in shipments]
        notes = frappe.get_list("Delivery Note", filters=[
            ["Delivery Note", "docstatus", "=", 1],
            ["Delivery Note Item", "against_sales_order", "in", sales_orders],
        ], fields=["name"], limit_page_length=0)
        if notes:
            items = frappe.get_list("Delivery Note Item", filters={
                "parent": ["in", list({note.name for note in notes})],
                "against_sales_order": ["in", sales_orders], "docstatus": 1,
            }, fields=["against_sales_order"], limit_page_length=0)
            delivered_orders = {item.against_sales_order for item in items}
    for so in shipments:
        so.shipment_status = "green" if so.name in delivered_orders else ("white" if so.delivery_date >= today else "orange")
    return shipments


@frappe.whitelist()
def get_note():
    _require_access()
    if not frappe.has_permission("Production Notes", "read"):
        return {"text": "", "can_write": False, "modified": None}
    notes = frappe.get_list("Production Notes", fields=["name", "prod_tracking_note", "modified"], limit_page_length=1)
    if notes:
        doc = frappe.get_doc("Production Notes", notes[0].name)
        return {"text": doc.prod_tracking_note or "", "modified": cstr(doc.modified),
                "can_write": bool(frappe.has_permission("Production Notes", "write", doc=doc)) and doc.docstatus == 0}
    return {"text": "", "modified": None, "can_write": bool(frappe.has_permission("Production Notes", "create"))}


@frappe.whitelist(methods=["POST"])
def save_note(note_text, modified=None):
    _require_access()
    _require_access("Production Notes", "write")
    notes = frappe.get_list("Production Notes", fields=["name"], limit_page_length=1)
    if notes:
        frappe.db.sql("select name from `tabProduction Notes` where name=%s for update", (notes[0].name,))
        doc = frappe.get_doc("Production Notes", notes[0].name)
        if not modified or get_datetime(doc.modified) != get_datetime(modified):
            frappe.throw(_("The production note was changed by another user. Reload before saving."), frappe.TimestampMismatchError)
    else:
        doc = frappe.new_doc("Production Notes")
    doc.prod_tracking_note = note_text
    doc.save()
    return {"modified": cstr(doc.modified)}


def install_page(publish=False):
    """Copy first if absent; update ONLY the independent page from versioned files."""
    _require_access("Web Page", "write")
    if frappe.db.exists("Web Page", PAGE_ROUTE):
        page = frappe.get_doc("Web Page", PAGE_ROUTE)
        if page.route != PAGE_ROUTE or page.title != "Production Tracking - Planning":
            frappe.throw(_("Destination page does not match the planning copy."))
    else:
        if frappe.db.exists("Web Page", {"route": PAGE_ROUTE}):
            frappe.throw(_("The planning route is already in use."))
        page = frappe.copy_doc(frappe.get_doc("Web Page", "production-tracking"))
        page.title = "Production Tracking - Planning"
        page.route = PAGE_ROUTE
        page.published = 0
        page.insert()
    for field, filename in (("main_section_html", "page.html"), ("javascript", "page.js"), ("css", "page.css")):
        with open(frappe.get_app_path("amf", "templates", "includes", "production_tracking_planning", filename)) as stream:
            page.set(field, stream.read())
    page.content_type = "HTML"
    page.published = cint(publish)
    page.save()
    return {"name": page.name, "route": page.route, "published": page.published}
