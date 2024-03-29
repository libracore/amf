import frappe
import base64
import os
from frappe import _
from frappe.utils.file_manager import save_file
from frappe.core.doctype.communication.email import make
from frappe.desk.form import assign_to

def get_context(context):
    context.no_cache = 1
    context.title = _('Packaging')

@frappe.whitelist()
def get_delivery_notes_by_prefix(prefix):
    # First, check the base Delivery Note
    base_note = frappe.get_value('Delivery Note', prefix, 'status')

    # If the base delivery note exists and is not cancelled, return it
    if base_note and base_note != 'Cancelled':
        return prefix

    # If the base delivery note is cancelled, look for amends
    if base_note == 'Cancelled':
        counter = 1
        while True:
            amend_name = prefix + '-' + str(counter)
            amend_status = frappe.get_value('Delivery Note', amend_name, 'status')

            if not amend_status:
                # This amend does not exist, break out of loop
                break

            if amend_status != 'Cancelled':
                # This amend is valid (not cancelled)
                return amend_name

            counter += 1

    # If no valid amends found or the base note does not exist
    return None


@frappe.whitelist()
def on_update(doc, method):
    print(doc)
    previous_doc = frappe.get_doc("Delivery Note", doc)
    # Check if the document is a 'Delivery Note' and its status is 'To Bill'
    if doc.doctype == "Delivery Note" and doc.status == "To Bill":
        # Check if the operator is updated
        if previous_doc and doc.operator != previous_doc.operator:
            user_email = 'alexandre.ringwald@amf.ch'
            subject = _("{doc_name} Ready To Ship").format(doc_name=doc.name)
            message = _(
                "Dear Madeleine,"
                "<br> {doc_name} has been updated by {operator} and is ready to ship in the shipping room."
                "<br> Regards,"
                "<br> Your Supply Chain Team"
            ).format(doc_name=doc.name, operator=doc.operator)
            
            # Send the email
            print("Sending email.")
            make(subject= subject,
                 content= message,
                 #cc=['madeleine.fryer@amf.ch'],
                 recipients=['alexandre.ringwald@amf.ch'],
                 communication_medium='Email',
                 send_email=True,)
    print("on_update(DN)")

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
    if not frappe.db.exists('ToDo', {'reference_type': 'Delivery Note', 'reference_name': delivery.name, 'owner': user_email}):
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
    #on_update(delivery, None)
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
