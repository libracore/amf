import frappe

def update_contact_status():
    try:
        # Define the statuses to exclude
        excluded_statuses = ["Back-Office", "Supplier", "AMF", "Distributor"]
        
        # Fetch contacts excluding specified statuses
        contacts = frappe.get_all(
            "Contact",
            filters={"status": ["not in", excluded_statuses]},
            fields=["name", "status"]
        )

        if not contacts:
            frappe.msgprint("No contacts found with the specified statuses.")
            return

        updated_contacts = []

        for contact in contacts:
            try:
                # Check for sales orders associated with the contact
                sales_orders_exist = frappe.get_value("Sales Order", {"contact_person": contact.name, "docstatus": 1}, "name")

                # Check for quotations only if no sales orders are found
                quotes_exist = None
                if not sales_orders_exist:
                    quotes_exist = frappe.get_value("Quotation", {"contact_person": contact.name, "docstatus": 1}, "name")

                # Update contact status based on findings
                if sales_orders_exist:
                    print(f"Sales order found: {sales_orders_exist} for contact: {contact.name} > Status: 'Customer'")
                    frappe.db.set_value("Contact", contact.name, "status", "Customer")
                    updated_contacts.append((contact.name, "Customer"))
                elif quotes_exist:
                    print(f"Quote found: {sales_orders_exist} for contact: {contact.name} > Status: 'Prospect'")
                    frappe.db.set_value("Contact", contact.name, "status", "Prospect")
                    updated_contacts.append((contact.name, "Prospect"))
                else:
                    print(f"No DocType found for contact: {contact.name}")

            except Exception as e:
                frappe.log_error(f"Error processing contact {contact.name}: {str(e)}", "Contact Status Update Error")

        # Commit transaction after processing all contacts
        frappe.db.commit()

        # Display a message with update results
        if updated_contacts:
            update_message = "\n".join([f"Contact {name} updated to {status}" for name, status in updated_contacts])
            frappe.msgprint(f"Updated contacts:\n{update_message}")
        else:
            frappe.msgprint("No contacts were updated.")

    except Exception as e:
        frappe.log_error(f"Error in update_contact_status: {str(e)}", "Contact Status Update Error")
        frappe.throw(f"An error occurred during the update: {str(e)}")

def update_contact_products():
    try:
        # Fetch all contacts
        contacts = frappe.get_all("Contact", fields=["name"])

        if not contacts:
            frappe.msgprint("No contacts found.")
            return

        for contact in contacts:
            try:
                # Fetch submitted Sales Orders for the contact
                sales_orders = frappe.get_all("Sales Order", {"contact_person": contact.name, "docstatus": 1}, ["name"])

                if not sales_orders:
                    continue  # Skip if no new sales orders for this contact

                # Dictionary to store cumulative item quantities
                item_quantities = {}

                # Collect item quantities across all sales orders
                for so in sales_orders:
                    sales_order_items = frappe.get_all("Sales Order Item", {"parent": so.name}, ["item_code", "qty"])

                    # Accumulate quantities by item_code
                    for item in sales_order_items:
                        item_code = item["item_code"]
                        item_quantities[item_code] = item_quantities.get(item_code, 0) + item["qty"]
                        print(item_quantities, "for contact:", contact.name)

                # Update the 'contact_product' child table
                for item_code, qty in item_quantities.items():
                    # Check if item_code already exists in the contact's product table
                    existing_product = frappe.get_value("contact_product", {"parent": contact.name, "parentfield": "products", "item_code": item_code}, ["name", "quantity"])

                    if existing_product:
                        # Update the existing row's quantity
                        new_qty = existing_product[1] + qty  # `quantity` is second in `existing_product`
                        frappe.db.set_value("contact_product", existing_product[0], "quantity", new_qty)
                    else:
                        # Add a new row in the contact's product child table
                        contact_doc = frappe.get_doc("Contact", contact.name)
                        contact_doc.append("products", {
                            "item_code": item_code,
                            "quantity": qty
                        })
                        contact_doc.save(ignore_permissions=True)

                frappe.msgprint(f"Contact products updated for {contact.name}.")

            except Exception as e:
                frappe.log_error(f"Error updating contact products for {contact.name}: {str(e)}", "Contact Product Update Error")

        frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"Error in update_contact_products: {str(e)}", "Contact Product Update Error")
        frappe.throw(f"An error occurred during the update: {str(e)}")

