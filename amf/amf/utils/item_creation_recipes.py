"""Pure recipe definitions. Preview and execution consume their exact output."""
from frappe.utils import escape_html
from amf.amf.utils.item_learned_defaults import build_item_description


def item_defaults(doc):
    return [dict(company=doc.get("company"), default_warehouse=doc.get("default_warehouse"))]


def component_definition(doc, group):
    code, name, reference = (doc.get(group + suffix) for suffix in ("_code", "_name", "_rnd"))
    item_group = "Plug" if group == "plug" else "Valve Seat"
    component = dict(item_code=code, item_name=name, item_group=item_group, item_type="Component",
        reference_code=reference, reference_name="{0}: {1}".format(code, name), stock_uom="Nos",
        tag_raw_mat=doc.get(group + "_mat"), is_purchase_item=0, country_of_origin="Switzerland",
        item_defaults=item_defaults(doc), description=build_item_description(code, name, item_group, "Component", reference))
    if doc.get(group + "_drawing"):
        component["drawing_item"] = [dict(drawing=doc.get(group + "_drawing"), item_code=code,
            item_name=name, reference_code=reference, version="01", revision="01", is_default=1)]
    assembly_code = code[0] + "1" + code[2:]
    assembly = dict(item_code=assembly_code, item_name=name, item_group=item_group, item_type="Sub-Assembly",
        reference_code=reference + ".ASM", reference_name="{0}: {1}".format(assembly_code, name), stock_uom="Nos",
        is_purchase_item=0, country_of_origin="Switzerland", item_defaults=item_defaults(doc),
        description=build_item_description(assembly_code, name, item_group, "Sub-Assembly", reference + ".ASM"))
    materials = [dict(item_code=code, qty=1)]
    qty = float(doc.get(group + "_acc") or 0)
    if qty > 0:
        materials.append(dict(item_code="SPL.3013" if group == "plug" else doc.get("seat_pin_item"), qty=qty))
    return component, assembly, materials


def standard_product_reference(head, body_reference, syringe_reference="", rule=None):
    if rule and rule.get("family") == "RVM":
        return rule["reference_base"].replace("-", "") + head + rule["reference_suffix"]
    return body_reference.replace("-", "") + head + syringe_reference.replace("-", "")


def product_definition(doc, rule, body, syringe=None):
    head = doc.get("head_code")
    reference = syringe.get("reference_code") if syringe else ""
    label = body.get("reference_code") or rule["body_label"]
    code = rule.get("product_code") or rule["prefix"] + head[-3:]
    name = label + "/" + (doc.get("head_rnd") or head) + ("/" + reference if reference else "")
    if rule["family"] == "RVM":
        name = rule["name_base"] + "/" + (doc.get("head_rnd") or head)
        if rule["name_suffix"]:
            name += "/" + rule["name_suffix"]
    materials = [dict(item_code=rule["body"], qty=1), dict(item_code=head, qty=1),
                 dict(item_code=doc.get("screw_type"), qty=doc.get("screw_quantity"))]
    scraps = []
    if rule["family"] == "RVM":
        materials.append(dict(item_code=doc.get("cap_type"), qty=1))
    else:
        materials.append(dict(item_code=rule["syringe"], qty=1))
        if rule["family"] == "HV":
            materials.append(dict(item_code="RVM.1204", qty=1))
        else:
            scraps.append(dict(item_code="RVM.1204", qty=1))
        if label.endswith("-L"):
            materials.extend([dict(item_code="C100", qty=1), dict(item_code="C101", qty=1)])
            if rule["family"] == "LV":
                materials.append(dict(item_code="T100", qty=1))
    description = "<b>Body:</b> {0} ({1})<br><b>Valve Head:</b> {2} ({3})".format(
        escape_html(label), escape_html(rule["body"]), escape_html(doc.get("head_name") or ""), escape_html(head))
    if syringe:
        volume = float(reference.split("-")[1])
        volume_label = "{0:g} µL".format(volume)
        if volume >= 1000:
            volume_label += " ({0:g} mL)".format(volume / 1000)
        description += "<br><b>Syringe:</b> {0} · {1}".format(escape_html(volume_label), escape_html(reference))
    data = dict(item_code=code, item_name=name, item_group="Product", item_type="Finished Good", stock_uom="Nos",
        reference_code=rule.get("product_reference") or standard_product_reference(head, label, reference, rule),
        reference_name=code + ": " + name, description=description, has_batch_no=0, is_purchase_item=0,
        country_of_origin="Switzerland", is_sales_item=1, item_defaults=item_defaults(doc),
        weight_per_unit=rule.get("product_weight", 2.18),
        weight_uom="Kg")
    return data, materials, scraps
