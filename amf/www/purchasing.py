import frappe

@frappe.whitelist()
def search_suppliers(query):
    # Perform a search query against the Supplier doctype
    suppliers = frappe.get_all('Supplier',
                               filters={'name': ['like', '%{}%'.format(query)]},
                               fields=['name'])
    return suppliers
