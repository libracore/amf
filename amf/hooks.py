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

app_include_css = [
    "/assets/amf/css/common.css",
]
app_include_js = [
    "/assets/amf/js/amf_templates.min.js",
    "/assets/amf/js/amf_common.js",
    "/assets/amf/js/common.js",
    "/assets/amf/js/dashboard_chart_colors.js",
]

web_include_css = [
    "/assets/amf/amf-dev.css",
    "/assets/amf/amf.css",
]
# web_include_js = "/assets/amf/js/amf.js"

# Include js in doctype views
doctype_js = {
    "Campaign": "public/js/campaign.js",
    "Contact": "public/js/contact.js",
    "Customer": "public/js/customer.js",
    # Keep both scripts active. A duplicate dict key would silently drop one.
    "Delivery Note": [
        "public/js/delivery_note.js",
    #    "public/js/delivery_note_submit_readiness.js",
    ],
    "Item": "public/js/item.js",
    "Quality Inspection": "public/js/quality_inspection.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    #"Purchase Order": "public/js/doctype/purchase_order_parser_warnings.js",
    "Purchase Receipt": "public/js/purchase_receipt_label.js",
    "Quotation": [
        "public/js/quotation.js",
        "public/js/quotation_sales_order_accessories.js",
    ],
    "Sales Order": [
        "public/js/sales_order.js",
        "public/js/quotation_sales_order_accessories.js",
    ],
    "Stock Entry": "public/js/stock_entry.js",
    "Work Order": "public/js/work_order.js",
}

# Include js in doctype list views
doctype_list_js = {
    "BOM": "public/js/list/bom_list.js",
    "Contact": "public/js/list/contact_list.js",
    "Item": "public/js/list/item_list.js",
    "Work Order": "public/js/list/work_order_list.js",
}

# Document Events
# ---------------

doc_events = {
    "Batch": {
        "autoname": "amf.amf.utils.batch_naming.apply_amf_batch_autoname",
        "after_insert": "amf.amf.utils.barcode.after_insert_handler",
    },
    "Bin": {
        "on_update": "amf.amf.utils.bin_bom_sync.sync_item_bom_stock_qty_on_bin_update",
    },
    "BOM": {
        "before_save": [
            "amf.amf.utils.bom_updating.bom_before_save",
            "amf.amf.utils.bom_child_bom_resolver.apply_item_default_boms_to_rows",
        ],
        "on_submit": "amf.amf.utils.bom_mgt.update_item_from_default_bom",
        "on_cancel": "amf.amf.utils.bom_mgt.update_item_from_default_bom",
        "on_update_after_submit": "amf.amf.utils.bom_mgt.update_item_from_default_bom",
    },
    "Contact": {
        "autoname": "amf.master_crm.naming.contact_autoname",
        "before_save": "amf.master_crm.contact.before_save",
        "validate": "amf.master_crm.contact.validate",
    },
    "Customer": {
        "validate": "amf.master_crm.customer_marketing.apply_customer_marketing_values",
    },
    "Customer Satisfaction Survey": {
        "after_insert": [
            "amf.master_crm.doctype.customer_satisfaction_survey.customer_satisfaction_survey.update_contact_csat_nps",
        ],
    },
    "Delivery Note": {
        "before_save": [
            "amf.amf.utils.delivery_note_api.before_save_dn",
        ],
        "before_update_after_submit": "amf.amf.utils.delivery_note_api.preserve_submitted_customs_identifiers",
        "after_insert": [
            "amf.amf.utils.delivery_note_api.auto_gen_qa_inspection",
            "amf.amf.doctype.loan_order.loan_order.update_linked_loan_order",
        ],
        "before_submit": "amf.amf.utils.delivery_note_api.check_qa_inspections_status",
        "on_submit": "amf.amf.doctype.loan_order.loan_order.update_linked_loan_order",
        "on_cancel": "amf.amf.doctype.loan_order.loan_order.update_linked_loan_order",
    },
    "Item": {
        "onload": "amf.amf.utils.item_costing.populate_item_batch_costing_table",
        "before_insert": "amf.amf.utils.item_batch_setup.apply_batch_tracking_rule",
        "validate": [
            "amf.amf.utils.item_batch_setup.apply_batch_tracking_rule",
            "amf.amf.utils.bom_mgt.sync_item_bom_fields",
            "amf.amf.utils.item_reporting.apply_item_reporting_fields",
        ],
        "after_insert": [
            "amf.amf.utils.custom.qr_code_to_document",
            "amf.amf.utils.item_batch_setup.ensure_default_batch_for_item",
        ],
        "on_update": "amf.amf.utils.item_batch_setup.ensure_default_batch_for_item",
    },
    "Lead": {
        "after_insert": [
            "amf.amf.utils.lead_customization.create_address_from_lead",
            "amf.amf.utils.lead_customization.create_contact_from_lead",
        ],
    },
    "Purchase Invoice": {
        "validate": "amf.amf.utils.purchase_invoice.apply_default_cost_center",
    },
    "Purchase Receipt": {
        "before_submit": "amf.amf.utils.purchase_receipt.assign_supplier_batches",
        "on_submit": [
            "amf.amf.utils.purchase_receipt.generate_qa_for_purchase_receipt",
            "amf.amf.utils.safety_stock_check.update_purchase_item_lead_times_from_receipt",
        ],
    },
    "Sales Order": {
        "on_submit": "amf.master_crm.customer_marketing.sync_customer_marketing_from_sales_order",
        "on_cancel": "amf.master_crm.customer_marketing.sync_customer_marketing_from_sales_order",
        "on_update_after_submit": "amf.master_crm.customer_marketing.sync_customer_marketing_from_sales_order",
    },
    "Project": {
        "before_insert": "amf.amf.utils.project_id.assign_project_id",
    },
    "Referral Satisfaction Survey": {
        "after_insert": [
            "amf.master_crm.doctype.referral_satisfaction_survey.referral_satisfaction_survey.update_contact_csat_nps",
        ],
    },
    "Serial No": {
        "after_insert": [
            "amf.amf.utils.custom.qrcode_serial_no",
        ],
    },
    "Stock Ledger Entry": {
        "on_submit": "amf.amf.utils.batch_auto_disable.queue_batch_disabled_state_sync",
    },
    "Stock Entry": {
        "onload": "amf.amf.utils.stock_entry.stock_entry_onload",
        "validate": "amf.amf.utils.stock_entry.stock_entry_validate",
        # Order matters: enrich values first, then apply stock/rate override.
        "before_save": [
            "amf.amf.utils.stock_entry.stock_entry_before_save",
            "amf.amf.utils.work_order_scrap.prepare_dynamic_usage_scrap_rows",
            "amf.amf.utils.stock_entry.get_stock_and_rate_override",
        ],
        "before_submit": [
            "amf.amf.utils.work_order_scrap.prepare_dynamic_usage_scrap_rows",
            "amf.amf.utils.stock_entry.stock_entry_before_submit",
        ],
        "on_submit": [
            "amf.amf.utils.custom.qr_code_to_document",
            "amf.amf.utils.stock_entry.check_rates_and_assign_on_submit",
            "amf.amf.utils.safety_stock_check.update_manufactured_item_lead_time_from_stock_entry",
            "amf.amf.doctype.loan_order.loan_order.update_linked_loan_order",
        ],
        "on_cancel": "amf.amf.doctype.loan_order.loan_order.update_linked_loan_order",
    },
    "Timer Production": {
        "before_save": "amf.amf.doctype.timer_production.timer_production.timer_before_save",
    },
    "Work Order": {
        "after_insert": "amf.amf.utils.on_work_order_submit.generate_wo_qr",
    },

    # "Sales Invoice": {
    #     "before_save": "amf.amf.utils.sales_invoice.validate_swiss_tva_on_sales_invoice"
    # },
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "hourly": [
        "amf.amf.amf.doctype.timer_production.timer_production.send_timer_alert",
    ],
    "daily": [
        "amf.amf.utils.batch_auto_disable.sync_all_batch_disabled_states",
        "amf.amf.utils.item_image.update_item_images",
        "amf.amf.utils.capacity.update_capacity_utilization_rate",
        "amf.www.tracking.fetch_and_display_tracking_info_enqueue",
        "amf.master_crm.doctype.gravity_forms.gravity_forms.daily_sync",
        "amf.amf.utils.work_order_creation.create_work_orders_based_on_reorder_levels",
        "amf.amf.utils.work_order_creation.plan_machining_work_orders_from_sales_orders",
        "amf.master_crm.organization.update_global_csat",
    ],
    # "hourly": ["amf.amf.utils.document_notification.update_purchase_orders"],
    "weekly": [
        "amf.amf.utils.safety_stock_check.run_weekly_stock_level_update",
        "amf.master_crm.contact.update_contact_statuses",
        "amf.master_crm.contact.update_organization_flags",
        # "amf.amf.utils.bom_mgt.execute_db_enqueue",
        "amf.master_crm.doctype.global_satisfaction_score.global_satisfaction_score.calculate_global_scores",
        "amf.amf.utils.item_mgt.update_all_item_valuation_rates_enq",
        "amf.amf.utils.cleaning.enqueue_log_cleanup",
    ],
    "monthly_long": [
        "amf.amf.utils.bom_hierarchy_sync.enqueue_sync_latest_bom_hierarchy_for_all_items",
        #"amf.amf.utils.monthly_operations_report.generate_previous_month_report",
    ],
}

# Override Methods
# ------------------------------
override_whitelisted_methods = {
    "frappe.desk.form.save.savedocs": "amf.amf.utils.delivery_note_save.savedocs",
}

# override_whitelisted_methods.update({
#     "frappe.desk.doctype.event.event.get_events": "amf.event.get_events"
# })
override_doctype_dashboards = {
    "Delivery Note": "amf.amf.utils.dashboards.modify_dn_dashboard",
    "Issue": "amf.amf.utils.dashboards.modify_issue_dashboard",
    "Sales Order": "amf.amf.utils.dashboards.modify_so_dashboard",
}

after_install = "amf.amf.utils.project_id.after_install"

# Migration Hook
# --------------
after_migrate = [
    "amf.master_crm.migration.translate_customer_to_organization",
    "amf.master_crm.customer_marketing.sync_customer_marketing_custom_fields",
    "amf.amf.utils.project_id.sync_project_id_customization",
    "amf.amf.utils.loan_order_setup.sync_loan_order_custom_fields",
    "amf.amf.utils.batch_auto_disable.sync_batch_auto_disable_custom_fields",
    "amf.amf.utils.batch_naming.sync_supplier_batch_custom_fields",
    "amf.amf.utils.item_reporting.sync_item_reporting_custom_fields",
    "amf.amf.utils.quotation_product_definition.sync_quotation_product_definition_custom_fields",
    "amf.amf.utils.work_order_scrap.sync_work_order_usage_scrap_custom_fields",
    "amf.amf.utils.kpi_dashboard.sync_supply_chain_manufacturing_dashboard",
]
