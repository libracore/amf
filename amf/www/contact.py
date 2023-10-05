import frappe

@frappe.whitelist(allow_guest=True)
def form(firstname, lastname, email, company, city, from_conf, comments):
    print("Method form()")
    print(firstname)
    contact = frappe.new_doc("Contact")
    if firstname is "":
       firstname = "/"
    contact.first_name = firstname
    contact.last_name = lastname
    contact.company_name = company
    contact.city = city
    contact.from_conf = from_conf
    contact.comments = comments

    # Append the email to the email_ids child table
    contact.append("email_ids", {
        "email_id": email,
        "is_primary": 1
    })

    contact.save()
    return "success"