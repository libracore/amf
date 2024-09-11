# Copyright (c) 2024, libracore AG and contributors
# For license information, please see license.txt

import frappe
import datetime
from frappe import _
import json

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
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150}
    ]
    
def get_data(filters):
    conditions = ""
    if filters.country:
        conditions += """ AND `tUAdr`.`country` = "{0}" """.format(filters.country)
    if filters.city:
        conditions += """ AND `tUAdr`.`city` LIKE "%{0}%" """.format(filters.city)
    if filters.customer:
        conditions += """ AND `tabCustomer`.`name` = "{0}" """.format(filters.customer)
        
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
          `tabContact`.`status` AS `status`
        FROM `tabCustomer`
        JOIN `tabDynamic Link` AS `DL1` ON (`tabCustomer`.`name` = `DL1`.`link_name` AND `DL1`.`link_doctype` = 'Customer' AND `DL1`.`parenttype` = 'Contact')
        LEFT JOIN `tabContact` ON `DL1`.`parent` = `tabContact`.`name`
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
      """.format(conditions=conditions)

    data = frappe.db.sql(sql_query, as_dict=1)

    return data
