# generate_qrcode.py

import frappe
from amf.amf.utils.generate_qr_item import generate_and_attach_qrcode  # Adjust this import accordingly

@frappe.whitelist()
def generate_and_attach():
    frappe.msgprint("generate_and_attach")
    try:
        generate_and_attach_qrcode()  # Adjust this call accordingly
        return "QR Codes generated successfully."
    except Exception as e:
        return str(e)
