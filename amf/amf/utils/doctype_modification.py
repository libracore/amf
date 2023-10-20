import frappe

def modify_all_doctypes():
    # Fetch all DocTypes
    all_doctypes = frappe.get_all("DocType", fields=["name"])

    # Loop through each DocType and modify it
    for doctype in all_doctypes:
        doctype_name = doctype.get("name")
        doc = frappe.get_doc("DocType", doctype_name)
        print(doctype_name)
        # Set the track_seen and track_changes attributes to 1 (True)
        if(doc.track_seen == 0):
            print("Set doc.track_seen.")
            doc.track_seen = 1
        if(doc.track_changes == 0):
            print("Set doc.track_changes.")
            doc.track_changes = 1

        # Save the modified DocType
        doc.save()

# Execute the function
modify_all_doctypes()
