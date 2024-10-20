import frappe
from frappe.utils import flt

@frappe.whitelist()
def get_stock(code=None):
    stock_data = []

    if code:
        # Check if the provided code is an item_code or a reference_code
        item = frappe.db.get_value('Item', {'item_code': code}, ['item_code', 'item_name', 'reference_code'])
        if not item:
            item = frappe.db.get_value('Item', {'reference_code': code}, ['item_code', 'item_name', 'reference_code'])
        if item:
            item_codes = [{'item_code': item[0], 'item_name': item[1], 'reference_code': item[2]}]
        else:
            frappe.throw(f"Item with code '{code}' not found.")
    else:
        item_codes = frappe.get_all('Item', filters={'disabled': 0}, fields=['item_code', 'item_name', 'reference_code'])

    for item in item_codes:
        item_code = item['item_code']
        item_name = item['item_name'] if 'item_name' in item else ''
        item_refc = item['reference_code'] if 'reference_code' in item else ''
        
        # Get a list of Bin documents for the specific item
        bins = frappe.get_all('Bin', filters={'item_code': item_code, 'warehouse': ['not like', '%OLD%']}, fields=['warehouse', 'actual_qty', 'reserved_qty', 'projected_qty'])

        for bin in bins:
            stock_data.append({
                'item_code': item_code,
                'item_name': item_name,
                'reference_code': item_refc,
                'warehouse': bin['warehouse'],
                'actual_qty': bin['actual_qty'],
                'reserved_qty': bin['reserved_qty'],
                'projected_qty': bin['projected_qty']
            })

    return stock_data

@frappe.whitelist()
def disable_zero_stock_batches():
    # Get batches with zero stock or batches not found in Stock Ledger Entry
    batches = frappe.db.sql("""
        SELECT name
        FROM `tabBatch`
        WHERE name NOT IN (
            SELECT DISTINCT batch_no
            FROM `tabStock Ledger Entry`
            WHERE batch_no IS NOT NULL
        )
        OR name IN (
            SELECT batch_no
            FROM `tabStock Ledger Entry`
            GROUP BY batch_no
            HAVING SUM(actual_qty) = 0
        )
    """, as_dict=True)

    # Disable batches
    for batch in batches:
        frappe.db.set_value('Batch', batch['name'], 'disabled', 1)
        frappe.db.commit()  # Commit the changes to the database after each update