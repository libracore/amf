import frappe
from frappe.utils import flt
from tabulate import tabulate
from collections import Counter

def get_items_shipped_data():
    """
    Fetches and displays the total quantity of items shipped for item groups 'Body', 'Valve Head',
    and 'Product' during the periods S1 (Jan-June) and S2 (July-Dec) for 2023 and 2024.
    Calculates the growth between S1 and S2 for each year.
    """
    # Define the time periods
    periods = {
        "2023_S1": ("2023-01-01", "2023-06-30"),
        "2023_S2": ("2023-07-01", "2023-12-31"),
        "2024_S1": ("2024-01-01", "2024-06-30"),
        "2024_S2": ("2024-07-01", "2024-12-31"),
    }

    # Define the item groups to include
    item_groups = ["Body", "Valve Head", "Product"]

    # Initialize the result dictionary
    result = {group: {period: 0 for period in periods.keys()} for group in item_groups}

    # Fetch data for each period
    for period, (start_date, end_date) in periods.items():
        # Query the delivery note items for the specified period and item groups
        data = frappe.db.sql("""
            SELECT 
                i.item_group, 
                SUM(i.qty) AS total_qty
            FROM 
                `tabDelivery Note Item` i
            JOIN 
                `tabDelivery Note` dn ON i.parent = dn.name
            WHERE 
                dn.docstatus = 1
                AND i.item_group IN %(item_groups)s
                AND dn.posting_date BETWEEN %(start_date)s AND %(end_date)s
            GROUP BY 
                i.item_group
        """, {
            "item_groups": item_groups,
            "start_date": start_date,
            "end_date": end_date
        }, as_dict=True)

        # Populate results
        for row in data:
            result[row["item_group"]][period] = row["total_qty"] or 0

    # Calculate growth between S1 and S2 for each year
    for group in item_groups:
        result[group]["2023_Growth"] = calculate_growth(result[group]["2023_S1"], result[group]["2023_S2"])
        result[group]["2024_Growth"] = calculate_growth(result[group]["2024_S1"], result[group]["2024_S2"])

    # Prepare the table for display
    headers = ["Item Group", "2023_S1", "2023_S2", "2023_Growth", "2024_S1", "2024_S2", "2024_Growth"]
    table_data = [
        [
            group,
            result[group]["2023_S1"],
            result[group]["2023_S2"],
            f"{result[group]['2023_Growth']}%",
            result[group]["2024_S1"],
            result[group]["2024_S2"],
            f"{result[group]['2024_Growth']}%"
        ]
        for group in item_groups
    ]

    # Display the result in tabular format
    print(tabulate(table_data, headers, tablefmt="grid"))
    print("Be careful because in 'Product' starting S2 2024, Valve Heads are also in the latter compared to 'Product' in S1 and before where VH where separated.")

def calculate_growth(s1, s2):
    """
    Calculates the percentage growth between S1 and S2.
    Returns growth as a percentage formatted as a float.
    """
    if s1 > 0:
        return round(((s2 - s1) / s1) * 100, 2)
    else:
        return 100.0 if s2 > 0 else 0.0

def parse_weight(weight):
    """
    Normalize weight by replacing commas with dots and converting to float.
    Handles cases like "72,5" or "7.9".
    """
    try:
        return float(str(weight).replace(',', '.'))
    except ValueError:
        return 0.0  # Return 0 if the weight value cannot be parsed

def get_delivery_notes_summary(filters=None):
    """
    Summarizes submitted delivery notes for the years 2023 and 2024,
    showing total weight, number of delivery notes, and the top 6 territories by shipment count.
    Separates the data by year and handles weight values with commas or dots.
    """
    if not filters:
        filters = {}

    # Define the years to include in the report
    years = ['2023', '2024']
    filters['docstatus'] = 1  # Only fetch submitted delivery notes

    # Initialize variables to store results per year
    report_data = {}

    for year in years:
        filters['posting_date'] = ['between', (f'{year}-01-01', f'{year}-12-31')]

        # Query delivery notes for the year
        delivery_notes = frappe.db.get_all(
            'Delivery Note',
            fields=['name', 'weight', 'territory'],
            filters=filters
        )

        total_weight = 0.0
        delivery_note_count = 0
        territory_counter = Counter()

        # Process the results
        for dn in delivery_notes:
            weight = parse_weight(dn.get('weight', 0))
            print(dn, year, weight)
            total_weight += weight
            delivery_note_count += 1
            if dn.get('territory'):
                territory_counter[dn['territory']] += 1

        # Get the top 6 territories
        top_territories = territory_counter.most_common(6)

        # Store the data for this year
        report_data[year] = {
            "total_weight": total_weight,
            "delivery_note_count": delivery_note_count,
            "top_territories": top_territories
        }

    # Prepare tables for each year
    all_tables = []
    for year, data in report_data.items():
        table_data = [
            ["Metric", f"Value for {year}"],
            ["Total Weight Shipped", f"{data['total_weight']} kg"],
            ["Number of Delivery Notes", data['delivery_note_count']],
            ["Top 6 Territories Shipped To", f"{len(data['top_territories'])} territories"],
        ]
        for territory, count in data['top_territories']:
            table_data.append([f"  - {territory}", f"{count} shipments"])

        # Format the table for this year
        year_table = tabulate(table_data, tablefmt="grid", numalign="right", stralign="left")
        all_tables.append(year_table)

    # Combine all year tables
    final_report = "\n\n".join(all_tables)
    print(final_report)
    
def get_manufactured_items_by_item_group():
    # Query to fetch manufactured items by item group for S1 and S2
    manufactured_items = frappe.db.sql("""
        SELECT 
            item.item_group AS item_group,
            SUM(CASE 
                WHEN MONTH(wo.planned_start_date) BETWEEN 1 AND 6 THEN wo.qty
                ELSE 0 
            END) AS s1_manufactured,
            SUM(CASE 
                WHEN MONTH(wo.planned_start_date) BETWEEN 7 AND 12 THEN wo.qty
                ELSE 0 
            END) AS s2_manufactured,
            SUM(wo.qty) AS total_manufactured
        FROM 
            `tabWork Order` wo
        INNER JOIN 
            `tabItem` item ON wo.production_item = item.name
        WHERE 
            wo.machine IS NOT NULL
            AND wo.docstatus = 1
            AND YEAR(wo.planned_start_date) = 2024
        GROUP BY 
            item.item_group
        ORDER BY 
            item.item_group ASC
    """, as_dict=True)

    # Prepare the data for tabulate
    table_data = []
    for item in manufactured_items:
        s1 = flt(item.get("s1_manufactured"))
        s2 = flt(item.get("s2_manufactured"))
        total = flt(item.get("total_manufactured"))
        
        # Calculate growth percentage
        if s1 > 0:
            growth = ((s2 - s1) / s1) * 100
        else:
            growth = 0 if s2 == 0 else 100  # If S1 is zero, set growth to 100% if S2 > 0
        
        table_data.append([
            item.get("item_group"),
            s1,
            s2,
            total,
            f"{growth:.2f}%"  # Format growth as a percentage with 2 decimal places
        ])
    
    # Define headers
    headers = ["Item Group", "S1 Manufactured", "S2 Manufactured", "Total Manufactured", "Growth (S1 to S2)"]

    # Display table
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
def calculate_price_ratio():
    """
    Calculate the ratio of the last purchase price over the purchase price before for items with purchase receipts.
    Returns a dictionary with item codes as keys and their price ratios as values.
    """
    # Fetch last two purchase receipt rates for each item
    items_with_ratios = {}

    # Query to get the last two purchase receipts for each item
    purchase_data = frappe.db.sql("""
        SELECT
            pri.item_code,
            pri.net_rate,
            pri.conversion_factor,
            pri.creation
        FROM
            `tabPurchase Receipt Item` pri
        JOIN
            `tabPurchase Receipt` pr ON pri.parent = pr.name
        WHERE
            pri.item_code IS NOT NULL
        AND
            pri.item_code NOT RLIKE 'GX'
        AND
            pr.supplier != 'AMF Medical'
        AND
            pr.company != 'Advanced Microfluidics SA (OLD)'
        AND
            pr.docstatus = 1
        ORDER BY
            pri.item_code ASC, pri.creation DESC
    """, as_dict=True)

    # Organize data by item_code
    items_data = {}
    for row in purchase_data:
        adjusted_rate = row["net_rate"] / (row["conversion_factor"] or 1)
        if row["item_code"] not in items_data:
            items_data[row["item_code"]] = []
        items_data[row["item_code"]].append(adjusted_rate)

    # Calculate ratio for each item
    for item_code, rates in items_data.items():
        if len(rates) >= 2:
            last_rate = rates[0]
            previous_rate = rates[1]
            if previous_rate != 0:
                ratio = last_rate / previous_rate
                items_with_ratios[item_code] = ratio

    # Filter out items with None ratio and sort by item_code (ascending)
    valid_ratios = {k: v for k, v in items_with_ratios.items() if v is not None}
    ratio_values = sorted(valid_ratios.values())

    # Remove the first 3 and last 3 extremes
    if len(ratio_values) > 6:  # Ensure enough data points to exclude extremes
        trimmed_ratios = ratio_values[3:-3]
    else:
        trimmed_ratios = ratio_values  # Not enough data to exclude extremes

    # Calculate mean of the trimmed ratios
    if trimmed_ratios:
        mean_ratio = sum(trimmed_ratios) / len(trimmed_ratios)
    else:
        mean_ratio = None  # No valid ratios to calculate mean
        
    return mean_ratio

def get_internal_vs_external_production():
    # Define item groups and pattern for 6-digit item codes
    item_groups = ["Plug", "Valve Seat"]
    item_code_pattern = "_.0___"  # Regex for second digit being 0 in a 6-digit item code
    
    # Query to get the total quantity of internally produced items
    internal_query = """
        SELECT
            SUM(wo.produced_qty) AS internal_qty
        FROM
            `tabWork Order` wo
        JOIN
            `tabItem` i ON wo.production_item = i.name
        WHERE
            i.item_group IN %(item_groups)s
            AND i.item_code REGEXP %(item_code_pattern)s
            AND wo.machine IS NOT NULL
    """
    internal_data = frappe.db.sql(
        internal_query, 
        {"item_groups": item_groups, "item_code_pattern": item_code_pattern}, 
        as_dict=True
    )
    internal_qty = internal_data[0].get("internal_qty", 0) or 0

    # Query to get the total quantity of externally produced items
    external_query = """
        SELECT
            SUM(pri.received_qty) AS external_qty
        FROM
            `tabPurchase Receipt Item` pri
        JOIN
            `tabItem` i ON pri.item_code = i.name
        WHERE
            i.item_group IN %(item_groups)s
            AND pri.item_code REGEXP %(item_code_pattern)s
    """
    external_data = frappe.db.sql(
        external_query, 
        {"item_groups": item_groups, "item_code_pattern": item_code_pattern}, 
        as_dict=True
    )
    external_qty = external_data[0].get("external_qty", 0) or 0

    # Return the result
    return {
        "internal_produced_qty": internal_qty,
        "external_produced_qty": external_qty
    }
    
def compare_internal_vs_external_manufacturing():
    """
    Compares the quantity of items manufactured internally vs externally by semester and year,
    split between 'Plug' and 'Valve Seat'.
    Internal: 'quantite_validee' field from the 'Planning' doctype.
    External: Submitted Purchase Receipt Items.

    Returns:
        str: Tabulated string containing the manufacturing quantities split by item group.
    """
    # Fetch internal manufacturing quantities split by item group
    internal_quantities = frappe.db.sql(
        """
        SELECT 
            YEAR(pl.creation) AS year,
            CEIL(MONTH(pl.creation) / 6) AS semester,
            it.item_group AS item_group,
            SUM(pl.quantite_validee) AS internal_qty
        FROM `tabPlanning` pl
        JOIN `tabItem` it ON it.name = pl.item_code
        WHERE it.item_group IN ('Plug', 'Valve Seat')
        GROUP BY year, semester, item_group
        """,
        as_dict=True
    )

    # Fetch external manufacturing quantities split by item group
    external_quantities = frappe.db.sql(
        """
        SELECT 
            YEAR(pr.posting_date) AS year,
            CEIL(MONTH(pr.posting_date) / 6) AS semester,
            it.item_group AS item_group,
            SUM(pri.qty) AS external_qty
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        JOIN `tabItem` it ON it.name = pri.item_code
        WHERE pr.docstatus = 1
        AND it.item_group IN ('Plug', 'Valve Seat')
        GROUP BY year, semester, item_group
        """,
        as_dict=True
    )

    # Organize data into a structured list for tabulation
    table = []
    headers = ["Year", "Semester", "Item Group", "Internal Qty", "External Qty"]

    # Populate table with internal quantities
    for row in internal_quantities:
        year, semester, item_group = row["year"], row["semester"], row["item_group"]
        table.append([
            year,
            semester,
            item_group,
            row["internal_qty"],
            0  # Placeholder for external qty
        ])
        

    # Update table with external quantities
    for row in external_quantities:
        year, semester, item_group = row["year"], row["semester"], row["item_group"]
        for entry in table:
            if entry[0] == year and entry[1] == semester and entry[2] == item_group:
                entry[4] = row["external_qty"]
                break
        else:
            table.append([
                year,
                semester,
                item_group,
                0,  # Placeholder for internal qty
                row["external_qty"]
            ])

    print(table)
    # Generate tabulated output independent of window size
    tabulated_output = tabulate(table, headers=headers, tablefmt="grid", numalign="right", stralign="left")

    return tabulated_output