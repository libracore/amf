import frappe
from frappe.core.doctype.communication.email import make

test_mode = None

def fetch_open_issues():
    """Fetch all open issues from the ERPNext database, then order them dynamically."""
    # Fetch all open issues without filtering by issue_type initially.
    issues = frappe.get_list('Issue',
                             filters={'status': 'Open'},
                             fields=['name', 'subject', 'input_selection', 'issue_type', 'amf_contact', 'creation', 'priority_result', 'amf_person', 'process_owner'],
                             order_by='creation desc')  # Default ordering, adjust if necessary.

    # Dynamic ordering based on input_selection and then by issue_type.
    # Assuming 'input_selection' is a field name to sort by, and you have it available here.
    input_selection = 'input_selection'  # Example, replace with actual field name if different.
    issues.sort(key=lambda x: (x.get(input_selection, "") or "", x.get('issue_type', "") or ""))
    if test_mode:
        print(issues)
    generate_html_report(issues)
    return 'Success Fetch Open Issues'

def generate_html_report(issues):
    """Generate an HTML table report for each process owner from a list of issues."""
    # Group issues by process_owner
    issues_by_owner = {}
    html_content = ""
    for issue in issues:
        # Ensure there's a default value for process_owner if it's None or not set
        process_owner = issue.get('process_owner') or 'No Owner Assigned'
        if process_owner not in issues_by_owner:
            issues_by_owner[process_owner] = []
        issues_by_owner[process_owner].append(issue)

    owner_emails = []

    # Generate and print/send HTML content for each process owner
    for owner, issues in issues_by_owner.items():
        if owner not in owner_emails and owner != 'No Owner Assigned':
            owner_emails.append(owner)  # Append unique email addresses
        
        html_content += f"<h3>Issues for {owner}</h3>"
        html_content += "<table border='1'><tr><th>ID</th><th>Subject</th><th>Input</th><th>Issue Type</th><th>Raised By</th><th>Created On</th><th>Priority</th></tr>"
        for issue in issues:
            # Construct the URL for each issue
            issue_url = f"https://amf.libracore.ch/desk#Form/Issue/{issue['name']}"
            # Embed the issue name within an anchor (<a>) tag to make it clickable
            html_content += f"<tr><td><a href='{issue_url}' target='_blank'>{issue['name']}</a></td><td>{issue['subject']}</td><td>{issue['input_selection']}</td><td>{issue['issue_type']}</td><td>{issue['amf_contact']}</td><td>{issue['creation']}</td><td>{issue['priority_result']}</td></tr>"
        html_content += "</table><br>"

        if test_mode:
            print(html_content)
    
    send_email_report(html_content, owner_emails)  # Send report to each owner

    return 'Generate HTML Report Issues'

def send_email_report(html_content, owner_emails):
    """Send customized reports to process_owner and amf_contact."""
    # Assuming email_content generation is done outside this function and passed as an argument
    # Generate reports for process_owner and amf_contact  
    email_content = f"Please find attached the report of open issues as of today. <br>{html_content}"

    email_context = {
            'recipients': owner_emails,
            'content': email_content,
            'subject': "Weekly Open Issues Report",
            'communication_medium': 'Email',
            'send_email': True,
            'cc': '',  # Adjust CC as necessary
            'attachments': [],  # Add any attachments if necessary
        }

        # Creating communication and sending email
    try:
        comm = make(**email_context)
        print(f"'make' email sent successfully to {owner_emails}.")
        return comm
    except AttributeError as e:
        print(f"AttributeError occurred: {str(e)}")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
