import frappe

@frappe.whitelist()
def form(firstname, lastname, email, company, city):
    print("Method form()")

    contact = frappe.new_doc("Contact")
    contact.first_name = firstname
    contact.last_name = lastname
    contact.company_name = company
    contact.city = city

    # Append the email to the email_ids child table
    contact.append("email_ids", {
        "email_id": email,
        "is_primary": 1
    })

    contact.save()
    return "success"
