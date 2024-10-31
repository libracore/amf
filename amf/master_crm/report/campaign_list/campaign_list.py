# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe
import datetime
from frappe import _
import json
from frappe.utils import cint

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    return [
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 80},
        {"label": _("Customer name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 120},
        {"label": _("Address"), "fieldname": "address_line1", "fieldtype": "Data", "width": 200},
        {"label": _("Add. address"), "fieldname": "address_line2", "fieldtype": "Data", "width": 200},
        {"label": _("PC"), "fieldname": "pincode", "fieldtype": "Data", "width": 50},
        {"label": _("City"), "fieldname": "city", "fieldtype": "Data", "width": 150},
        {"label": _("Contact"), "fieldname": "contact", "fieldtype": "Link", "options": "Contact", "width": 50},
        {"label": _("First name"), "fieldname": "first_name", "fieldtype": "Data", "width": 100},
        {"label": _("Last name"), "fieldname": "last_name", "fieldtype": "Data", "width": 100},
        {"label": _("Email"), "fieldname": "contact_email", "fieldtype": "Data", "width": 100},
        {"label": _("Phone"), "fieldname": "contact_phone", "fieldtype": "Data", "width": 100},
        {"label": _("Mobile"), "fieldname": "contact_mobile", "fieldtype": "Data", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
        {"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 100},
        {"label": _("Modified"), "fieldname": "modified", "fieldtype": "Datetime", "width": 100},
    ]
    
def get_data(filters):
    conditions = ""
    revenue_conditions = ""
    if filters.get("country"):
        conditions += """ AND (`tUAdr`.`country` = "{0}" OR `tabContact`.`country` = "{0}")""".format(filters.get("country"))
    if filters.get("city"):
        conditions += """ AND `tUAdr`.`city` LIKE "%{0}%" """.format(filters.get("city"))
    if filters.get("customer"):
        conditions += """ AND `tabCustomer`.`name` = "{0}" """.format(filters.get("customer"))
    if filters.get("territory"):
        conditions += """ AND `tabCustomer`.`territory` = "{0}" """.format(filters.get("territory"))
    if filters.get("modified_after"):
        conditions += """ AND `tabContact`.`modified` >= "{0}" """.format(filters.get("modified_after"))
    if filters.get("status"):
        conditions += """ AND `tabContact`.`status` = "{0}" """.format(filters.get("status"))
    if filters.get("type_of_contact"):
        conditions += """ AND `tabContact`.`contact_function` = "{0}" """.format(filters.get("type_of_contact"))
    if filters.get("source"):
        conditions += """ AND `tabContact`.`source` = "{0}" """.format(filters.get("source"))
    if filters.get("from_source"):
        conditions += """ AND `tabContact`.`from_source` = "{0}" """.format(filters.get("from_source"))
    if filters.get("product"):
        conditions += """ AND `tabContact`.`product` = "{0}" """.format(filters.get("product"))
    if filters.get("development_stage"):
        conditions += """ AND `tabContact`.`development_stage` = "{0}" """.format(filters.get("development_stage"))
    if cint(filters.get("gdpr")):
        conditions += """ AND `tabContact`.`gdpr_compliant` = 1 """
    if filters.get("deliverability"):
        conditions += """ AND `tabContact`.`deliverability` = "{0}" """.format(filters.get("deliverability"))
    if filters.get("qualification"):
        conditions += """ AND `tabContact`.`qualification` = {0} """.format(filters.get("qualification"))
    if filters.get("customer_group"):
        conditions += """ AND `tabContact`.`customer_group` = "{0}" """.format(filters.get("customer_group"))
    if filters.get("revenue_from"):
        revenue_conditions += """ AND `tabSales Invoice`.`posting_date` >= "{0}" """.format(filters.get("revenue_from"))
    if filters.get("revenue_to"):
        revenue_conditions += """ AND `tabSales Invoice`.`posting_date` <= "{0}" """.format(filters.get("revenue_to"))
    if filters.get("is_customer"):
        conditions += """ AND `tabCustomer`.`is_customer` = {0} """.format(1 if filters.get("is_customer") == "Yes" else 0)
        
    # base table is customer: contacts not linked to a customer are not shown
    sql_query = """SELECT 
          `tabCustomer`.`name` AS `customer`,
          `tabCustomer`.`customer_name` AS `customer_name`,
          `tabCustomer`.`website` AS `homepage`,
          `tUAdr`.`address_line1` AS `address_line1`,
          `tUAdr`.`address_line2` AS `address_line2`,
          `tUAdr`.`pincode` AS `pincode`,
          `tUAdr`.`city` AS `city`,
          `tabContact`.`name` AS `contact`,
          `tabContact`.`first_name` AS `first_name`,
          `tabContact`.`last_name` AS `last_name`,
          `tabContact`.`email_id` AS `contact_email`,
          `tabContact`.`phone` As `contact_phone`,
          `tabContact`.`mobile_no` AS `contact_mobile`,
          `tabContact`.`status` AS `status`,
          `tabContact`.`modified` AS `modified`,
          `tabContact`.`creation` AS `created`,
          (SELECT SUM(`tabSales Invoice`.`base_net_total`) 
           FROM `tabSales Invoice` 
           WHERE `tabSales Invoice`.`docstatus` = 1
             AND `tabSales Invoice`.`customer` = `tabCustomer`.`name`
             {revenue_conditions}) AS `revenue`,
          (SELECT MAX(`tabSales Order`.`transaction_date`) 
           FROM `tabSales Order` 
           WHERE `tabSales Order`.`docstatus` = 1
             AND `tabSales Order`.`contact_person` = `tabContact`.`name`) AS `last_po_date`
        
        FROM `tabContact`
        LEFT JOIN `tabDynamic Link` AS `DL1` ON (`tabContact`.`name` = `DL1`.`parent` AND `DL1`.`link_doctype` = 'Customer' AND `DL1`.`parenttype` = 'Contact')
        LEFT JOIN `tabCustomer` ON `DL1`.`link_name` = `tabContact`.`name`
        LEFT JOIN (
            SELECT *
            FROM (
              SELECT 
                `tabAddress`.`email_id` AS `email_id`,
                `tabAddress`.`phone` AS `phone`,
                `tabAddress`.`address_line1` AS `address_line1`,
                `tabAddress`.`address_line2` AS `address_line2`,
                `tabAddress`.`pincode` AS `pincode`,
                `tabAddress`.`city` AS `city`,
                `tDL`.`link_name` AS `customer`,
                `tabAddress`.`country` AS `country`
              FROM `tabAddress`
              LEFT JOIN `tabDynamic Link` AS `tDL` ON (
                `tabAddress`.`name` = `tDL`.`parent` 
                AND `tDL`.`link_doctype` = 'Customer' 
                AND `tDL`.`parenttype` = 'Address'
              )
              ORDER BY `tabAddress`.`is_primary_address` DESC
            ) AS `tAdr`
            GROUP BY `tAdr`.`customer`
        ) AS `tUAdr` ON `tabCustomer`.`name` = `tUAdr`.`customer`
        WHERE `tabContact`.`status` IS NOT NULL
          {conditions} 
        ORDER BY `tabCustomer`.`name` ASC;
      """.format(conditions=conditions, revenue_conditions=revenue_conditions)
    #frappe.throw(sql_query)
    data = frappe.db.sql(sql_query, as_dict=1)

    if filters.get("revenue"):
        out = []
        for d in data:
            if cint(d.get("revenue")) >= filters.get("revenue"):
                out.append(d)
                
        data = out
    
    if filters.get("last_po"):
        out = []
        cut_off_date = datetime.datetime.strptime(filters.get("last_po"), "%Y-%m-%d").date()
        for d in data:
            if d.get("last_po_date") and d.get("last_po_date") >= cut_off_date:
                out.append(d)
                
        data = out
    
    if filters.get("created_after"):
        out = []
        cut_off_date = datetime.datetime.strptime(filters.get("created_after"), "%Y-%m-%d").date()
        for d in data:
            if d.get("created") and d.get("created") >= cut_off_date:
                out.append(d)
                
        data = out
        
    return data
