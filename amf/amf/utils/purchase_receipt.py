import re
import frappe
from frappe.desk.form.assign_to import add as assign_to_add
from erpnext.stock.doctype.quality_inspection_template.quality_inspection_template \
	import get_template_details
import html

from frappe.utils import cstr

from amf.amf.utils.batch_naming import make_supplier_receipt_batch_id


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
