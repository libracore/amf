import frappe

@frappe.whitelist()
def get_latest_serial_no(item_code):
    serial_no = frappe.db.sql("""
        SELECT serial_no FROM `tabStock Entry Detail`
        WHERE item_code = %s
        ORDER BY creation DESC
        LIMIT 1
    """, item_code, as_dict=1)
    return serial_no[0]['serial_no'] if serial_no else None
