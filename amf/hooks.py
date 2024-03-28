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

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = [
    "/assets/amf/css/common.css",
]
app_include_js = [
    "/assets/amf/js/amf_common.js",
    "/assets/amf/js/common.js",
]

# include js, css files in header of web template
web_include_css = [
    "/assets/amf/amf-dev.css",
    "/assets/amf/amf.css",
]
# web_include_js = "/assets/amf/js/amf.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
""" doctype_js = {
    "Asset": ["public/js/doctype/asset.js"],
    "Contact": ["public/js/doctype/contact.js"],
    "Delivery Note": ["public/js/doctype/delivery_note.js"],
    "Expense Claim": ["public/js/doctype/expense_claim.js"],
    "Issue Type": ["public/js/doctype/issue_type.js"],
    "Issue": ["public/js/doctype/issue.js"],
    "Item": ["public/js/doctype/item.js"],
    "Job Card Time Log": ["public/js/doctype/job_card_time_log.js"],
    "Job Card": ["public/js/doctype/job_card.js"],
    "Journal Entry": ["public/js/doctype/journal_entry.js"],
    "Payment Entry": ["public/js/doctype/payment_entry.js"],
    "Purchase Invoice": ["public/js/doctype/purchase_invoice.js"],
    "Purchase Order": ["public/js/doctype/purchase_order.js"],
    "Purchase Receipt": ["public/js/doctype/purchase_receipt.js"],
    "Quotation": ["public/js/doctype/quotation.js"],
    "Sales Invoice": ["public/js/doctype/sales_invoice.js"],
    "Sales Order Item": ["public/js/doctype/sales_order_item.js"],
    "Sales Order": ["public/js/doctype/sales_order.js"],
    "Spreadsheet Expense Claim": ["public/js/doctype/spreadsheet_expense_claim.js"],
    "Stock Entry": ["public/js/doctype/stock_entry.js"],
    "Stock Reconciliation": ["public/js/doctype/stock_reconciliation.js"],
    "Supplier Quotation": ["public/js/doctype/supplier_quotation.js"],
    "Supplier": ["public/js/doctype/supplier.js"],
    "Timesheet": ["public/js/doctype/timesheet.js"],
    "Work Order": ["public/js/doctype/work_order.js"]
} """

# include js in doctype list views
doctype_list_js = {
    "Item": ["public/js/list/item_list.js"],
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "amf.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "amf.install.before_install"
# after_install = "amf.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "amf.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Work Order": {
        "on_submit": [
            "amf.amf.utils.custom.qr_code_to_document",
            "amf.amf.utils.on_work_order_submit.on_submit_wo",
        ]
    },
    "Job Card": {"on_submit": "amf.amf.utils.custom.qr_code_to_document"},
    "Lead": {
        "after_insert": [
            "amf.amf.utils.lead_customization.create_address_from_lead",
            "amf.amf.utils.lead_customization.create_contact_from_lead",
        ]
    },
    "Planning": {"on_update": "amf.www.planification.get_filter_value"},
    # "Stock Entry": {"before_submit": "amf.amf.utils.stock_entry.batch_to_stock_entry"},
    "Stock Entry": {"before_save": "amf.www.fftest.update_rate_and_availability_ste"},
    "Stock Entry": {"on_submit": "amf.amf.utils.custom.qr_code_to_document"},
    "Production Order": {"before_submit": "amf.amf.utils.custom.attach_qr_code_to_document"},
    "Batch": {"after_insert": "amf.amf.utils.barcode.after_insert_handler"},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    # 	"all": [
    # 		"amf.tasks.all"
    # 	],
    "daily": [
        "amf.amf.utils.item_image.update_item_images",
    ],
    "hourly": [
        "amf.amf.utils.document_notification.update_purchase_orders",
    ],
    "weekly": [
    	"amf.amf.utils.check_issue.fetch_open_issues",
        "amf.amf.utils.safety_stock_check.check_stock_levels",
    ],
    # 	"monthly": [
    # 		"amf.tasks.monthly"
    # 	]
}

# Testing
# -------

# before_tests = "amf.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "amf.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "amf.task.get_dashboard_data"
# }
