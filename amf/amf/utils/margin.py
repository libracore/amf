# -*- coding: utf-8 -*-
# Copyright (c) 2024, [Your Company Name] and contributors
# For license information, please see license.txt

import frappe
from frappe import _

# --- Configuration ---
# Define the hourly rates for different types of overhead in your local currency (CHF).
HOURLY_RATE_CHF_MACHINING = 75.0
HOURLY_RATE_CHF_ASSEMBLY = 60.0
HOURLY_RATE_CHF_QA = 65.0

# Define the overheads per item group.
# The keys are the exact names of your Item Groups.
# The values are dictionaries containing different time components in MINUTES.
# Admin time will be calculated using the ASSEMBLY rate.
OVERHEADS_IN_MINUTES = {
    "Valve Head": {
        "machining_time": 0,
        "assembly_time": 4,
        "qa_time": 5,
        "admin_time": 2,
    },
    "Valve Seat": {
        "machining_time": 12,
        "assembly_time": 0,
        "qa_time": 2,
        "admin_time": 0.5,  # 30 seconds
    },
    "Plug": {
        "machining_time": 6,
        "assembly_time": 0,
        "qa_time": 2,
        "admin_time": 0.5,
    },
    "Product": {
        "machining_time": 0,
        "assembly_time": 240,
        "qa_time": 15,
        "admin_time": 5,
    }
}
# --- End of Configuration ---
@frappe.whitelist()
def update_item_real_cost():
    """
    Main function to iterate through items, calculate, and update the real cost.
    The real cost is the sum of the material cost from the default BOM and
    a calculated overhead based on the item's group and specific hourly rates.
    """
    frappe.log("Starting Real Cost update process...")

    # Calculate cost per minute from the hourly rates for efficiency
    machining_cost_per_minute = HOURLY_RATE_CHF_MACHINING / 60.0
    assembly_cost_per_minute = HOURLY_RATE_CHF_ASSEMBLY / 60.0
    qa_cost_per_minute = HOURLY_RATE_CHF_QA / 60.0

    # Get a list of all item groups that have overheads defined
    item_groups_with_overhead = list(OVERHEADS_IN_MINUTES.keys())

    if not item_groups_with_overhead:
        frappe.log_error("No item groups defined in the OVERHEADS_IN_MINUTES configuration.", "Real Cost Update Error")
        return

    # Fetch all active, manufactured items that belong to the configured item groups
    items_to_process = frappe.get_all(
        "Item",
        filters={
            "item_group": ["in", item_groups_with_overhead],
            "is_stock_item": 1,
            "disabled": 0,
        },
        fields=["name", "item_group", "default_bom", "real_cost"]
    )

    if not items_to_process:
        frappe.log("No items found for the configured item groups with active BOMs.")
        return

    total_items = len(items_to_process)
    frappe.log(f"Found {total_items} items to process.")

    # Loop through each item to perform the calculation
    for idx, item in enumerate(items_to_process):
        try:
            # --- Step 1: Calculate BOM Material Cost ---
            bom_cost = 0.0
            # Find the default BOM for the item and fetch its pre-calculated total_cost.
            # This is more efficient than loading the full BOM document and recalculating the cost.
            default_bom_data = frappe.db.get_value(
                "BOM",
                {"item": item.name, "is_default": 1, "is_active": 1},
                ["name", "total_cost"],
                as_dict=True
            )
            if default_bom_data:
                bom_cost = default_bom_data.get("total_cost", 0.0)
            else:
                frappe.log(f"Real Cost Warning: Skipping BOM cost for Item '{item.name}': No active, default BOM found.")

            # --- Step 2: Calculate Granular Overhead Cost ---
            overhead_cost = 0.0
            item_group_config = OVERHEADS_IN_MINUTES.get(item.item_group)

            if item_group_config:
                # Make a copy to modify for special conditions
                config = item_group_config.copy()
                # Conditional logic for 'Product' item group based on item code
                if item.item_group == "Product":
                    if item.name.startswith(('41', '42', '43', '44')):
                        config["assembly_time"] = 30
                    else:
                        config["assembly_time"] = 240 # Explicitly set the default
                # Calculate cost for each component based on its specific rate
                machining_cost = config.get("machining_time", 0) * machining_cost_per_minute
                assembly_cost = config.get("assembly_time", 0) * assembly_cost_per_minute
                qa_cost = config.get("qa_time", 0) * qa_cost_per_minute
                admin_cost = config.get("admin_time", 0) * assembly_cost_per_minute
                
                overhead_cost = machining_cost + assembly_cost + qa_cost + admin_cost
            
            # --- Step 3: Calculate Final Real Cost and Update Item ---
            final_real_cost = (bom_cost + overhead_cost)*1.25
            if item.name == '420081':
                print(final_real_cost)
            frappe.db.set_value(
                    "Item",
                    item.name,
                    "real_cost", # The name of your custom field
                    final_real_cost,
                    update_modified=True
            )
            if item.name == '420081':
                print("set")
            frappe.db.commit()
            frappe.log(f"({idx+1}/{total_items}) Updated Item '{item.name}': BOM Cost={bom_cost:.2f}, Overhead={overhead_cost:.2f}, Real Cost={final_real_cost:.2f}")

        except Exception as e:
            frappe.log_error(
                message=f"Failed to process item '{item.name}'. Error: {str(e)}",
                title="Real Cost Processing Error"
            )
    
    frappe.db.commit()
    frappe.log("Real Cost update process completed successfully.")

# You can uncomment the line below to run this script directly for testing via the bench console
# if __name__ == "__main__":
#     update_item_real_cost()
