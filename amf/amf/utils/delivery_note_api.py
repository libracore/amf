import frappe
from amf.amf.utils.qr_code_generator import generate_qr_code
import os
from frappe.desk.form.assign_to import add as assign_to_add


@frappe.whitelist()
def generate_serial_number_qr_codes(stock_entry):
    doc = frappe.get_doc("Stock Entry", stock_entry)
    stock_entry_qr = []
    for item in doc.items:
        if item.serial_no:
            serial_numbers = item.serial_no.split('\n')
            for serial_number in serial_numbers:
                if serial_number.strip():
                    qr_code_base64 = generate_qr_code(serial_number)
                    stock_entry_qr.append(
                        {"serial_number": serial_number, "qr_code": qr_code_base64})
                    # Create a new child table entry for each QR code
                    doc.append('stock_entry_qr', {
                               "serial_number": serial_number, "qr_code": qr_code_base64})
    doc.save()  # Save the document to persist the new child table entries
    doc.reload()
    return stock_entry_qr


def update_sales_order(doc, method):
    # Dictionary to store aggregated quantities
    item_qty_map = {}
    print("doc.items:", doc.items)
    # Loop through the items in the Delivery Note
    sales_order_ref = None
    for item in doc.items:
        if sales_order_ref == None:
            sales_order_ref = item.against_sales_order
        item_code = item.item_code
        quantity = item.qty
        batch = item.batch_no
        print("item_code:", item_code)
        print("quantity:", quantity)
        print("batch:", batch)
        # Aggregate the quantity based on item code
        if item_code in item_qty_map:
            item_qty_map[item_code] += quantity
        else:
            item_qty_map[item_code] = quantity
    print("item_qty_map:", item_qty_map)
    print("sales_order_ref:", sales_order_ref)
    # Get the Sales Order linked with the Delivery Note
    sales_order = frappe.get_doc("Sales Order", sales_order_ref)

    # Loop through the items in the Sales Order and update the delivered quantity
    for item in sales_order.items:
        item_code = item.item_code

        if item_code in item_qty_map:
            # Update the delivered_qty field (assuming it exists)
            item.delivered_qty = item_qty_map[item_code]

    # Get the DocType
    doctype = frappe.get_doc("DocType", "Sales Order Item")

    # Loop through the fields to find the one you want
    for field in doctype.fields:
        if field.fieldname == 'delivered_qty':
            # Change the "Allow on Submit" setting
            if field.allow_on_submit == 0:
                field.allow_on_submit = 1

    # Save the changes
    doctype.save()

    # Bypass read-only restriction
    # sales_order.flags.ignore_permissions = True

    # Save the updated Sales Order
    sales_order.save()


@frappe.whitelist()
def generate_dhl(delivery_note_id):
    delivery_note = frappe.get_doc('Delivery Note', delivery_note_id)
    lines = []

    country_mapping = {
        'United States': 'US',
        'Canada': 'CA',
        'Afghanistan': 'AF',
        'Albania': 'AL',
        'Algeria': 'DZ',
        'American Samoa': 'AS',
        'Andorra': 'AD',
        'Angola': 'AO',
        'Anguilla': 'AI',
        'Antarctica': 'AQ',
        'Antigua and Barbuda': 'AG',
        'Argentina': 'AR',
        'Armenia': 'AM',
        'Aruba': 'AW',
        'Australia': 'AU',
        'Austria': 'AT',
        'Azerbaijan': 'AZ',
        'Bahamas (the)': 'BS',
        'Bahrain': 'BH',
        'Bangladesh': 'BD',
        'Barbados': 'BB',
        'Belarus': 'BY',
        'Belgium': 'BE',
        'Belize': 'BZ',
        'Benin': 'BJ',
        'Bermuda': 'BM',
        'Bhutan': 'BT',
        'Bolivia (Plurinational State of)': 'BO',
        'Bonaire, Sint Eustatius and Saba': 'BQ',
        'Bosnia and Herzegovina': 'BA',
        'Botswana': 'BW',
        'Bouvet Island': 'BV',
        'Brazil': 'BR',
        'British Indian Ocean Territory (the)': 'IO',
        'Brunei Darussalam': 'BN',
        'Bulgaria': 'BG',
        'Burkina Faso': 'BF',
        'Burundi': 'BI',
        'Cabo Verde': 'CV',
        'Cambodia': 'KH',
        'Cameroon': 'CM',
        'Canada': 'CA',
        'Cayman Islands (the)': 'KY',
        'Central African Republic (the)': 'CF',
        'Chad': 'TD',
        'Chile': 'CL',
        'China': 'CN',
        'Christmas Island': 'CX',
        'Cocos (Keeling) Islands (the)': 'CC',
        'Colombia': 'CO',
        'Comoros (the)': 'KM',
        'Congo (the Democratic Republic of the)': 'CD',
        'Congo (the)': 'CG',
        'Cook Islands (the)': 'CK',
        'Costa Rica': 'CR',
        'Croatia': 'HR',
        'Cuba': 'CU',
        'Curaçao': 'CW',
        'Cyprus': 'CY',
        'Czechia': 'CZ',
        'Denmark': 'DK',
        'Djibouti': 'DJ',
        'Dominica': 'DM',
        'Dominican Republic (the)': 'DO',
        'Ecuador': 'EC',
        'Egypt': 'EG',
        'El Salvador': 'SV',
        'Equatorial Guinea': 'GQ',
        'Eritrea': 'ER',
        'Estonia': 'EE',
        'Eswatini': 'SZ',
        'Ethiopia': 'ET',
        'Falkland Islands (the) [Malvinas]': 'FK',
        'Faroe Islands (the)': 'FO',
        'Fiji': 'FJ',
        'Finland': 'FI',
        'France': 'FR',
        'French Guiana': 'GF',
        'French Polynesia': 'PF',
        'French Southern Territories (the)': 'TF',
        'Gabon': 'GA',
        'Gambia (the)': 'GM',
        'Georgia': 'GE',
        'Germany': 'DE',
        'Ghana': 'GH',
        'Gibraltar': 'GI',
        'Greece': 'GR',
        'Greenland': 'GL',
        'Grenada': 'GD',
        'Guadeloupe': 'GP',
        'Guam': 'GU',
        'Guatemala': 'GT',
        'Guernsey': 'GG',
        'Guinea': 'GN',
        'Guinea-Bissau': 'GW',
        'Guyana': 'GY',
        'Haiti': 'HT',
        'Heard Island and McDonald Islands': 'HM',
        'Holy See (the)': 'VA',
        'Honduras': 'HN',
        'Hong Kong': 'HK',
        'Hungary': 'HU',
        'Iceland': 'IS',
        'India': 'IN',
        'Indonesia': 'ID',
        'Iran (Islamic Republic of)': 'IR',
        'Iraq': 'IQ',
        'Ireland': 'IE',
        'Isle of Man': 'IM',
        'Israel': 'IL',
        'Italy': 'IT',
        'Jamaica': 'JM',
        'Japan': 'JP',
        'Jersey': 'JE',
        'Jordan': 'JO',
        'Kazakhstan': 'KZ',
        'Kenya': 'KE',
        'Kiribati': 'KI',
        'Korea (the Republic of)': 'KR',
        'Kuwait': 'KW',
        'Kyrgyzstan': 'KG',
        'Latvia': 'LV',
        'Lebanon': 'LB',
        'Lesotho': 'LS',
        'Liberia': 'LR',
        'Libya': 'LY',
        'Liechtenstein': 'LI',
        'Lithuania': 'LT',
        'Luxembourg': 'LU',
        'Macao': 'MO',
        'Madagascar': 'MG',
        'Malawi': 'MW',
        'Malaysia': 'MY',
        'Maldives': 'MV',
        'Mali': 'ML',
        'Malta': 'MT',
        'Marshall Islands (the)': 'MH',
        'Martinique': 'MQ',
        'Mauritania': 'MR',
        'Mauritius': 'MU',
        'Mayotte': 'YT',
        'Mexico': 'MX',
        'Micronesia (Federated States of)': 'FM',
        'Moldova (the Republic of)': 'MD',
        'Monaco': 'MC',
        'Mongolia': 'MN',
        'Montenegro': 'ME',
        'Montserrat': 'MS',
        'Morocco': 'MA',
        'Mozambique': 'MZ',
        'Myanmar': 'MM',
        'Namibia': 'NA',
        'Nauru': 'NR',
        'Nepal': 'NP',
        'Netherlands (the)': 'NL',
        'New Caledonia': 'NC',
        'New Zealand': 'NZ',
        'Nicaragua': 'NI',
        'Niger (the)': 'NE',
        'Nigeria': 'NG',
        'Niue': 'NU',
        'Norfolk Island': 'NF',
        'Northern Mariana Islands (the)': 'MP',
        'Norway': 'NO',
        'Oman': 'OM',
        'Pakistan': 'PK',
        'Palau': 'PW',
        'Palestine, State of': 'PS',
        'Panama': 'PA',
        'Papua New Guinea': 'PG',
        'Paraguay': 'PY',
        'Peru': 'PE',
        'Philippines (the)': 'PH',
        'Pitcairn': 'PN',
        'Poland': 'PL',
        'Portugal': 'PT',
        'Puerto Rico': 'PR',
        'Qatar': 'QA',
        'Republic of North Macedonia': 'MK',
        'Romania': 'RO',
        'Russian Federation (the)': 'RU',
        'Rwanda': 'RW',
        'Réunion': 'RE',
        'Saint Barthélemy': 'BL',
        'Saint Helena, Ascension and Tristan da Cunha': 'SH',
        'Saint Kitts and Nevis': 'KN',
        'Saint Lucia': 'LC',
        'Saint Martin (French part)': 'MF',
        'Saint Pierre and Miquelon': 'PM',
        'Saint Vincent and the Grenadines': 'VC',
        'Samoa': 'WS',
        'San Marino': 'SM',
        'Sao Tome and Principe': 'ST',
        'Saudi Arabia': 'SA',
        'Senegal': 'SN',
        'Serbia': 'RS',
        'Seychelles': 'SC',
        'Sierra Leone': 'SL',
        'Singapore': 'SG',
        'Sint Maarten (Dutch part)': 'SX',
        'Slovakia': 'SK',
        'Slovenia': 'SI',
        'Solomon Islands': 'SB',
        'Somalia': 'SO',
        'South Africa': 'ZA',
        'South Georgia and the South Sandwich Islands': 'GS',
        'South Sudan': 'SS',
        'Spain': 'ES',
        'Sri Lanka': 'LK',
        'Sudan (the)': 'SD',
        'Suriname': 'SR',
        'Svalbard and Jan Mayen': 'SJ',
        'Sweden': 'SE',
        'Switzerland': 'CH',
        'Syrian Arab Republic': 'SY',
        'Taiwan (Province of China)': 'TW',
        'Tajikistan': 'TJ',
        'Tanzania, United Republic of': 'TZ',
        'Thailand': 'TH',
        'Timor-Leste': 'TL',
        'Togo': 'TG',
        'Tokelau': 'TK',
        'Tonga': 'TO',
        'Trinidad and Tobago': 'TT',
        'Tunisia': 'TN',
        'Turkey': 'TR',
        'Turkmenistan': 'TM',
        'Turks and Caicos Islands (the)': 'TC',
        'Tuvalu': 'TV',
        'Uganda': 'UG',
        'Ukraine': 'UA',
        'United Arab Emirates (the)': 'AE',
        'United Kingdom of Great Britain and Northern Ireland (the)': 'GB',
        'United States Minor Outlying Islands (the)': 'UM',
        'United States of America (the)': 'US',
        'Uruguay': 'UY',
        'Uzbekistan': 'UZ',
        'Vanuatu': 'VU',
        'Venezuela (Bolivarian Republic of)': 'VE',
        'Viet Nam': 'VN',
        'Virgin Islands (British)': 'VG',
        'Virgin Islands (U.S.)': 'VI',
        'Wallis and Futuna': 'WF',
        'Western Sahara': 'EH',
        'Yemen': 'YE',
        'Zambia': 'ZM',
        'Zimbabwe': 'ZW',
        'Åland Islands': 'AX',
    }

    for item in delivery_note.items:
        # Split the commodity code by the period
        parts = item.get("customs_tariff_number", "").split(".")
        first_part = parts[0]
        second_part = parts[1] if len(parts) > 1 else ""
        subpart1, subpart2 = second_part[:2], second_part[2:]
        formatted_commodity_code = "{}.{}.{}".format(
            first_part, subpart1, subpart2)
        # Map the country of origin to a 2-letter code
        country_of_origin_code = country_mapping.get(
            item.get("country_of_origin", ""), "")

        item_line = "1|INV_ITEM|{item_name}|{item_commodity_code}|{qty}|PCS|{net_rate}|{currency}|{weight_per_unit}||{country_of_origin}|MID|{item_code}||".format(
            item_name=item.item_name,
            # Assuming customs_tariff_number is a custom field
            item_commodity_code=formatted_commodity_code,
            qty=int(item.qty),
            net_rate=item.net_rate,
            currency=delivery_note.currency,
            weight_per_unit=item.weight_per_unit,
            country_of_origin=country_of_origin_code,
            item_code=item.item_code
        )
        lines.append(item_line)

    dhl_data = '\n'.join(lines)

    # Define the directory where the file will be saved
    file_directory = '/tmp/'
    if not os.path.exists(file_directory):
        os.makedirs(file_directory)

    # Define the complete path
    file_path = os.path.join(
        file_directory, 'dhl_file_{}.txt'.format(delivery_note_id))

    # Write data to the txt file
    with open(file_path, 'w') as f:
        f.write(dhl_data)

    # Define a filename
    file_name = 'dhl_file_{}.txt'.format(delivery_note_id)

    # Use save_file to save and attach the file to the Delivery Note
    attach_file = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "attached_to_doctype": 'Delivery Note',
        "attached_to_name": delivery_note_id,
        "content": dhl_data,
        "is_private": 0
    }).insert()

    return {"status": "success", "data": dhl_data, "message": "File has been successfully generated"}


def check_serial_nos(doc, method):
    test_mode = False
    # Iterate over all Delivery Note Items
    for item in doc.items:
        if test_mode:
            print("item:", item.name)
        serial_no_list = []
        # Fetch the 'has_serial_no' field value from the linked Item
        item_details = frappe.get_doc('Item', item.item_code)
        if test_mode:
            print("item_details:", item_details.name)
        if item_details.has_serial_no:
            if test_mode:
                print("has_serial_no")
            # If the Item requires a serial number, proceed to find linked Work Orders
            sales_order_linked = item.against_sales_order
            if test_mode:
                print(sales_order_linked)
            if sales_order_linked:
                work_orders = frappe.get_list('Work Order',
                                              filters={
                                                  'sales_order': sales_order_linked,
                                                  'status': ['in', ['Completed', 'In Progress']]
                                              },
                                              fields=['name'])
                if test_mode:
                    print("work_orders:", work_orders)
                for wo in work_orders:
                    # Fetch Stock Entries linked to this Work Order
                    stock_entries = frappe.get_list('Stock Entry',
                                                    filters={
                                                        'work_order': wo.name, 'docstatus': 1},
                                                    fields=['name'])

                    for se in stock_entries:
                        # Fetch serial numbers from each Stock Entry Detail
                        serial_numbers = frappe.db.sql("""
                            SELECT serial_no
                            FROM `tabStock Entry Detail`
                            WHERE parent=%s AND docstatus=1
                        """, (se.name), as_dict=1)
                        # Process the fetched serial numbers for both cases
                        if test_mode:
                            print(serial_numbers)
                        for sn in serial_numbers:
                            if sn['serial_no'] and ('\n' in sn['serial_no']):
                                # If serial numbers are concatenated with newline, split and extend the list
                                serial_no_list.extend(
                                    sn['serial_no'].split('\n'))
                            elif sn['serial_no']:
                                # If single serial number, append it to the list
                                serial_no_list.append(sn['serial_no'])

                # Remove any empty strings that might have resulted from splitting
                serial_no_list = [sn for sn in serial_no_list if sn]
                print(serial_no_list)
                if serial_no_list:
                    # Update the custom field in the Delivery Note Item with the serial numbers
                    item.db_set('serial_no', '\n'.join(serial_no_list))


def before_save_dn(doc, method):
    """
    Pre-save hook for Delivery Note to fetch and populate serial numbers from related Work Orders.
    This function checks each delivery note item, fetches related work orders, and gathers serial numbers
    from the stock entries of the 'Manufacture' type, storing them in the 'product_serial_no' field.
    """
    print ("===================AAAAAAAA==================")
    for item in doc.items:
        sales_order = item.against_sales_order
        
        # Log or print sales order for debugging purposes
        if not sales_order:
            frappe.log_error(f"No sales order found for item {item.item_code} in Delivery Note {doc.name}")
            continue  # Skip if no sales order is found

        try:
            # Fetch all Work Orders associated with the sales order and item
            work_orders = frappe.get_all(
                'Work Order', 
                filters={
                    'sales_order': sales_order,
                    'production_item': item.item_code
                }, 
                order_by = 'creation desc',
                fields=['name']
            )

            if not work_orders:
                frappe.log_error(f"No Work Orders found for Sales Order {sales_order} and Item {item.item_code}")
                continue  # Skip if no work orders are found

            serial_nos = []  # Initialize the list to store serial numbers

            for wo in work_orders:
                # Fetch Stock Entries with the purpose 'Manufacture' linked to the Work Order
                stock_entries = frappe.get_all(
                    'Stock Entry',
                    filters={
                        'work_order': wo.name,
                        'purpose': 'Manufacture',  # Only get stock entries with 'Manufacture' purpose
                        'docstatus': 1
                    },
                    order_by='creation asc', 
                    fields=['name']
                )

                if not stock_entries:
                    frappe.log_error(f"No Stock Entries found for Work Order {wo.name}")
                    continue  # Skip if no stock entries are found for this work order

                for stock_entry in stock_entries:
                    # Fetch the complete Stock Entry document
                    stock_entry_doc = frappe.get_doc('Stock Entry', stock_entry.name)

                    if stock_entry_doc.items:
                        # Loop through all rows to find rows with a serial number
                        for item_row in stock_entry_doc.items:
                            if item_row.serial_no:
                                # Append the serial number to the serial_nos list
                                serial_nos.append(item_row.serial_no)
                        
                        if not serial_nos:
                            # Log an error if no serial number found in any item row
                            frappe.log_error(f"No serial numbers found in any items of Stock Entry {stock_entry.name}")
                    else:
                        frappe.log_error(f"No items found in Stock Entry {stock_entry.name}")

            # After processing all stock entries, update the delivery note item field
            if serial_nos:
                all_serials = [s.strip() for s in "\n".join(serial_nos).split("\n") if s.strip()]
                limited_serials = all_serials[:int(item.qty)]
                limited_serials = sorted(limited_serials, key=lambda s: int(s.split("-")[1].lstrip("O")))
                if not item.product_serial_no:
                    item.product_serial_no = '\n'.join(limited_serials)  # Join serial numbers with a newline
                    print(f"{item.item_code}: \n{item.product_serial_no}")
            else:
                item.product_serial_no = None  # Set to None if no serial numbers found
                frappe.log_error(f"No serial numbers found for item {item.item_code} in Delivery Note {doc.name}")

        except Exception as e:
            # Log the exception for troubleshooting
            frappe.log_error(f"Error processing item {item.item_code} in Delivery Note {doc.name}: {str(e)}")

def auto_gen_qa_inspection(doc, method):
    """
    Auto-generate a Quality Inspection document after a Delivery Note is inserted.
    
    Args:
        doc: The Delivery Note document
        method: Hook method parameter (not used here)
    """
    # Global var
    email = "alexandre.trachsel@amf.ch"
    client = doc.get("customer")
    client_name = doc.get("customer_name") or "Client Inconnu"
    
    # Create a new Quality Inspection document
    qi = frappe.new_doc("Global Quality Inspection")
    qi.inspection_type = "Outgoing"
    qi.reference_type = "Delivery Note"
    qi.reference_name = doc.name  # Link the Quality Inspection to the Delivery Note
    qi.inspected_by = email
    qi.status = ''
    qi.customer = client
    
    # # Modify the meta field property to disable the mandatory check for item_code
    # field = qi.meta.get_field("item_code")
    # if field:
    #     field.reqd = 0
    
    # Ignore mandatory validations
    qi.flags.ignore_mandatory = True

    # Optionally, fetch a default Quality Inspection Template for Outgoing inspections.
    # Adjust the filter or field names as necessary based on your implementation.
    template = frappe.db.get_value("Quality Inspection Template", {"name": "Delivery Note"}, "name")
    if template:
        qi.quality_inspection_template = template
        template_readings = frappe.get_all(
            "Item Quality Inspection Parameter",
            {"parent": template},
            ["specification", "value"]
        )
        # Populate the Quality Inspection's readings child table with the template data
        for t in template_readings:
            row = qi.append("readings", {})
            row.specification = t.get("specification")
            row.value         = t.get("value")    
            row.status        = ""
    
    if client:
        client_template = frappe.get_all(
            "Quality Inspection Template",
            {"customer": client},
            ["name"]
            )
        print(client_template)
        if client_template:
            template_name = [tpl.get("name") for tpl in client_template]
            print(template_name[0])
            client_readings = frappe.get_all(
                "Item Quality Inspection Parameter",
                {"parent": template_name[0]},
                ["specification", "value"]
            )
            print(client_readings)
            
            for c in client_readings:
                row = qi.append("client_specific", {})
                row.specification = c.get("specification")
                row.value         = c.get("value")    
                row.status        = ""

    # Insert the new Quality Inspection document (ignoring permissions if necessary)
    qi.insert(ignore_permissions=True)
    
    # Build the assignment message with Delivery Note name and client (assumed to be in 'customer')
    
    assignment_message = f"Inspection Qualité générée pour la Delivery Note: {doc.name} pour le client: {client_name}"

    # Auto assign the Quality Inspection to atr@amf.ch with the message
    # Create assignment arguments using the new add method signature
    assignment_args = {
        "assign_to": email,
        "doctype": "Global Quality Inspection",
        "name": qi.name,
        "description": assignment_message,
        # "assignment_rule": <your_rule_here>,  # Optional if you need to specify an assignment rule.
    }
    assign_to_add(assignment_args)