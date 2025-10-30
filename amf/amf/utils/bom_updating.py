import frappe
from frappe import _
from frappe.exceptions import LinkExistsError, ValidationError

@frappe.whitelist()
def fetch_boms_with_operations_and_costs():
    """
    Fetch all BOMs that are default, with operations, and have operation costs not equal to zero.

    Returns:
        list: A list of dictionaries containing the BOMs that match the criteria.
    """
    try:
        # Query the BOMs with the specified criteria
        boms = frappe.db.sql(
            """
            SELECT
                b.name, b.item, b.operating_cost, b.is_default, b.with_operations
            FROM
                `tabBOM` b
            JOIN
                `tabItem` i ON b.item = i.name
            WHERE
                b.is_default = 1
                AND b.with_operations = 1
                AND b.operating_cost != 0
                AND i.disabled = 0
            """,
            as_dict=True
        )

        return boms

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error Fetching BOMs")
        frappe.throw(frappe._(f"An error occurred while fetching BOMs: {str(e)}"))

@frappe.whitelist()
def duplicate_boms_with_zero_cost():
    """
    Duplicate each BOM fetched by fetch_boms_with_operations_and_costs and set the operating_cost to 0.
    Additionally, set the base_hour_rate of all operations in the BOM to 0.

    Returns:
        list: A list of new BOM names created.
    """
    try:
        # Fetch BOMs with the specified criteria
        boms = fetch_boms_with_operations_and_costs()
        new_bom_names = []

        for bom in boms:
            # Duplicate the BOM
            new_bom = frappe.copy_doc(frappe.get_doc("BOM", bom["name"]))
            new_bom.is_default = 1  # Ensure the duplicate is not marked as default

            # Set base_hour_rate to 0 in the operations child table
            if new_bom.operations:
                for operation in new_bom.operations:
                    operation.base_hour_rate = 0
                    operation.base_operating_cost = 0
                    operation.operating_cost = 0

            new_bom.save()
            new_bom.submit()
            frappe.db.commit()
            # Append the new BOM name to the list
            new_bom_names.append(new_bom.name)

        return new_bom_names

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error Duplicating BOMs")
        frappe.throw(frappe._(f"An error occurred while duplicating BOMs: {str(e)}"))

@frappe.whitelist()
def deactivate_non_default_boms():
    """
    Fetch all BOMs that are not "default" and deactivate them.
    Only consider BOMs linked to enabled items whose name doesn't start with 10 or 20.
    Skip BOMs that cannot be disabled due to dependency on other BOMs.
    """
    try:
        # Fetch BOMs with the required conditions
        boms = frappe.get_all(
            "BOM",
            filters={
                "is_active": 1,          # Only active BOMs
                "is_default": 0          # Not default
            },
            fields=["name", "item"]
        )

        for bom in boms:
            item_doc = frappe.get_doc("Item", bom.item)

            # Skip if the item is disabled or if the name starts with '10' or '20'
            if item_doc.name.startswith(("10", "20")):
                continue

            try:
                # Deactivate the BOM
                bom_doc = frappe.get_doc("BOM", bom.name)
                bom_doc.is_active = 0
                bom_doc.save()
                frappe.db.commit()
                print(f"Deactivated BOM: {bom.name}")

            except ValidationError as e:
                # Skip BOMs that are linked to another BOM and cannot be disabled
                print(f"Skipping BOM {bom.name} due to dependency: {e}")

    except Exception as e:
        frappe.log_error(message=str(e), title="Error in Deactivating BOMs")
        print(f"Error: {e}")

@frappe.whitelist()
def deactivate_non_default_boms_():
    """
    Deactivate all non-default BOMs for enabled items, where the BOM name
    doesn't start with '10' or '20'. If disabling fails due to a linked
    reference, skip that BOM.
    """
    # 1. Fetch all enabled Items (disabled=0).
    #    We just pick the item name, then form a list from the results.
    enabled_items_records = frappe.db.get_list(
        "Item",
        filters={"disabled": 0}, 
        fields=["name"]
    )
    enabled_items = [record["name"] for record in enabled_items_records]
    
    # 2. Query BOMs that match the criteria:
    #    - is_default = 0  (not default)
    #    - disabled = 0    (currently active)
    #    - item in enabled_items
    #    - name NOT LIKE '10%' and name NOT LIKE '20%'
    boms_to_deactivate = frappe.db.get_list(
        "BOM",
        filters=[
            ["is_default", "=", 0],
            ["is_active", "=", 1],
            ["item", "in", enabled_items],
            ["name", "not like", "10%"],
            ["name", "not like", "20%"]
        ],
        fields=["name", "item"]
    )
    
    # 3. Loop through the BOMs and attempt to disable them
    for bom in boms_to_deactivate:
        bom_doc = frappe.get_doc("BOM", bom["name"])
        bom_doc.disabled = 1
        
        try:
            bom_doc.save()
            frappe.db.commit()  # Commit the change right away
            frappe.logger().info(f"Disabled BOM {bom_doc.name}.")
        except LinkExistsError:
            # BOM is linked to something else (like a sub-assembly),
            # so skip disabling it.
            frappe.log_error(
                title="BOM Deactivation Link Exists Error",
                message=_("Cannot disable BOM {0} because it is linked to another document.").format(bom_doc.name)
            )
            frappe.logger().warning(f"Skipping BOM {bom_doc.name} - linked to another document.")
            continue
            
            
"""
This is hooked in the BOM : before_save trigger (hooky.py)
"""
def bom_before_save(doc, event):
    if doc.is_default:
        update_depending_boms(doc.name, doc.item)
    
    return
    
    
"""
In case a default BOM is saved, update links to this BOM in all upper BOMs
"""
def update_depending_boms(bom, item):
    # find all BOMs depending on this item
    depending_boms = frappe.db.sql("""
        SELECT `tabBOM`.`name`
        FROM `tabBOM Item`
        LEFT JOIN `tabBOM` ON `tabBOM`.`name` = `tabBOM Item`.`parent`
        WHERE 
            `tabBOM Item`.`item_code` = %(item)s
            AND `tabBOM`.`docstatus` < 2;
        """,
        {'item': item},
        as_dict=True
    )
    for d in depending_boms:
        try:
            frappe.db.sql("""
                    UPDATE `tabBOM Item`
                    SET `bom_no` = %(bom)s
                    WHERE `parent` = %(depending)s;
                """,
                {
                    'bom': bom,
                    'depending': d.get("name")
                }
            )
        except Exception as err:
            frappe.log_error( "Unable to update depending BOM in {0}: {1}".format(d.get("name"), err), "Error updating depending bom")
        frappe.db.commit()
        
    return
    
