# -*- coding: utf-8 -*-
# Copyright (c) bNovate (Douglas Watson)
# For license information, please see license.txt

import base64
from io import BytesIO
from amf.amf.utils.qr_code_generator import generate_qr_code
import frappe
from frappe.model.document import Document
from frappe.utils.file_manager import save_file, save_file_on_filesystem
import os
import tempfile

from erpnextswiss.erpnextswiss.doctype.label_printer.label_printer import create_pdf

@frappe.whitelist()
def download_label(label_reference, content):
    # Open PDF label, display in the browser instead of downloading.
    label = frappe.get_doc("Label Printer", label_reference)
    frappe.local.response.filename = "{name}.pdf".format(name=label_reference.replace(" ", "-").replace("/", "-"))
    frappe.local.response.filecontent = create_pdf(label, content)
    frappe.local.response.type = "download"
    #frappe.local.response.display_content_as = "inline" # Doesn't have any effect on our frappe version.

@frappe.whitelist()
def download_label_for_doc(doctype, docname, print_format, label_reference):
    """ Return PDF label based on an existing print format and label_printer size """
    doc = frappe.get_doc(doctype, docname)
    pf = frappe.get_doc("Print Format", print_format)

    template = """<style>{css}</style>{html}""".format(css=pf.css, html=pf.html)
    content = frappe.render_template(template, {"doc": doc})
    return download_label(label_reference, content)

# location: amf.amf.utils.labels.py
@frappe.whitelist()
def download_label_for_web(item_code, print_format, label_reference):
    """ Return PDF label based on an existing print format and label_printer size """
    print("*** download_label_for_web in utils ***")
    # Generate QR Code and convert it to base64
    img = generate_qr_code(item_code)

    pf = frappe.get_doc("Print Format", print_format)

    template = """<style>{css}</style>{html}""".format(css=pf.css, html=pf.html)
    content = frappe.render_template(template, {"qr_code": {"qr_code": img}})
    return download_label(label_reference, content)

@frappe.whitelist()
def attach_label(delivery_note, label_reference, content):
    label = frappe.get_doc("Label Printer", label_reference)
    file_content = create_pdf(label, content)

    # Create a filename for the attached PDF
    file_name = "{delivery_note}_labels.pdf".format(delivery_note=delivery_note)

    # Save the PDF content to a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file_content)
        temp_path = temp_file.name

    # Attach the temporary file to the Delivery Note
    attached_file = save_file_on_filesystem(file_name, file_content)

    # Delete the temporary file
    os.unlink(temp_path)

    # Return the name of the attached file
    return "File '{file_name}' attached to Delivery Note: {delivery_note}".format(file_name=file_name, delivery_note=delivery_note)


# Example of how to use this from Javascript:
#
# const label_format = "Labels 50x30mm"
# const content = "Hello, world"
# window.open(
#          frappe.urllib.get_full_url("/api/method/bnovate.bnovate.utils.labels.download_label"  
# 		    + "?label_reference=" + encodeURIComponent(label_format)
# 		    + "&content=" + encodeURIComponent(content))
#     , "_blank"); // _blank opens in new tab.

# Other tips:
# use {{ frappe.get_url() }} in print formats to get base url for images and other files.
# All js scripts used in print formats (jsbarcode, qrcodejs...) should be imported from cdn.


#import frappe          # already imported
from PIL import Image, ImageDraw, ImageFont
import requests
#from io import BytesIO
#import os              # already imported

@frappe.whitelist()
def fetch_all_serial_nos(item_code=None):
    # Define filters to fetch serial numbers only for the given item_code
    filters = {}
    if item_code:
        filters['item_code'] = item_code

    # Fetch all serial numbers from the Serial No DocType
    serial_nos = frappe.get_all('Serial No', filters=filters, fields=['name', 'item_code', 'qrcode'])
    #serial_nos = frappe.get_all('Serial No', filters={'name': 'P221-O00000308'}, fields=['name', 'item_code', 'qrcode'])
    return serial_nos

@frappe.whitelist()
def print_label_for_all_serials():
    item_code = 'P221-O'
    
    # Fetch all serial numbers for the given item code
    serial_nos = fetch_all_serial_nos(item_code=item_code)
    # Iterate over all serial numbers and print each one
    for serial in serial_nos:
        print_label(serial['name'], serial['item_code'], serial['qrcode'],)

    return f"Printed {len(serial_nos)} labels for item code {item_code}"

def print_label(serial_no, item_code='P221-O', qrcode_url=None):
    # Define the label size (24mm height x 29mm width) in pixels (assuming 300 DPI)
    dpi = 1200  # Dots per inch for high-resolution print
    label_width_px = int(29 / 25.4 * dpi)  # Convert mm to inches and multiply by 300 DPI
    label_height_px = int(24 / 25.4 * dpi)  # Convert mm to inches and multiply by 300 DPI

    # Create a blank image with white background
    img = Image.new('RGB', (label_width_px, label_height_px), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Load the Arial Bold font from the system (adjust the path if necessary)
    try:
        font_path = os.path.join(frappe.utils.get_bench_path(), "apps/amf/amf/public/fonts/NimbusSansNarrow-Bold.ttf")  # Typical path on Linux
        if not os.path.exists(font_path):
            font_path = "C:/Windows/Fonts/arialbd.ttf"  # Typical path on Windows for Arial Bold

        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 90)  # Adjust size as needed for bold text
        else:
            raise IOError(f"Font not found at {font_path}")
    except Exception as e:
        # Log the error and use default font
        print(f"Error loading font: {e}")
        font = ImageFont.load_default()

    # Define the content for the sticker
    product_code = 'S103623'  # Static or fetched from another source
    power = '40W'
    voltage = '18-24V'
    
    # Format the serial number
    if item_code == 'P221-O':
        formatted_serial = f'BA{serial_no[-6:]}'  # BA + last six digits of serial no
    else:
        formatted_serial = serial_no  # Default format for serial number

    # Positioning constants based on your CSS
    top_position_mm = 6.6  # 6.7mm from the top
    left_position_mm = 7.75  # 7.5mm from the left
    # Calculate the bounding box for the product_code text
    text_bbox = draw.textbbox((0, 0), product_code, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    # Calculate the line height based on the text height and a 0.46em ratio
    line_height = int(1.34 * text_height)

    # Convert mm to pixels
    top_position_px = int(top_position_mm / 25.4 * dpi)
    left_position_px = int(left_position_mm / 25.4 * dpi)

    # Draw the product code
    draw.text((left_position_px, top_position_px), product_code, font=font, fill=(0, 0, 0))

    # Draw the formatted serial number below product code
    serial_top_position_px = top_position_px + line_height + 5
    draw.text((left_position_px, serial_top_position_px), formatted_serial, font=font, fill=(0, 0, 0))

    # Draw power below the serial number
    power_top_position_px = serial_top_position_px + line_height + 5
    draw.text((left_position_px, power_top_position_px), power, font=font, fill=(0, 0, 0))

    # Draw voltage below power
    voltage_top_position_px = power_top_position_px + line_height + 5
    draw.text((left_position_px, voltage_top_position_px), voltage, font=font, fill=(0, 0, 0))
        
    # Check if qrcode_url is a local path or URL
    if qrcode_url:
        try:
            # Check if the qrcode_url starts with '/private/files/' to treat it as a local file path
            if qrcode_url.startswith('/private/files/'):
                # Get the full path from ERPNext's file system
                full_qr_code_path = os.path.join(frappe.utils.get_files_path(), os.path.basename(qrcode_url))
                if not os.path.exists(full_qr_code_path):
                    raise Exception(f"Local QR code file not found: {full_qr_code_path}")
                # Open the QR code from the local path
                qr_img = Image.open(full_qr_code_path).convert('RGBA')
            else:
                # Otherwise, treat it as a URL and fetch it
                response = requests.get(qrcode_url)
                if response.status_code != 200:
                    raise Exception(f"Failed to fetch QR code. Status code: {response.status_code}")
                qr_img = Image.open(BytesIO(response.content)).convert('RGBA')

            # Resize the QR code to fit the 8mm x 8mm space
            qr_code_size_mm = 8  # 8mm size for QR code
            qr_code_size_px = int(qr_code_size_mm / 25.4 * dpi)
            qr_img = qr_img.resize((qr_code_size_px, qr_code_size_px))

            # Position the QR code
            qr_code_top_px = int(7.0 / 25.4 * dpi)  # Position from top in mm
            qr_code_right_px = label_width_px - int(0.9 / 25.4 * dpi) - qr_code_size_px  # Position from right in mm

            # Paste the QR code onto the image
            img.paste(qr_img, (qr_code_right_px, qr_code_top_px), qr_img)
        except Exception as e:
            print(f"Error fetching or processing QR code: {e}")

    # Save the image as a PNG or send directly to the printer
    img_name = f"{serial_no}_label.png"
    physical_img_path = os.path.join(
        frappe.utils.get_bench_path(), 
        "sites", 
        frappe.utils.get_site_path(),
        "public/files",
        img_name
    )
    img.save(physical_img_path)

    return f"/files/{img_name}"