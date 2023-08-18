import frappe

def create_address_from_lead(doc, method):
    if doc.is_new():  # Check if the Lead is being submitted
        # Fetch the required fields from the Lead DocType
        # lead_name = doc.lead_name
        # You can fetch more fields if needed
        # Create a new Address
        address = frappe.new_doc("Address")
        address.address_title = doc.company_name
        address.address_type = "Office"
        address.address_line1 = doc.address_line_1_contact
        address.address_line2 = doc.address_line_2_contact
        address.pincode = doc.postal_code_contact
        address.city = doc.city_town_contact
        address.county = doc.county_state_contact
        address.country = doc.country_contact
        address.email_id = doc.email
        address.phone = doc.mobile_no
        address.is_primary_address = 1
        
        # Map more fields from Lead to Address as required
        # For example:
        # address.address_line1 = doc.lead_address_line
        # address.city = doc.lead_city
        # ...and so on

        # Save the new Address
        address.insert()

def create_contact_from_lead(doc, method):
    if doc.is_new():
        # Create a new Contact
        contact = frappe.new_doc("Contact")
        contact.first_name = doc.first_contact_name
        contact.last_name = doc.last_contact_name
        contact.email_id = doc.email
        contact.salutation = doc.salutation
        contact.mobile_no = doc.mobile_no
        contact.company_name = doc.company_name

        # Add the email to the child table in Contact
        contact_detail = contact.append('email_ids', {})  # 'contact_details' is the fieldname of the child table
        contact_detail.email_id = doc.email
        contact_detail.is_primary = 1

        # Save the new Contact
        contact.insert()