import frappe
from frappe import _
import base64


def generate_qr(doc, method=None):
    from frappe.utils.file_manager import save_file
    from amf.amf.utils.qr_code_generator import generate_qr_code  # assuming generate_qr_code is in utils/qr_code_generator

     # get some data from the Work Order to put in the QR code
    #data = doc.name  # for example
    data = frappe.utils.get_url_to_form(doc.doctype, doc.name)

    # generate the QR code
    qr_code_str = generate_qr_code(data)

    # decode base64 string to bytes
    qr_code_bytes = base64.b64decode(qr_code_str)

    # save the QR code to a file and attach it to the Work Order
    if doc.doctype == "Work Order":
        file_data = save_file("qr_code.png", qr_code_bytes, "Work Order", doc.name, is_private=1)
    elif doc.doctype == "Job Card":
        file_data = save_file("qr_code.png", qr_code_bytes, "Job Card", doc.name, is_private=1)
    
    # Set the field to the file's URL
    doc.qr_code = file_data.file_url

    # Save the document (don't trigger events)
    #doc.save()
    #doc.reload()
