# Import necessary Frappe framework functions
import frappe
from frappe.model.document import Document

from io import BytesIO
import barcode
from barcode.writer import ImageWriter

def generate_barcode(data):
    # Choose the barcode format, e.g., 'code128'
    CODE128 = barcode.get_barcode_class('code128')
    # Generate the barcode
    barcode_instance = CODE128(data, writer=ImageWriter())
    # Save the barcode image to a file and return the file path
    file_path = f"/tmp/{data}.png"
    barcode_instance.save(file_path)
    return file_path

# Define the event hook handler
def after_insert_handler(doc, method):
    # Generate a barcode for the new batch (using its name or any unique identifier)
    barcode_path = generate_barcode(doc.name)
    # Here you might want to attach the barcode image to the document or store the path
    # For simplicity, let's assume we're storing the barcode file path in a custom field named 'barcode'
    doc.db_set('barcode', barcode_path)
    frappe.db.commit()
