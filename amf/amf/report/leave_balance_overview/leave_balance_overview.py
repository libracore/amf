# Copyright (c) 2025, libracore AG and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {'fieldname': 'employee', 'label': _("Employee"), 'fieldtype': 'Link', 'options': 'Employee', 'width': 120},
        {'fieldname': 'employee_name', 'label': _("Employee name"), 'fieldtype': 'Data', 'width': 150},
        {'fieldname': 'allocated_leaves', 'label': _("Allocated leaves"), 'fieldtype': 'Float', 'width': 120},
        {'fieldname': 'approved_leaves', 'label': _("Approved leaves"), 'fieldtype': 'Float', 'width': 120},
        {'fieldname': 'pending_leaves', 'label': _("Pending leaves"), 'fieldtype': 'Float', 'width': 120},
        {'fieldname': 'remaining_leaves', 'label': _("Remaining leaves"), 'fieldtype': 'Float', 'width': 120},
        {'fieldname': 'sick_leaves', 'label': _("Sick leaves"), 'fieldtype': 'Float', 'width': 120},
    ]
    
def get_data(filters):
    regular_leave_types = [lt['name'] for lt in frappe.get_all("Leave Type", filters={'allow_negative': 0}, fields=['name'])]
    #frappe.throw("{0}".format("'{0}'".format("', '".join(regular_leave_types))))
    
    employees = frappe.db.sql("""
        SELECT 
            `tabEmployee`.`name` AS `employee`, 
            `tabEmployee`.`employee_name`,
            (SELECT SUM(`new_leaves_allocated`)
             FROM `tabLeave Allocation`
             WHERE 
                `tabLeave Allocation`.`employee` = `tabEmployee`.`name`
                AND `tabLeave Allocation`.`docstatus` = 1
                AND `tabLeave Allocation`.`from_date` >= %(from_date)s
                AND `tabLeave Allocation`.`to_date` <= %(to_date)s
                AND `tabLeave Allocation`.`leave_type` IN ({regular_leave_types})
            ) AS `allocated_leaves`,
            (SELECT SUM(`total_leave_days`)
             FROM `tabLeave Application` AS `tA1`
             WHERE 
                `tA1`.`employee` = `tabEmployee`.`name`
                AND `tA1`.`docstatus` = 1
                AND `tA1`.`from_date` >= %(from_date)s
                AND `tA1`.`to_date` <= %(to_date)s
                AND `tA1`.`leave_type` IN ({regular_leave_types})
            ) AS `approved_leaves`,
            (SELECT SUM(`total_leave_days`)
             FROM `tabLeave Application` AS `tA2`
             WHERE 
                `tA2`.`employee` = `tabEmployee`.`name`
                AND `tA2`.`docstatus` = 0
                AND `tA2`.`from_date` >= %(from_date)s
                AND `tA2`.`to_date` <= %(to_date)s
                AND `tA2`.`leave_type` IN ({regular_leave_types})
            ) AS `pending_leaves`,
            (SELECT SUM(`total_leave_days`)
             FROM `tabLeave Application` AS `tA3`
             WHERE 
                `tA3`.`employee` = `tabEmployee`.`name`
                AND `tA3`.`docstatus` < 2
                AND `tA3`.`from_date` >= %(from_date)s
                AND `tA3`.`to_date` <= %(to_date)s
                AND `tA3`.`leave_type` IN ('Jour de maladie')
            ) AS `sick_leaves`
        FROM `tabEmployee`
        WHERE 
            `tabEmployee`.`date_of_joining` <= %(to_date)s
            AND (`tabEmployee`.`relieving_date` IS NULL 
                 OR `tabEmployee`.`relieving_date` >= %(from_date)s)
            AND `tabEmployee`.`company` = %(company)s
        ORDER BY `tabEmployee`.`employee_name` ASC;
        """.format(regular_leave_types=("'{0}'".format("', '".join(regular_leave_types)))),
        {
            'to_date': filters.get("to_date"),
            'from_date': filters.get("from_date"),
            'company': filters.get("company")
        },
        as_dict=True
    )
    
    for e in employees:
        e['remaining_leaves'] = flt(e.get('allocated_leaves')) - flt(e.get('approved_leaves')) - flt(e.get('pending_leaves'))
    return employees
