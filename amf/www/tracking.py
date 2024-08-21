import http
import json
import re
#from turtle import pd      # compatibility issue with TKInter
import urllib.parse
from amf.amf.utils.utilities import create_log_entry, update_log_entry
import frappe
from frappe.utils import now_datetime, add_months
import time

# DHL API details
DHL_API_URL = "https://api-eu.dhl.com/track/shipments"

@frappe.whitelist()
def fetch_and_display_tracking_info_enqueue():
    enqueue("amf.www.tracking.fetch_and_display_tracking_info", queue='long', tiemout=15000)
    return None

@frappe.whitelist()
def get_tracking_numbers():

    three_months_ago = add_months(now_datetime(), -1)

    # Fetch all delivery notes with the tracking_no and customer field
    delivery_notes = frappe.get_all(
        'Delivery Note',
        filters={'posting_date': ['>=', three_months_ago]},
        fields=['name', 'tracking_no', 'customer', 'posting_date'],
        order_by='posting_date desc'
    )
    
    # Filter to include only 10-digit numeric tracking numbers
    tracking_info = [
        {'name': dn['name'], 'tracking_no': dn['tracking_no'], 'customer': dn['customer'], 'date': dn['posting_date']}
        for dn in delivery_notes
        if dn['tracking_no'] and re.match(r'^\d{10}$', dn['tracking_no'])
    ]
    return tracking_info

def get_tracking_info(tracking_number):
    
    API_KEY = frappe.db.get_single_value("AMF DHL Settings", "dhl_api_key")

    params = urllib.parse.urlencode({
        'trackingNumber': tracking_number,
    })
    headers = {
        "DHL-API-Key": API_KEY
    }
    connection = http.client.HTTPSConnection("api-eu.dhl.com")
    connection.request("GET", "/track/shipments?" + params, "", headers)
    response = connection.getresponse()
    data = response.read()
    # Assuming response.status is an integer, convert it to a string
    status = str(response.status)
    # Convert the data to a JSON formatted string
    json_data = json.dumps(json.loads(data), indent=4)  # Adding indent for better readability, optional
    # Open the file and write the data
    with open("output.txt", "a+") as text_file:
        text_file.write(status + "\n" + json_data + "\n")
    #print(response.status + "\n" + json.loads(data) + "\n")
    if response.status == 200:
        print("Status:", response.status, "Reason:", response.reason)
        return json.loads(data)
    else:
        print("Error:", response.status, "Reason:", response.reason)
        return None

@frappe.whitelist()
def fetch_and_display_tracking_info():
    log = create_log_entry("Starting amf.amf.www.tracking method...", "fetch_and_display_tracking_info()")
    tracking_infos = get_tracking_numbers()  # Call the function to get tracking numbers and customers
    tracking_data = []
    update_log_entry(log, f"Tracking Numbers & Info Global: {tracking_infos}")
    for info in tracking_infos:
        time.sleep(12)
        api_info = get_tracking_info(info['tracking_no'])
        if api_info and 'shipments' in api_info and len(api_info['shipments']) > 0:
            shipment_info = api_info['shipments'][0]
            tracking_info_dict = {
                'name': info['name'],
                'tracking_number': info['tracking_no'],
                'customer': info['customer'],
                'date': info['date'],
                'status': shipment_info['status']['description'],  # Adjust based on the actual API response structure
                'last_update': shipment_info['status']['timestamp'],  # Adjust based on the actual API response structure
            }
        else:
            tracking_info_dict = {
                'name': info['name'],
                'tracking_number': info['tracking_no'],
                'customer': info['customer'],
                'date': info['date'],
                'status': '',
                'last_update': '',
                'destination': ''
            }
        update_log_entry(log, f"Tracking No: {info['tracking_no']} for Tracking Info: {tracking_info_dict}")
        try:
            tracking_data.append(tracking_info_dict)
        except Exception as e:
            print("Error in tracking_data:", {e})

    # Insert tracking data into the database
    for data in tracking_data:
        existing_doc = frappe.get_all('DHL Tracking Information', filters={'tracking_number': data['tracking_number']}, limit=1)
        
        if existing_doc:
            update_log_entry(log, f"Updating existing doc: {existing_doc[0].name}")
            # Update the existing document
            doc = frappe.get_doc('DHL Tracking Information', existing_doc[0].name)
            doc.status = data['status']
            doc.last_update = data['last_update']
            doc.save()
        else:
            update_log_entry(log, f"Creating new doc...")
            # Insert a new document
            frappe.get_doc({
                'doctype': 'DHL Tracking Information',
                'dn': data['name'],
                'tracking_number': data['tracking_number'],
                'customer': data['customer'],
                'fetch_date': data['date'],
                'status': data['status'],
                'last_update': data['last_update']
            }).insert()
        
        frappe.db.commit()