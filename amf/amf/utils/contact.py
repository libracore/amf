import csv
import os
import frappe

def update_or_create_contacts_from_csv():
    # Fetch the file content using the file URL
    site_path = frappe.get_site_path('private', 'files', 'contact.csv')
    
    # Check if the file exists
    if not os.path.exists(site_path):
        frappe.throw(f"File {site_path} does not exist.")
    
    with open(site_path, mode='r', encoding='utf-8') as infile:
        # Parse the CSV content using the CSV reader
        csv_reader = csv.DictReader(infile)
        
        # Get the meta information for the Contact doctype
        contact_meta = frappe.get_meta('Contact')
        
        # Iterate over each row in the CSV file
        for row in csv_reader:
            # Create a dictionary from the CSV row
            contact_data = {}
            for fieldname, value in row.items():
                contact_data[fieldname] = value

            # Search for existing contact by email
            email = contact_data.get('email_id')
            existing_contact = frappe.db.exists("Contact", {"email_id": email})
                
            if existing_contact:
                print(f"Updating existing contact: {existing_contact}")
                # Update the existing contact
                contact = frappe.get_doc("Contact", existing_contact)
                # Loop through the contact_data dictionary to update fields
                for column, value in contact_data.items():
                    if value:
                        try:
                            setattr(contact, column, value)
                        except Exception as e:
                            print(e)
                    contact.save(ignore_permissions=True)
            else:
                print(f"Creating new contact for email: {email}")
                new_contact = frappe.new_doc("Contact")
                # Loop through the contact_data dictionary to set values
                for column, value in contact_data.items():
                    print(column, value)
                    if contact_meta.has_field(column):
                        if value:
                            try:
                                setattr(new_contact, column, str(value))
                            except Exception as e:
                                print(e)
                        else:
                            print(f"Field '{column}' does not exist in the Contact doctype. Skipping this field.")
                # Insert the new contact
                try:
                    new_contact.insert(ignore_permissions=True)
                except Exception as e:
                    print(e)
                        
            
            frappe.db.commit()    