import os
import frappe
from frappe import whitelist

@whitelist()
def save_zpl_string_to_file(zpl_string, file_name):
    zpl_file_path = os.path.join(frappe.get_site_path(), file_name)

    with open(zpl_file_path, 'w') as zpl_file:
        zpl_file.write(zpl_string)

    return "ZPL string saved to file: {zpl_file_path}".format(zpl_file_path=zpl_file_path)
