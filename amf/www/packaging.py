import frappe
import base64
import os
from frappe import _
from frappe.utils.file_manager import save_file
from frappe.core.doctype.communication.email import make

def get_context(context):
    context.no_cache = 1
    context.title = _('Packaging')

@frappe.whitelist()
def update_weight(delivery_note, weight, length, height, width, operator, image_data):
    # print(f"Weight in Python: {weight}")  # Print the weight
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
    
    # Assign the Delivery Note to Madeleine Fryer
    user_email = "alexandre.ringwald@amf.ch"
    frappe.share.add("Delivery Note", delivery_note, user=user_email, write=1)

    # Send an email notification to Madeleine Fryer
    make(content="A Delivery Note has been assigned to you!", 
         subject="New Delivery Note Assignment", 
         recipients=[user_email], 
         doctype="Delivery Note", 
         name=delivery_note)

    delivery.reload()

@frappe.whitelist()
def upload_image(filename):
    # This is just a placeholder. You'll need to handle the file upload here.
    print("Received file with filename: {filename}".format(filename=filename))
    # You might need to use frappe's upload API to handle file uploads
    return "File upload successful"
