import http
import json
import os
import re
from turtle import pd
import urllib.parse
import frappe
import requests
import csv
from frappe.utils import now_datetime, add_months
import pandas as pd

# DHL API details
DHL_API_URL = "https://api-eu.dhl.com/track/shipments"

@frappe.whitelist()
def get_tracking_numbers():

    three_months_ago = add_months(now_datetime(), -3)

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
    
    API_KEY = frappe.get_value("ERPNext AMF Settings", "ERPNext AMF Settings", "dhl_api_key")

    params = urllib.parse.urlencode({
        'trackingNumber': tracking_number,
        'service': 'express'
    })
    headers = {
        'Accept': 'application/json',
        "DHL-API-Key": API_KEY
    }
    connection = http.client.HTTPSConnection("api-eu.dhl.com")
    connection.request("GET", "/track/shipments?" + params, "", headers)
    response = connection.getresponse()
    data = response.read()
    #print(response.status)
    if response.status == 200:
        return json.loads(data)
    else:
        return None

@frappe.whitelist()
def fetch_and_display_tracking_info():
    tracking_infos = get_tracking_numbers()  # Call the function to get tracking numbers and customers
    tracking_data = []
    for info in tracking_infos:
        name = info['name']
        tracking_number = info['tracking_no']
        customer = info['customer']
        date = info['date']
        
        # Initialize the tracking data with default values
        tracking_entry = {
            "name": name,
            "tracking_number": tracking_number,
            "customer": customer,
            "date": date,
            "status": "Unknown",  # Default value for status
            "last_update": "N/A"  # Default value for last_update
        }

        api_info = get_tracking_info(tracking_number)
        if api_info and 'shipments' in api_info and len(api_info['shipments']) > 0:
            shipment_info = api_info['shipments'][0]
            tracking_entry["status"] = shipment_info['status']['description'],  # Adjust based on the actual API response structure
            tracking_entry["last_update"] = shipment_info['status']['timestamp'],  # Adjust based on the actual API response structure

        tracking_data.append(tracking_entry)

        # # Read existing data from the file if it exists
        # if os.path.exists("data.txt"):
        #     with open("data.txt", "r") as file:
        #         try:
        #             existing_data = json.load(file)
        #             if existing_data is None:
        #                 existing_data = []
        #         except json.JSONDecodeError:
        #             existing_data = []
        # else:
        #     existing_data = []

        # # Append the new api_info to the existing data
        # existing_data.append(api_info)

        # # Write the updated data back to the file
        # with open("data.txt", "w") as file:
        #     file.write(json.dumps(existing_data, indent=4))
            
    # Insert tracking data into the database
    for data in tracking_data:
        existing_doc = frappe.get_all('DHL Tracking Information', filters={'tracking_number': data['tracking_number']}, limit=1)
        
        if existing_doc:
            # Update the existing document
            doc = frappe.get_doc('DHL Tracking Information', existing_doc[0].name)
            doc.status = data['status']
            doc.last_update = data['last_update']
            doc.save()
        else:
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


