# -*- coding: utf-8 -*-
# Copyright (c) bNovate (Douglas Watson)
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.file_manager import save_file
import os
import tempfile
from frappe.utils.file_manager import save_file_on_filesystem

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

@frappe.whitelist()
def attach_label(delivery_note, label_reference, content):
    label = frappe.get_doc("Label Printer", label_reference)
    file_content = create_pdf(label, content)

    # Create a filename for the attached PDF
    file_name = f"{delivery_note}_labels.pdf"

    # Save the PDF content to a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file_content)
        temp_path = temp_file.name

    # Attach the temporary file to the Delivery Note
    attached_file = save_file_on_filesystem(file_name, file_content)

    # Delete the temporary file
    os.unlink(temp_path)

    # Return the name of the attached file
    return f"File '{file_name}' attached to Delivery Note: {delivery_note}"


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