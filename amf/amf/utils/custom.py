import frappe

@frappe.whitelist()
def get_latest_serial_no(so_detail, sales_order, item_code):
    serial_no = frappe.db.sql("""
        SELECT 
            soi.name AS sales_order_item, 
            (SELECT sed.serial_no 
            FROM `tabStock Entry` AS se 
            JOIN `tabStock Entry Detail` AS sed ON se.name = sed.parent
            WHERE sed.item_code = soi.item_code AND se.docstatus = 1
            AND se.work_order = (
                SELECT wo.name 
                FROM `tabWork Order` AS wo 
                WHERE wo.sales_order_item = %s 
                AND wo.status = 'Completed'
                LIMIT 1
            )
            LIMIT 1
        ) AS serial_no
        FROM `tabSales Order` AS so 
        JOIN `tabSales Order Item` AS soi ON soi.parent = so.name
        WHERE so.name = %s AND soi.item_code = %s
    """, (so_detail, sales_order, item_code), as_dict=1)
    return serial_no[0]['serial_no'] if serial_no else None

@frappe.whitelist()
def get_latest_serial_no_new(so_detail, sales_order, item_code):
    try:
        serial_nos = frappe.db.sql("""
            SELECT 
                soi.name AS sales_order_item,
                sed.serial_no AS serial_no
            FROM `tabSales Order` AS so 
            JOIN `tabSales Order Item` AS soi ON soi.parent = so.name
            JOIN `tabWork Order` AS wo ON wo.sales_order_item = soi.name
            JOIN `tabStock Entry` AS se ON se.work_order = wo.name
            JOIN `tabStock Entry Detail` AS sed ON se.name = sed.parent
            WHERE 
                so.name = %s AND soi.item_code = %s AND wo.status = 'Completed' AND se.docstatus = 1
        """, (sales_order, item_code), as_dict=1)
        
        if serial_nos:
            # Collecting all serial numbers
            all_serial_nos = [entry['serial_no'] for entry in serial_nos]
            
            # You can return them as a list or join them into a string
            return ", ".join(all_serial_nos)
        
        return None
    except Exception as e:
        frappe.log_error(message=f"An error occurred: {e}", title="Get Latest Serial Number Error")
        return None
