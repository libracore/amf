import frappe
from frappe import _
from frappe.utils.file_manager import save_file, remove_all
import qrcode
from io import BytesIO
import os

def generate_and_attach_qrcode():
    # Fetch all items
    items = frappe.get_all('Item', filters={"name": ["NOT LIKE", "%/%"]}, fields=['name'])

    for item in items:
        item_name = item.name
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=0,
        )
        qr.add_data(item_name)
        qr.make(fit=True)

        img = qr.make_image(fill='black', back_color='white')
        
        # Convert the image to bytes
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_content = buffered.getvalue()

        # Save the generated QR code to a PNG
        # file_path = "/tmp/qr_code_{0}.png".format(item_name)
        # img.save(file_path)

        # Attach QR code PNG to the Item's qr_code field
        attach_to_item(item_name, img_content)

def attach_to_item(item_name, img_content):
    try:
        # Get the existing QR code URL
        # existing_qr_code = frappe.db.get_value('Item', item_name, 'qr_code')

        # Remove the QR code field value
        # frappe.db.set_value("Item", item_name, "qr_code", None)

        # If there's an existing QR code, delete it
        # if existing_qr_code:
        #     existing_file = frappe.get_list("File", filters={"file_url": existing_qr_code}, fields=["name"])
        #     if existing_file:
        #         frappe.delete_doc("File", existing_file[0].name)

        # Create a new File attachment
        remove_all("Item", item_name, True)
        file_data = save_file(f"{item_name}.png", img_content, "Item", item_name, "Home/Attachments", is_private=1)
        if file_data:
            # Update the Item's qr_code field with the attached file's URL
            frappe.db.set_value("Item", item_name, "qr_code", file_data.file_url)
    except Exception as e:
        frappe.throw(_("Unable to attach QR code to item {0}. Error: {1}").format(item_name, str(e)))

