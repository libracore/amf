import csv
from inspect import getfile
import os
import frappe
import pandas as pd
from tqdm import tqdm  # Import the tqdm library for the progress bar
import logging

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

def read_csv_to_dict(file_path):
    """
    Reads a CSV file, cleans the data, and converts it into a list of dictionaries.
    
    :param file_path: Path to the CSV file.
    :return: List of dictionaries, each representing a cleaned row.
    """
    try:
        # Get the full path to the file using Frappe's API
        full_path = frappe.get_site_path('private', 'files', 'contact.csv')
        
        # Read the CSV file into a pandas DataFrame
        df = pd.read_csv(full_path, encoding='utf-8')
        
        # Clean the DataFrame by replacing NaN values with empty strings
        df = df.fillna('')

        # Convert the cleaned DataFrame into a list of dictionaries
        data_list = df.to_dict(orient='records')

        return data_list
    
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return []
    except pd.errors.EmptyDataError:
        print("Error: No data found in the CSV file.")
        return []
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return []


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_value(value):
    """
    Helper function to replace 'nan' or non-string values with an empty string.
    
    :param value: The value to check.
    :return: Cleaned value (either the original value if valid or an empty string).
    """
    return "" if pd.isna(value) or not isinstance(value, str) else value

def get_contact_by_email(email):
    """
    Fetches a contact from ERPNext by email.

    :param email: The email to search for.
    :return: The contact document or None if not found.
    """
    contacts = frappe.get_all("Contact", filters={"email_id": email}, fields=["name", "email_id"])
    if contacts:
        return frappe.get_doc("Contact", contacts[0]["name"])
    return None

def create_new_contact(row_data):
    """
    Creates a new contact with data from the row.

    :param row_data: Dictionary containing contact information.
    :return: The newly created contact document.
    """
    contact_doc = frappe.get_doc({
        "doctype": "Contact",
        "first_name": clean_value(row_data.get('first_name')),
        "last_name": clean_value(row_data.get('last_name')),
        "email_ids": [{
            "doctype": "Contact Email",
            "email_id": clean_value(row_data.get('email')),
            "is_primary": 1
        }],
        'country': clean_value(row_data.get('country')),
        'company_name': clean_value(row_data.get('company_name')),
        'status': clean_value(row_data.get('status')),
        'deliverability': clean_value(row_data.get('deliverability')),
        'deliverability_type': clean_value(row_data.get('deliverability_type')),
        'gdpr_compliant': row_data.get('gdpr_compliant', False),
        'subscribed_to_newsletter': row_data.get('subscribed_to_newsletter', False),
        'source': clean_value(row_data.get('source')),
        'from_source': clean_value(row_data.get('from_source')),
        'customer_group': clean_value(row_data.get('customer_group')),
        'subscription_date': '2024-10-01' if row_data.get('subscribed_to_newsletter') else '',
        'filled_in_on': '2024-10-01' if row_data.get('gdpr_compliant') else ''
    })
    contact_doc.insert()
    #logging.info(f"New contact {contact_doc.name} created successfully.")
    return contact_doc

def update_contact(contact_doc, row_data):
    """
    Updates an existing contact with new data from the row.

    :param contact_doc: The contact document to update.
    :param row_data: Dictionary containing updated contact information.
    """
    contact_doc.update({
        'first_name': clean_value(row_data.get('first_name')),
        'last_name': clean_value(row_data.get('last_name')),
        'country': clean_value(row_data.get('country')),
        'company_name': clean_value(row_data.get('company_name')),
        'status': clean_value(row_data.get('status')),
        'deliverability': clean_value(row_data.get('deliverability')),
        'deliverability_type': clean_value(row_data.get('deliverability_type')),
        'gdpr_compliant': row_data.get('gdpr_compliant', False),
        'subscribed_to_newsletter': row_data.get('subscribed_to_newsletter', False),
        'source': clean_value(row_data.get('source')),
        'from_source': clean_value(row_data.get('from_source')),
        'customer_group': clean_value(row_data.get('customer_group')),
        'subscription_date': '2024-10-01' if row_data.get('subscribed_to_newsletter') else '',
        'filled_in_on': '2024-10-01' if row_data.get('gdpr_compliant') else ''
    })
    contact_doc.save()
    #logging.info(f"Contact {contact_doc.name} updated successfully.")

def find_or_create_contact(row_data):
    """
    Finds a contact by email or creates a new one if not found.
    
    :param row_data: Dictionary containing the contact information.
    """
    email = clean_value(row_data.get('email'))
    if not email:
        logging.error("Email not found in row data. Skipping row.")
        return

    try:
        contact_doc = get_contact_by_email(email)
        if contact_doc:
            update_contact(contact_doc, row_data)
        else:
            create_new_contact(row_data)
    
    except Exception as e:
        logging.error(f"Error while processing contact with email {email}: {e}")

def process_csv_contacts():
    """
    Main function to process CSV contacts. Reads the CSV and either updates
    or creates contacts in ERPNext.
    
    :param file_path: Path to the CSV file.
    """
    file_path = 'private/files/contact_test.csv'
    
    try:
        rows = read_csv_to_dict(file_path)
        if not rows:
            logging.warning("No rows to process.")
            return

        for row in tqdm(rows, desc="Processing Contacts", unit="contact"):
            find_or_create_contact(row)

        logging.info("Contact processing completed.")
    
    except Exception as e:
        logging.error(f"Failed to process contacts from CSV: {e}")

def validate_csv_columns(df, required_columns):
    """
    Validates that the CSV contains all required columns.
    
    :param df: The DataFrame containing the CSV data.
    :param required_columns: List of columns required to process contacts.
    :raises ValueError: If required columns are missing.
    """
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing columns in CSV: {missing_columns}")
    
import frappe

import frappe

def update_contact_status():
    try:
        # Fetch contacts with status different from 'back-office', 'supplier', 'AMF', or 'distributor'
        contacts = frappe.get_all(
            "Contact",
            filters={
                "status": ["not in", ["Back-Office", "Supplier", "AMF", "Distributor"]]
            },
            fields=["name", "status"]  # Add any additional fields you may need
        )

        if not contacts:
            frappe.msgprint("No contacts found with the specified statuses.")
            return

        updated_contacts = []

        for contact in contacts:
            try:
                # Fetch sales orders for the contact first, as we assume most contacts may have sales orders
                sales_orders = frappe.get_all(
                    "Sales Order",
                    filters={"contact_person": contact.name, "docstatus": 1},  # Only submitted sales orders
                    fields=["name"]
                )

                # Fetch quotes for the contact only if no sales orders are found
                quotes = []
                if not sales_orders:
                    quotes = frappe.get_all(
                        "Quotation",
                        filters={"contact_person": contact.name, "docstatus": 1},  # Only submitted quotations
                        fields=["name"]
                    )

                # Update status to 'Customer' if there is at least one sales order
                if sales_orders:
                    print("Customer:", contact.name)
                    frappe.db.set_value("Contact", contact.name, "status", "Customer")
                    updated_contacts.append((contact.name, "Customer"))

                # Update status to 'Prospect' if there are quotes but no sales orders
                elif quotes:
                    print("Prospect:", contact.name)
                    frappe.db.set_value("Contact", contact.name, "status", "Prospect")
                    updated_contacts.append((contact.name, "Prospect"))

            except Exception as e:
                frappe.log_error(f"Error processing contact {contact.name}: {str(e)}", "Contact Status Update Error")

        # Commit transaction after processing all contacts
        frappe.db.commit()

        # Log results
        if updated_contacts:
            message = "\n".join([f"Contact {name} updated to {status}" for name, status in updated_contacts])
            frappe.msgprint(f"Updated contacts:\n{message}")
        else:
            frappe.msgprint("No contacts were updated.")

    except Exception as e:
        frappe.log_error(f"Error in update_contact_status: {str(e)}", "Contact Status Update Error")
        frappe.throw(f"An error occurred during the update: {str(e)}")


