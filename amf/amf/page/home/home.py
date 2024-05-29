# amf/amf/page/home.py

import frappe

@frappe.whitelist()
def get_web_pages():
    web_pages = frappe.get_all('Web Page',filters={'published': '1'}, fields=['title', 'route', 'name'])
    return web_pages
