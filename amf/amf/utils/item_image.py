import frappe

@frappe.whitelist()
def update_item_images():
    # Fetch all items
    items = frappe.get_all("Item", filters={"disabled": 0}, fields=["name", "item_code", "image"])

    # Dictionary to store the existence of files
    file_existence_cache = {}

    # List to store items that need updating
    items_to_update = []

    for item in items:
        # Replace '.' with '_' and append '_pic.png'
        filename = (item.item_code.replace(".", "_") + "_pic.png").lower()

        # Construct the file URLs
        file_url = "/files/" + filename
        file_url_pr = "/private/files/" + filename

        # Check if the item's image is already set to the correct file
        if item.image not in [file_url, file_url_pr]:
            # Check if file exists in the cache or the File doctype
            if file_url not in file_existence_cache:
                file_existence_cache[file_url] = frappe.db.exists("File", {"file_url": file_url})
            
            file_exists = file_existence_cache[file_url]
            file_url_to_use = file_url

            if not file_exists:
                if file_url_pr not in file_existence_cache:
                    file_existence_cache[file_url_pr] = frappe.db.exists("File", {"file_url": file_url_pr})
                file_exists = file_existence_cache[file_url_pr]
                file_url_to_use = file_url_pr

            if file_exists:
                # Add the item to the update list
                items_to_update.append({'name': item.name, 'image': file_url_to_use})
    #print(file_existence_cache)
    #print(items_to_update)

    # Bulk update items
    if items_to_update:
        for item in items_to_update:
            print("Updating image for item:", item['name'])
            frappe.db.set_value("Item", item['name'], "image", item['image'])
    
    frappe.db.commit()


def clear_item_images():
    # Fetch all items
    items = frappe.get_all('Item', fields=['name'])

    for item in items:
        # Clear the image field
        frappe.db.set_value('Item', item.name, 'image', None)
        frappe.db.commit()
    print("Clearing done.")
