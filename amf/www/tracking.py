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
    #print(response.status)
    
    # Assuming response.status is an integer, convert it to a string
    status = str(response.status)
    # Convert the data to a JSON formatted string
    json_data = json.dumps(json.loads(data), indent=4)  # Adding indent for better readability, optional
    # Open the file and write the data
    with open("output.txt", "a+") as text_file:
        text_file.write(status + "\n" + json_data + "\n")
    #print(response.status + "\n" + json.loads(data) + "\n")
    if response.status == 200:
        return json.loads(data)
    else:
        print("Error:", response.status, "Reason:", response.reason)
        return None

@frappe.whitelist()
def fetch_and_display_tracking_info():
    tracking_infos = get_tracking_numbers()  # Call the function to get tracking numbers and customers
    tracking_data = []
    for info in tracking_infos:
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
        tracking_data.append(tracking_info_dict)

    with open("output_data.txt", "w+") as text_file:
        for entry in tracking_data:
            text_file.write(str(entry) + "\n") 
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


