import re
import frappe
from frappe.desk.form.assign_to import add as assign_to_add
from erpnext.stock.doctype.quality_inspection_template.quality_inspection_template \
	import get_template_details
from erpnext.stock.doctype.batch.batch import get_batch_qty
import re
import html


def auto_gen_qa_inspection(batch_name):
    """
    Automatically generate a Quality Inspection for certain Batches when the manufacture_batch field in work_order is filled in.
    """
    # controle if batch exists
    if not frappe.db.exists("Batch", batch_name):
        return
    doc = frappe.get_doc("Batch", batch_name)
    if not doc:
        return
    
    email = "alexandre.trachsel@amf.ch"

    item_code = doc.item
    item_group = frappe.db.get_value("Item", item_code, "item_group")
    is_six_digit = len(item_code) == 6 and item_code.isdigit()
    
    if item_code.startswith(("20", "10")) and is_six_digit:
        # create Quality Inspection
        qi = frappe.new_doc("Global Quality Inspection")
        qi.item_code = item_code
        qi.inspection_type = "Incoming"
        qi.reference_type = "Batch"
        qi.reference_name = doc.name
        qi.batch_no = doc.name
        qi.sample_size = get_batch_qty(batch_no=doc.name, warehouse="Quality Control - AMF21")
        description = frappe.db.get_value("Item", item_code, "internal_description") or ""

        description = description.replace("<b>", "").replace("</b>", "")
        description = re.sub(r'</div>\s*<div>', '\n', description)
        description = description.replace("<div>", "").replace("</div>", "")
        description = html.unescape(description)

        qi.description = description
        qi.item_name = frappe.db.get_value("Item", item_code, "item_name")
        qi.inspected_by = email
        qi.status = ''
        qi.drawing = get_item_drawing(item_code)

        qi.flags.ignore_mandatory = True

        # check if there is a Quality Inspection Template for this item
        item_template = frappe.db.get_value("Quality Inspection Template", {"name": ["like", f"% {item_code} %"]}, "name")
        if item_template:
            template_details = get_template_details(item_template)
            # Add a title row
            title_row = qi.append("item_specific", {})
            title_row.is_title = 1
            title_row.specification = item_template
            title_row.value = ""
            title_row.status = ""
            for detail in template_details:
                row = qi.append("item_specific", {})
                row.specification = detail.get("specification")
                row.value         = detail.get("value")
                row.status        = ""
        
        # add item group specific templates
        if item_group == "Plug":
            template_details = get_template_details("Contrôle usinage PLUG")
            # Add a title row
            title_row = qi.append("item_specific", {})
            title_row.is_title = 1
            title_row.specification = "Contrôle usinage PLUG"
            title_row.value = ""
            title_row.status = ""
            for detail in template_details:
                row = qi.append("item_specific", {})
                row.specification = detail.get("specification")
                row.value         = detail.get("value")
                row.status        = ""
        elif item_group == "Valve Seat":
            template_details = get_template_details("Contrôle usinage SEAT")
            # Add a title row
            title_row = qi.append("item_specific", {})
            title_row.is_title = 1
            title_row.specification = "Contrôle usinage SEAT"
            title_row.value = ""
            title_row.status = ""
            for detail in template_details:
                row = qi.append("item_specific", {})
                row.specification = detail.get("specification")
                row.value         = detail.get("value")
                row.status        = ""

        # add general inspection template for Batches if exists
        general_template = frappe.db.get_value("Quality Inspection Template",  {"name": ["like", f"% BATCH %"]}, "name")
        if general_template:
            qi.quality_inspection_template = general_template
            template_details = get_template_details(general_template)
            for detail in template_details:
                row = qi.append("readings", {})
                row.specification = detail.get("specification")
                row.value         = detail.get("value")
                row.status        = ""

        # add one line in items table for checking the quantity
        if qi.sample_size > 0:
            qty_row = qi.append("items", {})
            qty_row.item_code = item_code
            qty_row.item_name = qi.item_name
            qty_row.item_qty  = qi.sample_size
            qty_row.status     = ""

        # Insert the new Quality Inspection document (ignoring permissions if necessary)
        # print all fieds for debugging
        # for d in qi.as_dict():
        #     print(f"{d}: {qi.get(d)}")
        qi.insert(ignore_permissions=True)

        # Build the assignment message with Delivery Note name and client (assumed to be in 'customer')
        assignment_message = f"Inspection Qualité générée pour le Batch: {doc.name} pour l'item: {item_code}:{qi.item_name}."
        
        # Auto assign the Quality Inspection to atr@amf.ch with the message
        # Create assignment arguments using the new add method signature
        assignment_args = {
            "assign_to": email,
            "doctype": "Global Quality Inspection",
            "name": qi.name,
            "description": assignment_message,
            # "assignment_rule": <your_rule_here>,  # Optional if you need to specify an assignment rule.
        }
        assign_to_add(assignment_args)
        
        # # Notify the user about the created Quality Inspection with a clickable link
        # frappe.msgprint(
        #     f"""Quality Inspection: 
        #     <b><a href="/desk#Form/Global Quality Inspection/{qi.name}" target="_blank">{qi.name}</a></b>
        #         has been created and assigned to {email}.""",
        #     title="Quality Inspection Created",
        #     indicator="green")
        


def get_item_drawing(item_code):
    """
    Get the drawing file for a given item code.
    """
    item = frappe.get_doc("Item", item_code)
    for drawing in item.drawing_item:
        if drawing.is_default:
            drawing_file = drawing.drawing
            break
    return drawing_file