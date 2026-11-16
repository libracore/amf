# DocType layouts

The Customize Form exports in `amf/amf/custom/` define the Sales Order layout
and its Sales Order Item, Sales Taxes and Charges, Payment Schedule and Sales
Team child-table customizations. Keep `sync_on_migrate: 1` in these files so
Frappe v12 reapplies them after the standard ERPNext schema and app fixtures.

Export future Sales Order changes to the **AMF** module, including its child
tables. Do not restore the duplicate `master_crm/custom/sales_team.json`: a
second export for the same DocType can overwrite the AMF export during
migration. The ERPNextSwiss Sales Order export runs before AMF on this site,
so AMF supplies the final `edi_file` field position.

The OTIF and custom-item setup hooks create missing Sales Order fields only.
They must not update existing Sales Order field definitions after the exported
layout has been synchronized. Business values such as `skip_otif_kpi` are
unaffected by layout synchronization.

The ERPNextSwiss HLK domain declares no custom fields. Domain setup and cleanup
therefore leave existing fields and their layouts intact when Domain Settings
is saved or HLK is enabled/disabled. Keep layouts in customization exports
instead of restoring field definitions in `erpnextswiss/domains/hlk.py`.

Work Order `sales_order_item.allow_on_submit = 1` is a targeted Property Setter
fixture in `amf/fixtures/property_setter.json`, selected by the `fixtures` hook.
It is applied on installation and migration without replacing other Work Order
customizations. Keep this field's other properties as configured in Customize
Form; allowing updates after submission does not change visibility or read-only
settings.
