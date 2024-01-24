import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry


def batch_to_stock_entry(doc, method=None):
    print("Entering batch_to_stock_entry...")
    # Check if the purpose of the stock entry is 'Manufacture'
    if doc.purpose == "Manufacture" and doc.items:
        # Get the last item in the stock entry's items list
        last_item = doc.items[-1]
        # Fetch the 'has_batch_no' attribute for the item
        has_batch_no = frappe.db.get_value("Item", last_item.item_code, "has_batch_no")
        # If the item has a batch number
        if has_batch_no:
            # Generate the batch_id using the given format
            batch_id = f"{last_item.item_code} • {doc.posting_date} • {doc.work_order} • {int(doc.fg_completed_qty)}"
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
