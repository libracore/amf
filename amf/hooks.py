# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "amf"
app_title = "AMF"
app_publisher = "libracore AG"
app_description = "ERP applications and tools for AMF"
app_icon = "octicon octicon-file-directory"
app_color = "#2b47d9"
app_email = "info@libracore.com"
app_license = "AGPL"

# Include in <head>
# ------------------

app_include_css = ["/assets/amf/css/common.css"]
app_include_js = [
    "/assets/amf/js/amf_templates.min.js",
    "/assets/amf/js/amf_common.js",
    "/assets/amf/js/common.js"
]

web_include_css = [
    "/assets/amf/amf-dev.css",
    "/assets/amf/amf.css"
]
# web_include_js = "/assets/amf/js/amf.js"

# Include js in doctype views
doctype_js = {
    "Contact": "public/js/contact.js",
    "Customer": "public/js/customer.js",
    "Quotation": "public/js/quotation.js",
    "Sales Order": "public/js/sales_order.js",
    "Delivery Note": "public/js/delivery_note.js",
    "Campaign": "public/js/campaign.js"
}

# Include js in doctype list views
doctype_list_js = {
    "Item": ["public/js/list/item_list.js"],
    "Contact": "public/js/list/contact_list.js"
}

# Document Events
# ---------------

doc_events = {
    "Work Order": {
        "on_submit": [
            "amf.amf.utils.custom.qr_code_to_document",
            "amf.amf.utils.on_work_order_submit.on_submit_wo",
        ]
    },
    "Job Card": {
        "on_submit": "amf.amf.utils.custom.qr_code_to_document"
    },
    "Lead": {
        "after_insert": [
            "amf.amf.utils.lead_customization.create_address_from_lead",
            "amf.amf.utils.lead_customization.create_contact_from_lead"
        ]
    },
    "Stock Entry": {
        "before_save": "amf.www.fftest.update_rate_and_availability_ste"
    },
    "Stock Entry": {
        "on_submit": "amf.amf.utils.custom.qr_code_to_document"
    },
    "Production Order": {
        "before_submit": "amf.amf.utils.custom.attach_qr_code_to_document"
    },
    "Batch": {
        "after_insert": "amf.amf.utils.barcode.after_insert_handler"
    },
    "Delivery Note": {
        "before_save": "amf.amf.utils.delivery_note_api.before_save_dn"
    },
    "Serial No": {
        "after_insert": "amf.amf.utils.custom.qrcode_serial_no"
    },
    "Contact": {
        "autoname": "amf.master_crm.naming.contact_autoname",
        "before_save": "amf.master_crm.contact.before_save",
        "validate": "amf.master_crm.contact.validate"
    }
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "amf.amf.utils.item_image.update_item_images",
        "amf.amf.utils.capacity.update_capacity_utilization_rate",
        "amf.www.tracking.fetch_and_display_tracking_info_enqueue",
        "amf.amf.utils.item_master3.update_bom_list_enqueue",
        "amf.master_crm.doctype.gravity_forms.gravity_forms.daily_sync"
    ]
    # "hourly": ["amf.amf.utils.document_notification.update_purchase_orders"],
    # "weekly": [
    #     "amf.amf.utils.check_issue.fetch_open_issues",
    #     "amf.amf.utils.safety_stock_check.check_stock_levels",
    #     "amf.amf.utils.forecast.get_item_details_and_quantities"
    # ]
}

# Override Methods
# ------------------------------
# override_whitelisted_methods = {
#     "frappe.desk.doctype.event.event.get_events": "amf.event.get_events"
# }
# override_doctype_dashboards = {
#     "Task": "amf.task.get_dashboard_data"
# }

# Migration Hook
# --------------
# after_migrate = ['amf.master_crm.migration.translate_customer_to_organization']
