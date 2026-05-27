import re
import base64
import frappe
from frappe.desk.form.assign_to import add as assign_to_add
from erpnext.stock.doctype.quality_inspection_template.quality_inspection_template \
	import get_template_details
import html
from io import BytesIO

from frappe import _
from frappe.utils import cstr, formatdate

from amf.amf.utils.batch_naming import make_supplier_receipt_batch_id

RAW_MATERIAL_ITEM_GROUP = "Raw Material"
RAW_MATERIAL_LABEL_REFERENCE = "Labels 62x100mm"
RAW_MATERIAL_LABEL_WIDTH_MM = 100
RAW_MATERIAL_LABEL_HEIGHT_MM = 62
RAW_MATERIAL_LABEL_BACKGROUND_FILE = "slide_usi.pdf"
RAW_MATERIAL_FIT_VALUE_WIDTH_MM = 58
RAW_MATERIAL_LABEL_PRINT_MARGIN_MM = 2


def assign_supplier_batches(pr_doc, method=None):
    """
    Create or reuse one internal Batch per item and supplier batch combination.
    """
    created_batches = {}
    item_codes = [row.item_code for row in pr_doc.get("items") if row.item_code]
    if not item_codes:
        return

    item_batch_map = {
        item.name: item.has_batch_no
        for item in frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]},
            fields=["name", "has_batch_no"],
        )
    }

    for row in pr_doc.get("items"):
        if not row.item_code or not item_batch_map.get(row.item_code):
            continue

        supplier_batch = cstr(row.get("supplier_batch")).strip()
        key = (row.item_code, supplier_batch)

        if row.batch_no:
            created_batches.setdefault(key, row.batch_no)
            _sync_batch_supplier_batch(row.batch_no, supplier_batch)
            continue

        if not row.get("batch_no_auto_generation"):
            continue

        if key in created_batches:
            row.batch_no = created_batches[key]
            continue

        batch_values = {
            "doctype": "Batch",
            "item": row.item_code,
            "batch_id": make_supplier_receipt_batch_id(pr_doc.supplier),
            "supplier": pr_doc.supplier,
            "reference_doctype": pr_doc.doctype,
            "reference_name": pr_doc.name,
        }
        if frappe.get_meta("Batch").get_field("supplier_batch"):
            batch_values["supplier_batch"] = supplier_batch

        batch = frappe.get_doc(batch_values).insert(ignore_permissions=True)
        row.batch_no = batch.name
        created_batches[key] = batch.name


def _sync_batch_supplier_batch(batch_no, supplier_batch):
    if not batch_no or not supplier_batch or not frappe.db.exists("Batch", batch_no):
        return
    if not frappe.get_meta("Batch").get_field("supplier_batch"):
        return

    current_supplier_batch = cstr(frappe.db.get_value("Batch", batch_no, "supplier_batch")).strip()
    if not current_supplier_batch:
        frappe.db.set_value(
            "Batch",
            batch_no,
            "supplier_batch",
            supplier_batch,
            update_modified=False,
        )

@frappe.whitelist()
def get_templates_for_purchase_receipt(item_codes):
    """
    Find quality inspection templates for items in a purchase receipt.

    param items: JSON string of items in the purchase receipt
    return: list of Quality Inspection Templates associated with the items
    """
    template_list =[]

    # check if a specific template exists for each item code
    item_codes = frappe.parse_json(item_codes)
    for item_code in item_codes:
        item_template = frappe.db.get_value("Quality Inspection Template", {"name": ["like", f"%{item_code}%"]}, "name")
        if item_template and item_template not in template_list:
            template_list.append(item_template)
        
    return template_list


def generate_qa_for_purchase_receipt(pr_doc, method = None):
    """
    Generate Quality Inspection documents for a Purchase Receipt.

    """
    print("Generating Quality Inspection for Purchase Receipt:", pr_doc.name)
    if pr_doc.needs_quality_inspection != 1:
        return
    print("Purchase Receipt needs quality inspection.")

    email = "alexandre.trachsel@amf.ch"

    templates = pr_doc.get("qa_template")
    if templates:
        print("Found quality inspection templates in Purchase Receipt.")
        qa = frappe.new_doc("Global Quality Inspection")
        qa.reference_type = "Purchase Receipt"
        qa.reference_name = pr_doc.name
        qa.inspection_type = "Incoming"
        qa.inspected_by = email
        qa.status = ""
        qa.supplier = pr_doc.supplier
        # add for each item in prec document a line in drawings table with its drawing if it exists
        for item in pr_doc.items:
            drawing = get_item_drawing(item.item_code)
            drawing_row = qa.append("drawings", {})
            drawing_row.item_code = item.item_code
            drawing_row.item_name = item.item_name
            drawing_row.drawing = drawing

            qty_row = qa.append("items", {})
            qty_row.item_code = item.item_code
            qty_row.item_name = item.item_name
            qty_row.item_qty  = item.qty
            qty_row.status     = ""

        qa.flags.ignore_mandatory = True

        for template in templates:
            template_name = template.template_name
            template_details = get_template_details(template_name)
            if template_details:
                # Add a title row
                title_row = qa.append("item_specific", {})
                title_row.specification = template_name
                title_row.value = ""
                title_row.status = ""

                for detail in template_details:
                    detail_row = qa.append("item_specific", {})
                    detail_row.specification = detail.get("specification")
                    detail_row.value = detail.get("value")
                    detail_row.status = ""

        general_template = frappe.db.get_value("Quality Inspection Template",  {"name": "Purchase Receipt"}, "name")
        if general_template:
            qa.quality_inspection_template = general_template
            template_details = get_template_details(general_template)
            for detail in template_details:
                row = qa.append("readings", {})
                row.specification = detail.get("specification")
                row.value         = detail.get("value")
                row.status        = ""       


        qa.insert(ignore_permissions=True)

        assignment_message = f"Quality Inspection {qa.name} has been created for Purchase Receipt {pr_doc.name}."
        assignment_args = {
            "assign_to": email,
            "doctype": qa.doctype,
            "name": qa.name,
            "description": assignment_message,
        }
        assign_to_add(assignment_args)

        # Notify the user about the created Quality Inspection with a clickable link
        frappe.msgprint(
            f"""Quality Inspection: 
            <b><a href="/desk#Form/Global Quality Inspection/{qa.name}" target="_blank">{qa.name}</a></b>
                has been created and assigned to {email}.""",
            title="Quality Inspection Created",
            indicator="green"
        )



def get_item_drawing(item_code):
    """
    Get the drawing file for a given item code.
    """
    item = frappe.get_doc("Item", item_code)
    # return the drawing file where is_default is set if any
    drawing_file = None
    for drawing in item.drawing_item:
        if drawing.is_default:
            drawing_file = drawing.drawing
            break
    return drawing_file


@frappe.whitelist()
def has_raw_material_items(purchase_receipt):
    pr_doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
    pr_doc.check_permission("read")

    labels = _get_raw_material_label_rows(pr_doc, require_batch=False)
    return {
        "has_items": bool(labels),
        "count": len(labels),
    }


@frappe.whitelist()
def download_raw_material_stickers(purchase_receipt):
    pr_doc = frappe.get_doc("Purchase Receipt", purchase_receipt)
    pr_doc.check_permission("read")

    labels = _get_raw_material_label_rows(pr_doc, require_batch=True)
    if not labels:
        frappe.throw(_("No Raw Material items found on this Purchase Receipt."))

    label_printer = _get_raw_material_label_printer()

    frappe.local.response.filename = "{0}-raw-material-stickers.pdf".format(
        _safe_filename(pr_doc.name)
    )
    frappe.local.response.filecontent = _create_raw_material_label_pdf(
        label_printer,
        _render_raw_material_sticker_html(labels, label_printer),
    )
    frappe.local.response.type = "pdf"


def _get_raw_material_label_rows(pr_doc, require_batch=False):
    item_codes = sorted(set([
        row.item_code for row in pr_doc.get("items")
        if row.item_code
    ]))
    if not item_codes:
        return []

    item_by_code = _get_item_details_by_code(item_codes)
    raw_material_groups = _get_raw_material_item_groups()
    batch_supplier_batch = _get_batch_supplier_batch_map(pr_doc)

    labels = []
    seen = set()
    rows_missing_batch = []

    for row in pr_doc.get("items"):
        item = item_by_code.get(row.item_code) or frappe._dict()
        item_group = item.get("item_group") or row.get("item_group")
        if item_group not in raw_material_groups:
            continue

        batch_no = cstr(row.get("batch_no")).strip()
        if require_batch and not batch_no:
            rows_missing_batch.append(cstr(row.get("idx") or row.item_code))
            continue

        supplier_batch = (
            cstr(row.get("supplier_batch")).strip()
            or cstr(batch_supplier_batch.get(batch_no)).strip()
        )
        label_key = (row.item_code, batch_no, supplier_batch)
        if require_batch and label_key in seen:
            continue

        seen.add(label_key)
        labels.append(frappe._dict({
            "posting_date": formatdate(pr_doc.posting_date) if pr_doc.posting_date else "",
            "supplier": pr_doc.get("supplier_name") or pr_doc.get("supplier") or "",
            "purchase_order": pr_doc.get("purchase_order_") or row.get("purchase_order") or "",
            "supplier_batch": supplier_batch,
            "batch_no": batch_no,
            "batch_qr_code": _generate_batch_qr_code(batch_no) if batch_no else "",
            "item_code": row.item_code,
            "item_name": row.get("item_name") or item.get("item_name") or "",
        }))

    if rows_missing_batch:
        frappe.throw(_(
            "Cannot generate Raw Material stickers because row(s) {0} have no Batch No."
        ).format(", ".join(rows_missing_batch)))

    return labels


def _get_item_details_by_code(item_codes):
    items = frappe.get_all(
        "Item",
        filters={"name": ["in", item_codes]},
        fields=["name", "item_group", "item_name"],
    )
    return {item.name: item for item in items}


def _get_raw_material_item_groups():
    group = frappe.db.get_value(
        "Item Group",
        RAW_MATERIAL_ITEM_GROUP,
        ["lft", "rgt"],
        as_dict=True,
    )
    if not group:
        return set()

    groups = frappe.get_all(
        "Item Group",
        filters={
            "lft": [">=", group.lft],
            "rgt": ["<=", group.rgt],
        },
        fields=["name"],
    )
    return set([group.name for group in groups])


def _get_batch_supplier_batch_map(pr_doc):
    if not frappe.get_meta("Batch").get_field("supplier_batch"):
        return {}

    batch_nos = sorted(set([
        cstr(row.get("batch_no")).strip()
        for row in pr_doc.get("items")
        if row.get("batch_no")
    ]))
    if not batch_nos:
        return {}

    batches = frappe.get_all(
        "Batch",
        filters={"name": ["in", batch_nos]},
        fields=["name", "supplier_batch"],
    )
    return {batch.name: batch.supplier_batch for batch in batches}


def _generate_batch_qr_code(batch_no):
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(batch_no)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def _render_raw_material_sticker_html(labels, label_printer):
    content = [_raw_material_sticker_css(label_printer)]
    for label in labels:
        content.append("""
            <section class="amf-pr-label">
                <div class="amf-pr-label__value amf-pr-label__value--date">{posting_date}</div>
                <div class="amf-pr-label__value amf-pr-label__value--item-code">{item_code}</div>
                <div class="amf-pr-label__value amf-pr-label__value--item-name" style="{item_name_style}">{item_name}</div>
                <div class="amf-pr-label__value amf-pr-label__value--supplier">{supplier}</div>
                <div class="amf-pr-label__value amf-pr-label__value--supplier-batch">{supplier_batch}</div>
                <div class="amf-pr-label__value amf-pr-label__value--purchase-order">{purchase_order}</div>
                <div class="amf-pr-label__value amf-pr-label__value--amf-batch" style="{batch_no_style}">{batch_no}</div>
                <div class="amf-pr-label__qr">
                    <img src="data:image/png;base64,{batch_qr_code}" alt="">
                </div>
            </section>
        """.format(
            posting_date=_escape(label.posting_date),
            supplier=_escape(label.supplier),
            item_code=_escape(label.item_code),
            item_name=_escape(label.item_name),
            supplier_batch=_escape(label.supplier_batch),
            purchase_order=_escape(label.purchase_order),
            batch_no=_escape(label.batch_no),
            item_name_style=_fit_label_value_style(label.item_name, 12, 7.2),
            batch_no_style=_fit_label_value_style(label.batch_no, 16, 7.6),
            batch_qr_code=label.batch_qr_code,
        ))

    return "\n".join(content)


def _get_raw_material_label_printer():
    if frappe.db.exists("Label Printer", RAW_MATERIAL_LABEL_REFERENCE):
        return frappe.get_doc("Label Printer", RAW_MATERIAL_LABEL_REFERENCE)

    return frappe._dict({
        "width": RAW_MATERIAL_LABEL_WIDTH_MM,
        "height": RAW_MATERIAL_LABEL_HEIGHT_MM,
    })


def _create_raw_material_label_pdf(label_printer, content):
    import os
    import pdfkit

    fname = os.path.join("/tmp", "frappe-pdf-{0}.pdf".format(frappe.generate_hash()))
    label_width = label_printer.get("width") or RAW_MATERIAL_LABEL_WIDTH_MM
    label_height = label_printer.get("height") or RAW_MATERIAL_LABEL_HEIGHT_MM
    options = {
        "page-width": "{0}mm".format(label_width),
        "page-height": "{0}mm".format(label_height),
        "margin-top": "0mm",
        "margin-bottom": "0mm",
        "margin-left": "0mm",
        "margin-right": "0mm",
        "disable-smart-shrinking": "",
        "print-media-type": None,
        "encoding": "UTF-8",
        "quiet": None,
    }

    html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body>{content}</body>
        </html>
    """.format(content=content)

    try:
        pdfkit.from_string(html_content, fname, options=options)
        with open(fname, "rb") as fileobj:
            return _apply_raw_material_label_background(fileobj.read())
    finally:
        if os.path.exists(fname):
            os.remove(fname)


def _apply_raw_material_label_background(label_pdf):
    import os
    from PyPDF2 import PdfFileReader, PdfFileWriter

    background_path = frappe.get_site_path(
        "private",
        "files",
        RAW_MATERIAL_LABEL_BACKGROUND_FILE,
    )
    if not os.path.exists(background_path):
        frappe.throw(_(
            "Raw Material sticker background file {0} was not found in private files."
        ).format(RAW_MATERIAL_LABEL_BACKGROUND_FILE))

    with open(background_path, "rb") as background_file:
        background_pdf = background_file.read()

    background_template_reader = PdfFileReader(BytesIO(background_pdf))
    if background_template_reader.getNumPages() < 1:
        frappe.throw(_("Raw Material sticker background PDF has no pages."))

    label_reader = PdfFileReader(BytesIO(label_pdf))
    if label_reader.getNumPages() < 1:
        frappe.throw(_("Raw Material sticker overlay PDF has no pages."))

    writer = PdfFileWriter()
    # PyPDF2 page objects keep references to their source readers until write().
    background_readers = []

    for page_index in range(label_reader.getNumPages()):
        background_reader = PdfFileReader(BytesIO(background_pdf))
        background_readers.append(background_reader)
        page = background_reader.getPage(0)
        page.mergePage(label_reader.getPage(page_index))
        _add_raw_material_label_page(writer, page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output.read()


def _add_raw_material_label_page(writer, page):
    margin_pt = RAW_MATERIAL_LABEL_PRINT_MARGIN_MM * 72.0 / 25.4
    if margin_pt <= 0:
        writer.addPage(page)
        return

    page_width = float(page.mediaBox.getWidth())
    page_height = float(page.mediaBox.getHeight())
    if margin_pt * 2 >= page_width or margin_pt * 2 >= page_height:
        frappe.throw(_("Raw Material sticker print margin is larger than the label page."))

    scale = min(
        (page_width - (margin_pt * 2)) / page_width,
        (page_height - (margin_pt * 2)) / page_height,
    )
    tx = (page_width - (page_width * scale)) / 2
    ty = (page_height - (page_height * scale)) / 2

    output_page = writer.addBlankPage(width=page_width, height=page_height)
    output_page.mergeScaledTranslatedPage(page, scale, tx, ty)


def _fit_label_value_style(value, max_font_size_pt, line_height_mm):
    font_size = _get_fit_font_size(value, max_font_size_pt, RAW_MATERIAL_FIT_VALUE_WIDTH_MM)
    return (
        "width:{width}mm;"
        "max-width:{width}mm;"
        "font-size:{font_size:.1f}pt;"
        "line-height:{line_height}mm;"
    ).format(
        width=RAW_MATERIAL_FIT_VALUE_WIDTH_MM,
        font_size=font_size,
        line_height=line_height_mm,
    )


def _get_fit_font_size(value, max_font_size_pt, max_width_mm):
    text = cstr(value).strip()
    if not text:
        return max_font_size_pt

    try:
        from reportlab.pdfbase import pdfmetrics

        max_width_pt = max_width_mm * 72.0 / 25.4
        text_width_pt = pdfmetrics.stringWidth(text, "Helvetica-Bold", max_font_size_pt)
        if text_width_pt <= max_width_pt:
            return max_font_size_pt

        # Leave a small buffer because wkhtmltopdf renders Arial/Helvetica
        # slightly differently than ReportLab's built-in Helvetica metrics.
        return max(3.5, (max_width_pt * 0.96 / text_width_pt) * max_font_size_pt)
    except Exception:
        return _get_fit_font_size_by_length(text, max_font_size_pt, max_width_mm)


def _get_fit_font_size_by_length(text, max_font_size_pt, max_width_mm):
    average_char_width_mm = 0.18 * max_font_size_pt
    estimated_width_mm = len(text) * average_char_width_mm
    if estimated_width_mm <= max_width_mm:
        return max_font_size_pt

    return max(3.5, max_font_size_pt * max_width_mm / estimated_width_mm)


def _raw_material_sticker_css(label_printer):
    css = """
        <style>
            @page {
                size: __LABEL_WIDTH__mm __LABEL_HEIGHT__mm;
                margin: 0;
            }

            html,
            body {
                margin: 0;
                padding: 0;
                width: __LABEL_WIDTH__mm;
                height: __LABEL_HEIGHT__mm;
                background: transparent;
                font-family: Arial, Helvetica, sans-serif;
            }

            *,
            *::before,
            *::after {
                box-sizing: border-box;
            }

            .amf-pr-label {
                position: relative;
                display: block;
                width: __LABEL_WIDTH__mm;
                height: __LABEL_HEIGHT__mm;
                color: #000;
                overflow: hidden;
                page-break-after: always;
                page-break-inside: avoid;
            }

            .amf-pr-label:last-child {
                page-break-after: auto;
            }

            .amf-pr-label__value {
                position: absolute;
                /*left: 14mm;
                right: 28.5mm;*/
                height: 7.2mm;
                color: #000;
                overflow: hidden;
                padding: 0;
                font-size: 12pt;
                font-weight: 700;
                line-height: 7.2mm;
                white-space: nowrap;
                text-overflow: ellipsis;
            }

            .amf-pr-label__value--date {
                top: 1.5mm;
                right: 1mm;
                height: 8mm;
                font-size: 20pt;
                line-height: 8mm;
            }

            .amf-pr-label__value--item-code {
                top: 10.5mm;
                left: 15mm;
                font-size: 20pt;
                line-height: 7.4mm;
            }

            .amf-pr-label__value--item-name {
                top: 18.9mm;
                left: 15mm;
                width: __FIT_VALUE_WIDTH__mm;
                max-width: __FIT_VALUE_WIDTH__mm;
            }

            .amf-pr-label__value--supplier {
                top: 28mm;
                left: 15mm;
            }

            .amf-pr-label__value--supplier-batch {
                top: 36.8mm;
                left: 15mm;
            }

            .amf-pr-label__value--purchase-order {
                top: 45.8mm;
                left: 15mm;
            }

            .amf-pr-label__value--amf-batch {
                top: 54.5mm;
                left: 15mm;
                /*right: 28.5mm;*/
                width: __FIT_VALUE_WIDTH__mm;
                max-width: __FIT_VALUE_WIDTH__mm;
                height: 7.6mm;
                font-size: 8pt;
                line-height: 7.6mm;
                white-space: nowrap;
                text-overflow: clip;
            }

            .amf-pr-label__qr {
                position: absolute;
                top: 8.9mm;
                right: 1.8mm;
                width: 24.5mm;
                height: 24.5mm;
                overflow: hidden;
                text-align: center;
            }

            .amf-pr-label__qr img {
                display: block;
                width: 24.5mm;
                height: 24.5mm;
                margin: 0;
                object-fit: contain;
            }
        </style>
    """
    return css.replace(
        "__LABEL_WIDTH__",
        cstr(label_printer.get("width") or RAW_MATERIAL_LABEL_WIDTH_MM),
    ).replace(
        "__LABEL_HEIGHT__",
        cstr(label_printer.get("height") or RAW_MATERIAL_LABEL_HEIGHT_MM),
    ).replace(
        "__FIT_VALUE_WIDTH__",
        cstr(RAW_MATERIAL_FIT_VALUE_WIDTH_MM),
    )


def _escape(value):
    return html.escape(cstr(value))


def _safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", cstr(value)).strip("-") or "purchase-receipt"
