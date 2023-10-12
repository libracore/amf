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
# app_include_css = "/assets/amf/css/amf.css"
app_include_js = "/assets/amf/js/amf_common.js"

# include js, css files in header of web template
web_include_css = [ 
    "/assets/amf/amf-dev.css",
    "/assets/amf/css/amf.css"
]
# web_include_js = "/assets/amf/js/amf.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
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
      "amf.amf.utils.on_work_order_submit.generate_qr",
      "amf.amf.utils.on_work_order_submit.on_submit_wo"
    ]
  },
  "Job Card": {
    "on_submit": "amf.amf.utils.on_work_order_submit.generate_qr"
  },
  "Lead": {
    "before_save": [
        "amf.amf.utils.lead_customization.create_address_from_lead",
        "amf.amf.utils.lead_customization.create_contact_from_lead"
    ]
  }
  # "Delivery Note": {
  #     "on_update": "amf.www.packaging.on_update"
  # }
}

# Scheduled Tasks
# ---------------

scheduler_events = {
# 	"all": [
# 		"amf.tasks.all"
# 	],
  "daily": [
 	  "amf.amf.utils.safety_stock_check.check_stock_levels"
  ],
  "hourly": [
    "amf.amf.utils.document_notification.update_purchase_orders",
 	],
# 	"weekly": [
# 		"amf.tasks.weekly"
# 	]
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
