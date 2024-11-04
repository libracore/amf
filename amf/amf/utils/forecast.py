from frappe.core.doctype.communication.email import make
import frappe

test_mode = False

def get_item_details_and_quantities():
    item_codes = [
        "C100", "C101", "C102", "C103", "C201", "C202", "C203", "C204",
        "K101", "K100-12", "K100-6", "T100",
        "S-1000-P", "S-100-P", "S-250-P", "S-500-P", "S-50-P", "S-2500-P", "S-5000-P",
        "300002", "300003", "300005", "300006", "300007", "300009", "300010", "300012", "300013", "300014", "300016", "300017", "300019", "300020", "300021", "300022", "300023", "300024", "300025", "300026", "300029", "300030", "300031", "300032", "300033", "300034", "300035", "300036", "300037", "300038", "300039", "300040", "300041", "300042", "300043", "300044", "300045", "300046", "300049", "300052", "300055", "300057", "300058", "300059", "300060", "300061", "300064", "300065", "300066", "300067", "300068", "300069", "300070", "300072", "300073", "300074", "300075", "300076", "300077", "300078", "300079", "300080", "300081", "310050",
        "320221", "522100", "521101", "521100", "520101", "520103", "520102", "320202", "320203", "320201", "520100", "320200", "520000", "320101", "510100", "320100", "510000", "320102", "510010", "540000"
    ]
    warehouses = ["Main Stock - AMF21", "Assemblies - AMF21", "Work In Progress - AMF21"]

    # Constructing the query
    items_details_query = """
    SELECT 
        i.item_code, i.item_name, i.item_group, ip.price_list_rate AS unit_price
    FROM 
        `tabItem` i
    LEFT JOIN 
        `tabItem Price` ip ON i.item_code = ip.item_code
    WHERE 
        i.item_code IN ({})
        AND ip.price_list = 'Price List 2023 AMF CHF'
    ORDER BY 
        i.item_group, i.item_code
    """.format(','.join(['%s'] * len(item_codes)))  # SQL placeholders for item codes

    items_details = frappe.db.sql(items_details_query, item_codes, as_dict=True)

    # Mapping item codes to details for easier lookup
    items_map = {item['item_code']: item for item in items_details}

    # Query to fetch total quantities from specified warehouses
    quantities_query = """
    SELECT 
        item_code, SUM(actual_qty) as total_qty
    FROM 
        `tabBin` 
    WHERE 
        item_code IN ({}) AND warehouse IN ({})
    GROUP BY 
        item_code
    """.format(','.join(['%s'] * len(item_codes)), ','.join(['%s'] * len(warehouses)))

    total_quantities = frappe.db.sql(quantities_query, item_codes + warehouses, as_dict=True)

    # Adding quantities to items_map
    for qty in total_quantities:
        if qty['item_code'] in items_map:
            items_map[qty['item_code']].update({'total_qty': qty['total_qty']})
    
    generate_html_table(list(items_map.values()))
    print("Done get_item_details_and_quantities()")
    return None

def generate_html_table(items_details):
    base_url = "https://amf.libracore.ch/desk#Form/Item/"
    html_content = """
    <style>
        table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Courier New', Courier, monospace; /* Applying Courier New font */
        }
        th {
            background-color: #2b47d9;
            color: white;
            padding: 4px;
            text-align: left;
        }
        td {
            padding: 4px;
            border: 1px solid #ddd;
            text-align: left;
        }
        tr:nth-child(even) {background-color: #f2f2f2;}
        .low-quantity {
            background-color: #f8d7da !important; /* Light red for low quantity */
        }
    </style>
    <table>
        <tr>
            <th>ITEM CODE</th>
            <th>ITEM NAME</th>
            <th>ITEM GROUP</th>
            <th>UNIT PRICE</th>
            <th>TOTAL QUANTITY</th>
        </tr>
    """

    for item in items_details:
        # Applying the 'low-quantity' class for items with total quantity below 10
        row_class = "low-quantity" if item.get('total_qty', 0) < 5 else ""
        item_url = f"{base_url}{item.get('item_code')}"
        html_content += f"""
        <tr class="{row_class}">
            <td><a href='{item_url}'>{item.get('item_code', '')}</a></td>
            <td>{item.get('item_name', '')}</td>
            <td>{item.get('item_group', '')}</td>
            <td>{item.get('unit_price', '')} CHF</td>
            <td>{item.get('total_qty', 0)}</td>
        </tr>
        """

    html_content += "</table>"
    
    if test_mode: print(html_content)
    send_email_forecast(html_content)

    print("Done generate_html_table()")
    return None

def send_email_forecast(email_content):
    # Creating email context
    email_context = {
        'recipients': ['sales@amf.ch', 'nathan.favereau@amf.ch'],
        'content': email_content,
        'subject': "Weekly Availibity of Standard Items",
        'communication_medium': 'Email',
        'send_email': True,
        'cc': 'alexandre.ringwald@amf.ch',
        'attachments': [],  # Add any attachments if necessary
    }

    # Creating communication and sending email
    try:
        comm = make(**email_context)
        print("'make' email return successfully.")
        return comm
    except AttributeError as e:
        print(f"AttributeError occurred: {str(e)}")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")