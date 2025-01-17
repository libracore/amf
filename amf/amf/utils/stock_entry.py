import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


def batch_to_stock_entry(doc, method=None):
    print("Entering batch_to_stock_entry...")
    # Check if the purpose of the stock entry is 'Manufacture'
    if doc.purpose == "Manufacture" and doc.items:
        # Get the last item in the stock entry's items list
        last_item = doc.items[-1]
        # Fetch the 'has_batch_no' attribute for the item
        has_batch_no = frappe.db.get_value(
            "Item", last_item.item_code, "has_batch_no")
        # If the item has a batch number
        if has_batch_no:
            # Generate the batch_id using the given format
            batch_id = f"{last_item.item_code} {doc.posting_date} {doc.work_order} {int(doc.fg_completed_qty)}"
            print(batch_id)
            # Create a new Batch entry
            new_batch = frappe.get_doc(
                {"doctype": "Batch", "item": last_item.item_code, "batch_id": batch_id}
            ).insert()

            # Update the batch_no of the last item with the newly created batch's name
            last_item.batch_no = new_batch.name

        # Save the document changes (since we updated the batch_no)
        # doc.save()
    print("Ending batch_to_stock_entry...")


# def call_get_stock_and_rate_for_all():
#     # Fetch all Stock Entry names
#     stock_entries = frappe.get_list("Stock Entry", fields=["name"])

#     # Test Input
#     stock_entries = frappe.get_list("Stock Entry", filters={"name": "STE-04342"}, fields=["name"])

#     for entry in stock_entries:
#         # Get the Stock Entry document
#         stock_entry_doc = frappe.get_doc("Stock Entry", entry.get("name"))
#         print(f"Stock Entry: {stock_entry_doc.name}")
#         # Call the get_stock_and_rate method
#         stock_entry_doc.get_stock_and_rate()

#         # Save the Stock Entry to update changes
#         stock_entry_doc.save(ignore_permissions=True)  # Adding ignore_permissions based on your role & privileges

#         # Print the details (customize as per your requirement)
#         print(f"Stock Entry: {stock_entry_doc.name}, Rate and Stock Updated")

@frappe.whitelist()
def get_batch_item_qty_per_warehouse(item_code=None):
    """
        Returns a list of dictionaries showing the warehouse
        and the net quantity (sum of actual_qty) of a specific item
        from all batches in each warehouse using
        tabStock Ledger Entry (SLE).

        :param item_code: The Item Code whose quantity is being queried.
        :return:          A list of dicts, e.g.:
                          [
                              {"warehouse": "Stores - A", "batch_no": "BATCH001", "total_qty": 50.0},
                              {"warehouse": "Stores - B", "batch_no": "BATCH002", "total_qty": -10.0}
                          ]
                          where total_qty is the net result of actual_qty
                          from all matching entries.
        """
    if not item_code:
        item_code = '100024'
    data = frappe.db.sql(
        """
            SELECT
                sle.warehouse AS warehouse,
                sle.batch_no AS batch_no,
                SUM(sle.actual_qty) AS total_qty
            FROM `tabStock Ledger Entry` as sle
            JOIN `tabBatch` as b ON b.name = sle.batch_no
            WHERE item_code = %(item_code)s
            AND b.disabled = 0
            GROUP BY sle.warehouse, sle.batch_no
            ORDER BY sle.warehouse, sle.batch_no
            """,
        {"item_code": item_code},
        as_dict=True
    )

    return data

@frappe.whitelist()
def get_sub_bom_items(item_code=None, include_top_level=True):
    """
    Fetch the item codes of all sub-BOMs recursively for a given item_code.

    Args:
        item_code (str): The item code to fetch BOM and sub-BOMs for.
        include_top_level (bool): Whether to include the given item_code in the results. Default is True.

    Returns:
        dict: A dictionary where keys are BOM names and values are lists of item codes.
    """
    if not item_code:
        item_code = '300024'
    result = {}
    isolated_items = []

    def fetch_bom_items(bom_name):
        """Fetch items from a BOM and process sub-BOMs recursively."""
        # Fetch all BOM items
        bom_items = frappe.get_all(
            "BOM Item",
            fields=["item_code", "bom_no"],
            filters={"parent": bom_name, "docstatus": 1},
        )

        # Store items for this BOM
        result[bom_name] = []

        for item in bom_items:
            result[bom_name].append(item.item_code)
            # Stop if the 2nd digit of item_code is '0'
            if len(item.item_code) > 1 and item.item_code[1] == '0':
                isolated_items.append(item.item_code)
                continue
            # If the item has a sub-BOM, process it recursively
            if item.bom_no:
                fetch_bom_items(item.bom_no)

    # Fetch the main BOM for the item
    main_bom = frappe.get_value(
        "BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")
    if not main_bom:
        frappe.throw(f"No active default BOM found for Item: {item_code}")

    if include_top_level:
        result[main_bom] = [item_code]

    # Process the main BOM
    fetch_bom_items(main_bom)

    all_batch_data = {}

    for item in isolated_items:
        batch_data = get_batch_item_qty_per_warehouse(item)
        filtered_data = [entry for entry in batch_data if entry["total_qty"] != 0]
        if filtered_data:
            #print(filtered_data)
            all_batch_data[item] = filtered_data

    return isolated_items, all_batch_data

@frappe.whitelist()
def get_bom_batches(item_code):
    """
    Fetch plug and seat batch numbers for the given item_code from recursive BOM.

    Args:
        item_code (str): Item code to fetch batches for.

    Returns:
        dict: {
            "plug_batches": List of plug batch numbers,
            "seat_batches": List of seat batch numbers
        }
    """
    _, isolated_items = get_sub_bom_items(item_code)
    plug_batches = []
    seat_batches = []
    for item in isolated_items:
        batch_data = get_batch_item_qty_per_warehouse(item)
        for entry in batch_data:
            if entry["total_qty"] > 0 and entry["warehouse"] != 'Scrap - AMF21':
                print(entry)
                if item.startswith("1"):
                    plug_batches.append(entry["batch_no"])
                elif item.startswith("2"):
                    seat_batches.append(entry["batch_no"])

    return {
        "plug_batches": plug_batches,
        "seat_batches": seat_batches
    }
