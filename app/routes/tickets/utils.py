# MYVINECHURCH.ONLINE/app/routes/tickets/utils.py
# Full path: MYVINECHURCH.ONLINE/app/routes/tickets/utils.py
# File name: utils.py
# Brief, detailed purpose: Helper functions for the **Ticket Manager** blueprint ONLY (routes/tickets/).
# 100% rebuilt clean version - exact same behavior as before, but now can_manage_tickets() properly checks:
#   - Owner / Admin role (via session)
#   - Explicit membership in the ticket_managers table (your dedicated ticket group admin)
#   - Old group-based 'manage_tickets' permission (for backward compatibility)
# This file is now 100% isolated to administrative ticket management (ticket_managers group + Admins/Owner).
# No user-facing functions remain here.

from flask import session
from app.utils.emailer import send_email
from .queries import (
    user_has_manage_tickets_group_permission,
    get_ticket_manager_user_ids,
    get_staff_emails,
    get_creator_email,
    get_ticket_for_notification
)


def can_manage_tickets(user_id):
    """Return True if user can manage ALL tickets (Ticket Manager dashboard).
    Checks in this order:
      1. User role is Owner or Admin (always full access)
      2. User is explicitly listed in the ticket_managers table
      3. User belongs to any group with 'manage_tickets' permission
    """
    if not user_id:
        return False

    # 1. Owner or Admin always have full access
    user_role = session.get('user_role')
    if user_role in ['Owner', 'Admin']:
        return True

    # 2. Check dedicated ticket_managers table (this is why you couldn't see tickets)
    manager_ids = get_ticket_manager_user_ids()
    if user_id in manager_ids:
        return True

    # 3. Fallback to old group permission system
    return user_has_manage_tickets_group_permission(user_id)


def send_ticket_notification(ticket, subject, body, notify_staff=False, notify_creator=False, always_creator=False):
    """Orchestrate emails to staff and/or creator. Exact original behavior preserved (Ticket Manager only)."""
    staff_emails = get_staff_emails() if notify_staff else []
    creator_email = get_creator_email(ticket) if (notify_creator or always_creator) else None

    emails = set()
    if staff_emails:
        emails.update(staff_emails)
    if creator_email:
        emails.add(creator_email)

    if not emails:
        return

    full_body = body + f"\n\nView ticket: https://myvinechurch.online/tickets/{ticket['id']}"

    for email in emails:
        try:
            send_email(email, subject, full_body)
        except Exception as e:
            print(f"Warning: Failed to send ticket notification to {email}: {e}")


