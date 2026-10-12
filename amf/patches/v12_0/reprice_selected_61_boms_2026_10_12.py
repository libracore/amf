from __future__ import unicode_literals, print_function

import frappe

from amf.amf.report.bom_cost_breakdown.selected_bom_reprice import apply_scoped_proposal


def execute():
    # The reviewed Item list and proposal are for this site's manufacturing data.
    if frappe.local.site != "site1.local":
        return
    # Frappe commits the BOM changes together with this patch's Patch Log entry.
    result = apply_scoped_proposal(commit=False)
    print("Selected 61-Item recursive BOM repricing: {}".format(result))
