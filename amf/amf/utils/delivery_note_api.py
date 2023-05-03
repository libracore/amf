import frappe
from amf.amf.utils.qr_code_generator import generate_qr_code

@frappe.whitelist()
def generate_serial_number_qr_codes(delivery_note):
    doc = frappe.get_doc("Delivery Note", delivery_note)
    qr_codes = []
    for item in doc.items:
        if item.serial_no:
            serial_numbers = item.serial_no.split('\n')
            for serial_number in serial_numbers:
                if serial_number.strip():
                    qr_code_base64 = generate_qr_code(serial_number)
                    qr_codes.append({"serial_number": serial_number, "qr_code": qr_code_base64})
    return qr_codes
