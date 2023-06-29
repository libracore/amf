import frappe
import base64
import os
from frappe import _
from frappe.utils.file_manager import save_file, save_url
from frappe.core.doctype.communication.email import make
from frappe.desk.form import assign_to

def get_context(context):
    context.no_cache = 1
    context.title = _('Packaging')

@frappe.whitelist()
def update_weight(delivery_note, weight, length, height, width, operator, image_data=None):
    # print("Weight in Python: {weight}".format(weight=weight))  # Print the weight
    delivery = frappe.get_doc("Delivery Note", delivery_note)
    delivery.update({
        "weight": weight,
        "length": length,
        "height": height,
        "width": width,
        "operator": operator
    })
    delivery.save()

    if image_data:
        # The image_data is in the format "data:image/png;base64,iVBORw0K...". We need to split out the base64 part:
        base64_data = image_data.split(",")[-1]

        # Decode the base64 data to bytes:
        data = base64.b64decode(base64_data)

        # Save the file and link it to the Delivery Note:
        file = save_file("image.png", data, "Delivery Note", delivery_note, is_private=1)

        # Update the Delivery Note with the file url:
        delivery.update({
            "image": file.file_url
        })
        delivery.save()
    
    # Clear existing assignees
    # existing_assignees = frappe.get_all("ToDo", filters={"reference_type": "Delivery Note", "reference_name": delivery_note}, fields=["name", "owner"])
    # for assignee in existing_assignees:
    #     assignee_doc = frappe.get_doc("ToDo", assignee.name)
    #     assignee_doc.delete()

    # Assign the Delivery Note to Madeleine Fryer
    user_email = "madeleine.fryer@amf.ch"
    assign_to.add({
        'assign_to': user_email, 
        'doctype': 'Delivery Note', 
        'name': delivery_note, 
        'description': 'Please review this delivery note and proceed with the shipment.'})

    # Send an email notification to Madeleine Fryer
    # make(content="A Delivery Note has been assigned to you!", 
    #      subject="New Delivery Note Assignment", 
    #      recipients=[user_email], 
    #      doctype="Delivery Note", 
    #      name=delivery_note)

    delivery.reload()

@frappe.whitelist()
def upload_image(filename):
    if frappe.request.method != "POST":
        # only allow POST
        frappe.throw(_("Invalid Method"), frappe.PermissionError)

    if filename:
        # check if a file was provided
        file = frappe.request.files.get('file')
    else:
        frappe.throw(_("No file was provided for uploading"), frappe.PermissionError)

    if file:
        # save the file and get its url
        filedata = save_file(file.filename, file.stream.read(), "Delivery Note")
        return filedata.file_url
