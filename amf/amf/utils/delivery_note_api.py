import frappe
from amf.amf.utils.qr_code_generator import generate_qr_code

@frappe.whitelist()
def generate_serial_number_qr_codes(stock_entry):
    doc = frappe.get_doc("Stock Entry", stock_entry)
    stock_entry_qr = []
    for item in doc.items:
        if item.serial_no:
            serial_numbers = item.serial_no.split('\n')
            for serial_number in serial_numbers:
                if serial_number.strip():
                    qr_code_base64 = generate_qr_code(serial_number)
                    stock_entry_qr.append({"serial_number": serial_number, "qr_code": qr_code_base64})
                    # Create a new child table entry for each QR code
                    doc.append('stock_entry_qr', {"serial_number": serial_number, "qr_code": qr_code_base64})
    doc.save()  # Save the document to persist the new child table entries
    return stock_entry_qr
