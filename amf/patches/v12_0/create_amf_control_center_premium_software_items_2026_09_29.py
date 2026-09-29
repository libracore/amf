"""Create the AMF Control Center Premium software offerings and CHF prices."""

import frappe
from frappe.utils import today


PRICE_LIST = "Price List S2 2026 AMF - CHF"
ITEMS = (
    (
        "920001", "AMF-CCP-LSPONE",
        "AMF Control Center Premium - included with LSPone",
        "AMF Control Center Premium license included with the purchase of an LSPone.", 0,
    ),
    (
        "920002", "AMF-CCP-OFFER",
        "AMF Control Center Premium - commercial offer",
        "AMF Control Center Premium license provided free of charge as a commercial offer.", 0,
    ),
    (
        "920003", "AMF-CCP-DISCOUNT",
        "AMF Control Center Premium - discounted",
        "AMF Control Center Premium license at a discounted price", 490,
    ),
    (
        "920004", "AMF-CCP-FULL",
        "AMF Control Center Premium - standard",
        "AMF Control Center Premium license", 990,
    ),
)


def execute():
    frappe.set_user("Administrator")

    if not frappe.get_meta("Item").has_field("reference_code"):
        raise RuntimeError("Item.reference_code is required for the AMF software items")
    if frappe.db.get_default("item_naming_by") != "Item Code":
        raise RuntimeError("Item naming must use Item Code")

    price_list = frappe.get_doc("Price List", PRICE_LIST)
    if (price_list.currency, price_list.enabled, price_list.selling) != ("CHF", 1, 1):
        raise RuntimeError("The target CHF selling price list must be enabled")

    if not frappe.db.exists("Item Group", "Software"):
        frappe.get_doc({
            "doctype": "Item Group",
            "item_group_name": "Software",
            "parent_item_group": "All Item Groups",
            "is_group": 0,
            "show_in_website": 0,
        }).insert()
    else:
        group = frappe.get_doc("Item Group", "Software")
        if group.parent_item_group != "All Item Groups" or group.is_group:
            raise RuntimeError("Existing Software item group has unexpected settings")

    for code, reference, name, description, rate in ITEMS:
        reference_owner = frappe.db.get_value("Item", {"reference_code": reference}, "name")
        if reference_owner and reference_owner != code:
            raise RuntimeError("Reference {} belongs to Item {}".format(reference, reference_owner))

        if not frappe.db.exists("Item", code):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": code,
                "item_name": name,
                "reference_code": reference,
                "item_group": "Software",
                "description": description,
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_sales_item": 1,
                "is_purchase_item": 0,
                "include_item_in_manufacturing": 0,
                "disabled": 0,
                "show_in_website": 0,
                "standard_rate": 0,
            }).insert()
        else:
            item = frappe.get_doc("Item", code)
            actual = (
                item.item_name, item.description, item.item_group, item.stock_uom,
                item.is_stock_item, item.is_sales_item, item.is_purchase_item, item.disabled,
            )
            expected = (name, description, "Software", "Nos", 0, 1, 0, 0)
            if actual != expected or item.reference_code not in (None, "", reference):
                raise RuntimeError("Existing Item {} differs from the requested offering".format(code))
            if item.reference_code != reference:
                item.reference_code = reference
                item.save()

        prices = frappe.get_all(
            "Item Price", filters={"item_code": code, "price_list": PRICE_LIST},
            fields=["name", "price_list_rate", "currency", "selling"],
        )
        if not prices:
            frappe.get_doc({
                "doctype": "Item Price",
                "item_code": code,
                "price_list": PRICE_LIST,
                "price_list_rate": rate,
                "valid_from": today(),
            }).insert()
        elif (len(prices) != 1 or
              (prices[0].price_list_rate, prices[0].currency, prices[0].selling)
              != (rate, "CHF", 1)):
            raise RuntimeError("Existing CHF Item Price differs for Item {}".format(code))
