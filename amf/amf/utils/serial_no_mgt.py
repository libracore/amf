import frappe
from frappe.model.rename_doc import rename_doc

@frappe.whitelist()
def rename_serial_nos_enqueue():
    frappe.enqueue("amf.amf.utils.serial_no_mgt.rename_serial_nos_for_522100_via_sql", queue='long', timeout=15000)
    return None

def rename_serial_nos_for_522100_via_sql():
    """
    1) Use raw SQL to fetch Serial Nos for item_code='522100' where
       the numeric portion of the name (after 'P221-O') is between 4230 and 4509.
    2) Rename them to '522100-0000xxxx' format, incrementing from 775 to 1054.
    3) Use rename_doc to properly update references, then commit once.
    """
    old_start_num = 4230
    old_end_num   = 4509
    new_start_num = 775

    # The numeric portion we want is everything after 'P221-O', 
    # i.e. SUBSTRING(name, 7), because:
    #   P221-O00004230
    #   ^    ^ 
    #   1    6
    # => The '0' at position #7 is the start of the numeric block "00004230"
    query = """
        SELECT name
        FROM `tabSerial No`
        WHERE item_code = '522100'
          AND name LIKE 'P221-O%%'
          AND CAST(SUBSTRING(name, 7) AS UNSIGNED) BETWEEN %s AND %s
    """

    serial_nos = frappe.db.sql(
        query,
        (old_start_num, old_end_num),
        as_dict=True
    )
    print(serial_nos)

    for row in serial_nos:
        old_name = row["name"]
        # Extract numeric portion (e.g. 'P221-O00004230' -> '00004230')
        numeric_str = old_name[6:]  # since index 6 is the '0' after "P221-O", zero-based in Python
        old_num = int(numeric_str)   # => 4230

        offset  = old_num - old_start_num
        new_num = new_start_num + offset

        # Build new name, e.g. '522100-00000775'
        new_name = f"522100-{new_num:08d}"
        print(new_name)

        # Use rename_doc to properly update references and underlying links
        rename_doc("Serial No", old_name, new_name, force=False, merge=False)

        # Commit once at the end
        frappe.db.commit()
