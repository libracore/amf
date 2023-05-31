import frappe
from frappe import _

def get_context(context):
    context.no_cache = 1
    context.title = _('Packaging')

@frappe.whitelist()
def update_weight(delivery_note, weight, length, height, width, operator):
    # print("Weight in Python: {weight}".format(weight=weight))  # Print the weight
    delivery = frappe.get_doc("Delivery Note", delivery_note)
    delivery.update({
        "weight": weight,
        "length": length,
        "height": height,
        "width": width,
        "weight": weight,
        "operator": operator
    })
    delivery.save()

@frappe.whitelist()
def upload_image(filename):
    # This is just a placeholder. You'll need to handle the file upload here.
    print("Received file with filename: {filename}".format(filename=filename))
    # You might need to use frappe's upload API to handle file uploads
    return "File upload successful"
