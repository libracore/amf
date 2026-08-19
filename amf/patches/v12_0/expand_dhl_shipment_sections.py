# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from amf.amf.utils.dhl_shipment_setup import (
	install_dhl_settings_schema,
	install_dhl_shipment_fields,
	set_dhl_shipment_sections_non_collapsible,
)


def execute():
	install_dhl_settings_schema()
	install_dhl_shipment_fields()
	set_dhl_shipment_sections_non_collapsible()
