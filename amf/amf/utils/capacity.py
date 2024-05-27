# amf/amf/utils/capacity.py

import datetime
import frappe

WORKING_HOURS_PER_WEEK = 42
WORKING_DAYS_PER_WEEK = 5

# List of public holidays in Switzerland
# Note: Add more holidays based on the specific canton or year
PUBLIC_HOLIDAYS = [
    '01-01',  # New Year's Day
    '01-02',  # Berchtold's Day
    '03-29',
    '04-01',
    '05-09',  # Labour Day
    '05-20',
    '08-01',  # Swiss National Day
    '09-16',
    '12-25',  # Christmas Day
    '12-26'   # St. Stephen's Day
]

def is_public_holiday(date):
    return date.strftime('%m-%d') in PUBLIC_HOLIDAYS

def calculate_working_days(start_date_str, end_date_str):
    # Parse the date strings into datetime.date objects
    start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    current_date = start_date
    working_days = 0
    while current_date <= end_date:
        if current_date.weekday() < WORKING_DAYS_PER_WEEK and not is_public_holiday(current_date):  # Monday to Friday and not a public holiday
            working_days += 1
        current_date += datetime.timedelta(days=1)
    return working_days

def calculate_working_hours(working_days):
    return (working_days / WORKING_DAYS_PER_WEEK) * WORKING_HOURS_PER_WEEK

def get_dates_for_semester(year, semester):
    if semester == 1:
        start_date = datetime.date(year, 1, 1)
        end_date = datetime.date(year, 6, 30)
    else:
        start_date = datetime.date(year, 7, 1)
        end_date = datetime.date(year, 12, 31)
    return start_date, end_date

def calculate_capacity_utilization():
    current_date = datetime.date.today()
    current_year = current_date.year

    if current_date.month <= 6:
        current_semester = 1
    else:
        current_semester = 2

    start_date_semester, _ = get_dates_for_semester(current_year, current_semester)
    start_date_year = datetime.date(current_year, 1, 1)

    working_days_semester = calculate_working_days(start_date_semester.strftime('%Y-%m-%d'), current_date.strftime('%Y-%m-%d'))
    working_days_year = calculate_working_days(start_date_year.strftime('%Y-%m-%d'), current_date.strftime('%Y-%m-%d'))

    working_hours_semester = calculate_working_hours(working_days_semester)
    working_hours_year = calculate_working_hours(working_days_year)

    return {
        'working_days_semester': working_days_semester,
        'working_days_year': working_days_year,
        'working_hours_by_semester': working_hours_semester,
        'working_hours_by_year': working_hours_year
    }

def calculate_downtime():
    capacity_docs = frappe.get_all('Capacity Utilization Rate', fields=['name', 'start', 'stop'])
    total_downtime = datetime.timedelta()

    for doc in capacity_docs:
        capacity_doc = frappe.get_doc('Capacity Utilization Rate', doc.name)
        if capacity_doc.start and capacity_doc.stop:
            total_downtime += capacity_doc.stop - capacity_doc.start
    return (total_downtime.total_seconds() / 3600 / 24), (total_downtime.total_seconds() / 3600 * 0.35)  # Convert seconds to hours

def update_capacity_utilization_rate():
    # Get all documents of Capacity Utilization Rate
    capacity_docs = frappe.get_all('Capacity Utilization Rate', fields=['name'])
    
    # Calculate values
    utilization_data = calculate_capacity_utilization()
    total_downtime_days, total_downtime_hours = calculate_downtime()

    # Calculate working hours for machines
    working_hours_machine_semester = utilization_data['working_hours_by_semester'] - total_downtime_hours
    working_hours_machine_year = utilization_data['working_hours_by_year'] - total_downtime_hours

    working_days_machine_semester = utilization_data['working_days_semester'] - total_downtime_days
    working_days_machine_year = utilization_data['working_days_year'] - total_downtime_days
    
    for doc in capacity_docs:
        # Fetch the document
        capacity_doc = frappe.get_doc('Capacity Utilization Rate', doc.name)
        
        # Update fields
        capacity_doc.working_days_semester = utilization_data['working_days_semester']
        capacity_doc.working_days_year = utilization_data['working_days_year']
        capacity_doc.working_hours_by_semester = utilization_data['working_hours_by_semester']
        capacity_doc.working_hours_by_year = utilization_data['working_hours_by_year']
        capacity_doc.working_hours_machine_semester = working_hours_machine_semester
        capacity_doc.working_hours_machine_year = working_hours_machine_year
        capacity_doc.working_days_machine_semester = working_days_machine_semester
        capacity_doc.working_days_machine_year = working_days_machine_year

        # Calculate and update capacity utilization rates
        capacity_doc.capacity_utilization_rate_semester = (working_hours_machine_semester / utilization_data['working_hours_by_semester']) * 100
        capacity_doc.capacity_utilization_rate_year = (working_hours_machine_year / utilization_data['working_hours_by_year']) * 100
        
        # Save the document
        capacity_doc.save()
    
    # Commit the changes
    frappe.db.commit()
