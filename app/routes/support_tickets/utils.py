# MYVINECHURCH.ONLINE/app/routes/support_tickets/utils.py
# Full path: MYVINECHURCH.ONLINE/app/routes/support_tickets/utils.py
# File name: utils.py
# Brief, detailed purpose: Helper functions for the **user-facing Support Tickets** blueprint (My Portal).
# This is now 100% isolated from the Ticket Manager utils.
# • Handles email notifications to staff when a member submits a new ticket.
# • Clean, simple, and ready for future user-side helpers (e.g. ticket ownership checks).

from flask import session
from app.utils.emailer import send_email
from .queries import get_staff_emails, get_ticket_title


def send_new_ticket_notification_to_staff(ticket_id, title, category_name, priority):
    """Send email to all staff/admins/owners when a member submits a new support ticket."""
    staff_emails = get_staff_emails()
    if not staff_emails:
        return

    subject = f"New Support Ticket #{ticket_id}: {title}"
    body = f"""A new support ticket has been submitted by a member.

Ticket ID: #{ticket_id}
Title: {title}
Category: {category_name}
Priority: {priority.capitalize()}

Please log in to the Ticket Manager to review and respond.

View ticket: https://myvinechurch.online/tickets/{ticket_id}
"""

    for email in staff_emails:
        try:
            send_email(email, subject, body)
        except Exception as e:
            print(f"Warning: Failed to send new ticket notification to {email}: {e}")


