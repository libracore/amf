from __future__ import unicode_literals

import frappe


def get_stale_item_variant_attribute_links(template_item=None, limit=None):
    """
    Return Item Variant Attribute rows whose hidden variant_of link no longer
    matches the parent Item.

    ERPNext copies Item.variant_of into every Item Variant Attribute row when a
    variant is created. If the parent Item is later converted back to a normal
    Item, those child rows can keep pointing at an old template. Since Frappe
    validates child-table Link fields before Item validate hooks run, a disabled
    old template can block otherwise unrelated Item saves.
    """
    params = {}
    conditions = _get_stale_link_conditions(template_item, params)
    limit_clause = ""

    if limit:
        params["limit"] = int(limit)
        limit_clause = " LIMIT %(limit)s"

    return frappe.db.sql(
        """
        SELECT
            iva.name,
            iva.parent,
            iva.idx,
            iva.variant_of AS child_variant_of,
            item.variant_of AS parent_variant_of,
            item.disabled AS parent_disabled,
            item.item_group,
            item.item_name
        FROM `tabItem Variant Attribute` iva
        INNER JOIN `tabItem` item ON item.name = iva.parent
        WHERE {conditions}
        ORDER BY iva.parent, iva.idx
        {limit_clause}
        """.format(
            conditions=" AND ".join(conditions),
            limit_clause=limit_clause,
        ),
        params,
        as_dict=True,
    )


def repair_stale_item_variant_attribute_links(template_item=None, commit=False):
    """
    Clear or repair stale hidden Item Variant Attribute.variant_of values.

    - If the parent Item is no longer a variant, clear the child-row variant_of.
    - If the parent Item still is a variant but the child row points elsewhere,
      align the child row to the parent Item.variant_of.
    """
    stale_rows = get_stale_item_variant_attribute_links(template_item=template_item)
    summary = {
        "stale_rows": len(stale_rows),
        "cleared_rows": 0,
        "synchronized_rows": 0,
    }

    if not stale_rows:
        return summary

    params = {}
    conditions = _get_stale_link_conditions(template_item, params)

    clear_conditions = list(conditions)
    clear_conditions.append("ifnull(item.variant_of, '') = ''")
    summary["cleared_rows"] = _run_update(
        """
        UPDATE `tabItem Variant Attribute` iva
        INNER JOIN `tabItem` item ON item.name = iva.parent
        SET iva.variant_of = ''
        WHERE {conditions}
        """.format(conditions=" AND ".join(clear_conditions)),
        params,
    )

    sync_conditions = list(conditions)
    sync_conditions.append("ifnull(item.variant_of, '') != ''")
    summary["synchronized_rows"] = _run_update(
        """
        UPDATE `tabItem Variant Attribute` iva
        INNER JOIN `tabItem` item ON item.name = iva.parent
        SET iva.variant_of = item.variant_of
        WHERE {conditions}
        """.format(conditions=" AND ".join(sync_conditions)),
        params,
    )

    if commit:
        frappe.db.commit()

    return summary


@frappe.whitelist()
def preview_stale_item_variant_attribute_links(template_item=None, limit=100):
    return get_stale_item_variant_attribute_links(template_item=template_item, limit=limit)


@frappe.whitelist()
def repair_stale_item_variant_attribute_links_now(template_item=None):
    return repair_stale_item_variant_attribute_links(template_item=template_item, commit=True)


def _get_stale_link_conditions(template_item=None, params=None):
    if params is None:
        params = {}

    conditions = [
        "iva.parenttype = 'Item'",
        "iva.parentfield = 'attributes'",
        "ifnull(iva.variant_of, '') != ''",
        "ifnull(iva.variant_of, '') != ifnull(item.variant_of, '')",
    ]

    if template_item:
        conditions.append("iva.variant_of = %(template_item)s")
        params["template_item"] = template_item

    return conditions


def _run_update(query, params):
    frappe.db.sql(query, params)
    return frappe.db._cursor.rowcount or 0
