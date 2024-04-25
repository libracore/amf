import base64
import frappe
from frappe import _
from frappe.utils.file_manager import save_file, remove_all
import qrcode
from io import BytesIO
import os

def generate_and_attach_qrcode(item_code):
    print(item_code)
    if item_code:
        # items = [{'name': item_code}]  # If item_code is provided, work with just that item
        items = frappe.get_all('Item', filters={'item_code': item_code}, fields=['name'])
        print("single:", items)
    else:
        # Fetch all items if item_code isn't provided
        items = frappe.get_all('Item', fields=['name'])
        print("all:", items)
    
    # total_items = len(items)
    # processed = 0
    
    for item in items:
        remove_all("Item", item.name, False)
        print("after removing")
        item_name = item.name.replace("/","-")
        qr = qrcode.QRCode(
            version=10,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=2,
            border=1,
        )
        qr.add_data(item_name)
        qr.make(fit=True)

        img = qr.make_image(fill='black', back_color='white')
        
        # Convert the image to bytes
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_content = buffered.getvalue()

        # processed += 1
        # progress = (processed / total_items) * 100
        # frappe.publish_realtime("progress", {"progress": progress}, user=frappe.session.user)

        # Attach QR code PNG to the Item's qr_code field
        attach_to_item(item_name, img_content)

def attach_to_item(item_name, img_content):
    try:
        # Create a new File attachment
        file_data = save_file("{}.png".format(item_name), img_content, "Item", item_name, is_private=0)
        if file_data:
            # Update the Item's qr_code field with the attached file's URL
            frappe.db.set_value("Item", item_name, "qr_code", file_data.file_url)
    except Exception as e:
        frappe.throw(_("Unable to attach QR code to item {0}. Error: {1}").format(item_name, str(e)))

