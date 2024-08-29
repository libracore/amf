# -*- coding: utf-8 -*-
# Copyright (c) 2024, libracore AG and Contributors
# See license.txt
#
# Simple run:
#   $ bench execute amf.master_crm.doctype.gravity_forms.test_gravity_forms.test

from __future__ import unicode_literals

import frappe
import unittest

class TestGravityForms(unittest.TestCase):
    pass

def test():
    gravity = frappe.get_doc("Gravity Forms", "Gravity Forms")
    
    forms = gravity.get_forms()
    
    for f in forms:
        print("{0}: {1} ({2} entries)".format(f.get('id'), f.get('title'), f.get('entries')))
    
    # fetch form
    fields = gravity.get_form_fields(3)
    for f in fields:
        print("{0}: {1}".format(f.get('id'), f.get('label')))
    
    entries = gravity.get_form_entries(3)
    
    for e in entries:
        print("{0}".format(e))
        
    return
    
