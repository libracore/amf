import frappe
import qrcode
from io import BytesIO
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image
import os

def generate_qr_code(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=2,
        border=0,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_str

@frappe.whitelist()
def generate_qr_code_for_item(item_code):
    return generate_qr_code(item_code)

@frappe.whitelist()
def generate_pdf_with_qr_codes():
    print("Running...")
    #items = frappe.get_all('Item', fields=['item_code', 'item_name', 'item_group'], filters={"item_code": ["not like", "%/%"]})
    items = frappe.get_all('Item', fields=['item_code', 'item_name', 'item_group'],
                                   filters={"item_code": ["not like", "%/%"]},
                                   order_by="item_group asc, item_name asc")

    # Define color mapping here (replace with your actual item groups and desired colors)
    color_mapping = {
        'Plug': (1, 0, 0),  # Red
        'Valve Seat': (0, 1, 0),  # Green
        'Valve Head': (0, 0, 1),  # Blue
        'Electronic boards': (1, 1, 0),
        'Cables': (0, 1, 1),
        'Generic items': (1, 0, 1),
        'Kits': (1, 1, 1),
        'Packaging': (0.5, 0, 0),
        'Parts': (0, 0.5, 0),
        'Products': (0, 0, 0.5),
        'Raw Materials': (0.5, 0.5, 0),
        'Assemblies': (0, 0.5, 0.5),
        'Marketing Materials': (0.5, 0.5, 0.5),
        'Sub Assemblies': (1, 0.5, 0),
    }

    filename = "/tmp/qrcodes.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    height -= 150
    column_width = (width / 3) - 28
    x = column_width / 2 # Start in the middle of the first column
    y = height  # Start at the top of the page
    column = 0

    current_item_group = items[0]['item_group'] if items else None

    for item in items:
        #print("x:", x)
        #print("y:", y)

        if item['item_group'] != current_item_group:
            c.showPage()
            # Draw the title of the new item group at the top of the page
            c.setFont("Courier", 30)
            c.drawString(column_width/2, height + 100, item['item_group'])
            y = height
            current_item_group = item['item_group']
            column = 0
            x = column * column_width + column_width / 2

        qr_code_data = generate_qr_code(item['item_code'])
        qr_code_img = Image.open(BytesIO(base64.b64decode(qr_code_data)))

        qr_file_path = "/tmp/qr_code_{}.png".format(item['item_code'])
        qr_code_img.save(qr_file_path)

        if y < 50:  # If we're at the bottom of the page...
            column += 1  # Move to the next column
            y = height  # Reset Y to the top of the page

            if column > 2:  # If we're past the last column...
                c.showPage()  # Move to the next page
                column = 0  # Reset the column count

            x = column * column_width + column_width / 2  # Calculate the new X position

        # Draw the item code above the QR code
        
        n = 20
        item_name = item['item_name']
        if len(item_name) > n:
            item_name = item_name[:n-3] + '...'
        c.setFont("Courier", 8)  # Set the font and size
        c.drawString(x, y-10, item['item_code'])  # Draw the string
        c.setFont("Courier", 8)  # Set the font and size
        c.drawString(x, y-20, item_name)
        # Set the color for the item group
        color = color_mapping.get(item['item_group'], (0, 0, 0))  # Default to black if item group not found
        c.setFillColorRGB(*color)
        c.setFont("Courier", 8)  # Set the font and size
        c.drawString(x, y-30, item['item_group'])
        color = (0, 0, 0)  # Default to black if item group not found
        c.setFillColorRGB(*color)

        c.drawImage(qr_file_path, x, y, width=80, height=80)
        y = y - 125  # Move down the page

        # Remove the temporary QR code image file
        os.remove(qr_file_path)

    c.save()

    # Convert the PDF file to base64 string to send back to front-end
    with open(filename, 'rb') as file:
        pdf_data = file.read()
    return base64.b64encode(pdf_data).decode("utf-8")