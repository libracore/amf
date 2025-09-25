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
    "Campaign": "public/js/campaign.js",
    "Item": "public/js/item.js",
    "Work Order": "public/js/work_order.js",
    "Quality Inspection": "public/js/quality_inspection.js",
}

# Include js in doctype list views
doctype_list_js = {
    "Item": "public/js/list/item_list.js",
    "Contact": "public/js/list/contact_list.js",
    "Work Order": "public/js/list/work_order_list.js",
    "BOM": "public/js/list/bom_list.js",
}

# Document Events
# ---------------

doc_events = {
    "Work Order": {
        "on_submit": [
            "amf.amf.utils.custom.qr_code_to_document",
        ]
    },
    "Lead": {
        "after_insert": [
            "amf.amf.utils.lead_customization.create_address_from_lead",
            "amf.amf.utils.lead_customization.create_contact_from_lead"
        ]
    },
    "Stock Entry": {
        "onload": "amf.amf.utils.stock_entry.stock_entry_onload",
        "validate": "amf.amf.utils.stock_entry.stock_entry_validate",
        "before_submit": "amf.amf.utils.stock_entry.stock_entry_before_submit",
        "before_save": "amf.amf.utils.stock_entry.stock_entry_before_save",
        "on_submit": [
            "amf.amf.utils.custom.qr_code_to_document",
            "amf.amf.utils.stock_entry.check_rates_and_assign_on_submit",
        ]
    },
    "Batch": {
        "after_insert": "amf.amf.utils.barcode.after_insert_handler"
    },
    "Delivery Note": {
        "before_save": "amf.amf.utils.delivery_note_api.before_save_dn"
    },
    "Delivery Note": {
        "after_insert": "amf.amf.utils.delivery_note_api.auto_gen_qa_inspection"
    },
    "Serial No": {
        "after_insert": [
            "amf.amf.utils.custom.qrcode_serial_no",
        ]
    },
    "Contact": {
        "autoname": "amf.master_crm.naming.contact_autoname",
        "before_save": "amf.master_crm.contact.before_save",
        "validate": "amf.master_crm.contact.validate"
    },
    "Item": {
        "after_insert": "amf.amf.utils.custom.qr_code_to_document"
    },
    "Customer Satisfaction Survey": {
        "after_insert": [
            "amf.master_crm.doctype.customer_satisfaction_survey.customer_satisfaction_survey.update_contact_csat_nps"
        ]  
    },
    "Referral Satisfaction Survey": {
        "after_insert": [
            "amf.master_crm.doctype.referral_satisfaction_survey.referral_satisfaction_survey.update_contact_csat_nps"
        ]  
    },
    "BOM": {
        "before_save": "amf.amf.utils.bom_updating.bom_before_save",
        "validate": "amf.amf.utils.bom_child_bom_resolver.apply_item_default_boms_to_rows"
    }
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "amf.amf.utils.item_image.update_item_images",
        "amf.amf.utils.capacity.update_capacity_utilization_rate",
        "amf.www.tracking.fetch_and_display_tracking_info_enqueue",
        "amf.master_crm.doctype.gravity_forms.gravity_forms.daily_sync",
        "amf.amf.utils.bom_mgt.execute_scheduled",
        "amf.amf.utils.work_order_creation.create_work_orders_based_on_reorder_levels",
        "amf.master_crm.organization.update_global_csat"
    ],
    # "hourly": ["amf.amf.utils.document_notification.update_purchase_orders"],
    "weekly": [
        "amf.master_crm.contact.update_contact_statuses",
        "amf.master_crm.contact.update_organization_flags",
        "amf.amf.utils.bom_mgt.execute_db_enqueue",
        "amf.master_crm.doctype.global_satisfaction_score.global_satisfaction_score.calculate_global_scores",
        "amf.amf.utils.item_mgt.update_all_item_valuation_rates_enq",
        "amf.amf.utils.cleaning.enqueue_log_cleanup",
    ],
}

# Override Methods
# ------------------------------
# override_whitelisted_methods = {
#     "frappe.desk.doctype.event.event.get_events": "amf.event.get_events"
# }
override_doctype_dashboards = {
    "Delivery Note": "amf.amf.utils.dashboards.modify_dn_dashboard"
}

# Migration Hook
# --------------
after_migrate = ['amf.master_crm.migration.translate_customer_to_organization']
