# Central email notification dispatcher — all system emails flow through here.

from typing import Optional, List
import os
import secrets
import pymysql
from flask import url_for, current_app
from app.models.db import get_db
from app.utils.emailer import send_email


def external_url(endpoint: str, **values) -> str:
    """Build an absolute URL for emails. Uses APP_PUBLIC_URL when set (recommended for production)."""
    base = (os.environ.get('APP_PUBLIC_URL') or os.environ.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if base:
        path = url_for(endpoint, _external=False, **values)
        return f"{base}{path}"
    return url_for(endpoint, _external=True, **values)


# Catalog of email use cases (shown in Settings → Notifications)
EMAIL_USAGE_CATALOG = [
    {'key': 'registration_admin_alert', 'label': 'New registration alert', 'audience': 'Admins who opt in', 'trigger': 'Someone registers'},
    {'key': 'registration_verify', 'label': 'Email verification', 'audience': 'New registrant', 'trigger': 'Registration when verification required'},
    {'key': 'registration_approved', 'label': 'Account approved', 'audience': 'Approved member', 'trigger': 'Admin approves pending account'},
    {'key': 'registration_welcome', 'label': 'Welcome email', 'audience': 'New member', 'trigger': 'Auto-approved registration or admin-created member'},
    {'key': 'password_reset', 'label': 'Password reset code', 'audience': 'Requesting user', 'trigger': 'Forgot password'},
    {'key': 'username_recovery', 'label': 'Username recovery', 'audience': 'Requesting user', 'trigger': 'Forgot username'},
    {'key': 'bill_reminder', 'label': 'Bill payment reminder', 'audience': 'Assigned users (opt-in) + optional bill email', 'trigger': 'Manual or scheduled before due date'},
    {'key': 'donation_receipt', 'label': 'Donation receipt', 'audience': 'Donor', 'trigger': 'Donation recorded (when enabled)'},
    {'key': 'donation_report', 'label': 'Donation report', 'audience': 'Staff recipient', 'trigger': 'Manual report email from donations'},
    {'key': 'event_invite', 'label': 'Event invitation', 'audience': 'Selected members', 'trigger': 'Events email tool'},
    {'key': 'announcement_blast', 'label': 'Announcement email', 'audience': 'Selected members', 'trigger': 'Announcements email tool'},
    {'key': 'support_ticket', 'label': 'Support ticket alert', 'audience': 'Staff', 'trigger': 'New support ticket'},
    {'key': 'member_roster', 'label': 'Member roster / broadcast', 'audience': 'External address, all members, or roster-to-all', 'trigger': 'Members → Member Emails (3 send modes)'},
]


def get_notification_settings() -> dict:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT registration_auto_approve, registration_require_email_verification,
               email_send_donation_receipts, email_auto_bill_reminders,
               church_name
        FROM settings WHERE id = 1
    """)
    row = cur.fetchone() or {}
    return {
        'registration_auto_approve': bool(row.get('registration_auto_approve')),
        'registration_require_email_verification': bool(row.get('registration_require_email_verification', 1)),
        'email_send_donation_receipts': bool(row.get('email_send_donation_receipts', 1)),
        'email_auto_bill_reminders': bool(row.get('email_auto_bill_reminders', 1)),
        'church_name': row.get('church_name') or 'MyVine Church',
    }


def _church_name() -> str:
    return get_notification_settings()['church_name']


def _safe_send(to_email: str, subject: str, body: str, notification_type: str) -> bool:
    if not to_email:
        return False
    try:
        send_email(to_email, subject, body)
        return True
    except Exception as e:
        print(f"Email notification failed ({notification_type}) to {to_email}: {e}")
        return False


def get_admin_registration_recipients() -> List[str]:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT email FROM users
        WHERE notify_new_registrations = 1
          AND role IN ('Owner', 'Admin', 'Staff')
          AND email IS NOT NULL AND email != ''
          AND accepts_emails = 1
    """)
    return [r['email'] for r in cur.fetchall() if r.get('email')]


def generate_verification_token() -> str:
    return secrets.token_urlsafe(32)


def send_registration_admin_alert(user: dict) -> int:
    """Notify opted-in admins of a new registration. Returns count sent."""
    subject = f"New registration: {user.get('username')} ({_church_name()})"
    body = f"""A new account was created on {_church_name()}.

Name: {user.get('first_name', '')} {user.get('last_name', '')}
Username: {user.get('username')}
Email: {user.get('email')}
Status: {user.get('role', 'pending')}

Review pending registrations in Members → Pending Registrations.
"""
    sent = 0
    for email in get_admin_registration_recipients():
        if _safe_send(email, subject, body, 'registration_admin_alert'):
            sent += 1
    return sent


def send_email_verification(user_id: int, email: str, token: str, username: str) -> bool:
    verify_url = external_url('auth.verify_email', token=token)
    subject = f"Verify your email — {_church_name()}"
    body = f"""Hello {username},

Please verify your email address for {_church_name()}.

Open this link, then click the "Verify my email" button on the page:
{verify_url}

If you did not register, you can ignore this message.
"""
    return _safe_send(email, subject, body, 'registration_verify')


def send_registration_approved(email: str, username: str) -> bool:
    login_url = external_url('auth.login')
    subject = f"Your account has been approved — {_church_name()}"
    body = f"""Hello {username},

Your account on {_church_name()} has been approved. You can now log in:

{login_url}

Welcome to the community!
"""
    return _safe_send(email, subject, body, 'registration_approved')


def send_registration_welcome(email: str, username: str, extra_note: str = '') -> bool:
    subject = f"Welcome to {_church_name()}"
    body = f"""Hello {username},

Welcome to {_church_name()}! Your account is ready.

{extra_note}

Log in anytime to connect with the community.
"""
    return _safe_send(email, subject, body, 'registration_welcome')


def send_donation_receipt(donation: dict, church_info: dict) -> bool:
    email = donation.get('donor_email') or donation.get('member_email')
    if not email:
        return False
    if not get_notification_settings()['email_send_donation_receipts']:
        return False
    church = church_info.get('church_name') or _church_name()
    subject = f"Donation receipt — {church}"
    body = f"""Thank you for your generous gift to {church}.

Donor: {donation.get('name', 'Donor')}
Amount: ${float(donation.get('amount', 0)):,.2f}
Date: {donation.get('date')}
Method: {donation.get('method', 'N/A')}
Confirmation #: {donation.get('confirmation_number') or 'N/A'}

{church_info.get('tax_status') or ''}

This message serves as acknowledgment of your donation. Please retain for your records.
"""
    return _safe_send(email, subject, body, 'donation_receipt')


def get_bill_reminder_recipients(bill_id: int, bill: Optional[dict] = None) -> List[dict]:
    """Users assigned with remind_me + bill email prefs, plus optional bill reminder_email."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    recipients = []
    seen = set()

    cur.execute("""
        SELECT u.email, u.first_name
        FROM recurring_bill_assignments a
        JOIN users u ON a.user_id = u.id
        WHERE a.bill_id = %s AND a.remind_me = 1
          AND u.accepts_emails = 1
          AND COALESCE(u.accepts_bill_emails, 1) = 1
          AND u.email IS NOT NULL AND TRIM(u.email) != ''
    """, (bill_id,))
    for row in cur.fetchall():
        email = (row.get('email') or '').strip()
        key = email.lower()
        if email and key not in seen:
            seen.add(key)
            recipients.append({'email': email, 'first_name': row.get('first_name')})

    reminder_email = (bill or {}).get('reminder_email') or ''
    if not reminder_email:
        cur.execute("SELECT reminder_email FROM recurring_bills WHERE id = %s", (bill_id,))
        row = cur.fetchone()
        reminder_email = (row or {}).get('reminder_email') or ''

    for part in reminder_email.replace(';', ',').split(','):
        email = part.strip()
        key = email.lower()
        if email and key not in seen:
            seen.add(key)
            recipients.append({'email': email, 'first_name': 'Team'})

    return recipients


def send_bill_reminders_for_bill(bill: dict) -> int:
    """Send bill reminder to all eligible recipients. Returns count sent."""
    bill_id = bill.get('id')
    if not bill_id:
        return 0
    sent = 0
    for recipient in get_bill_reminder_recipients(bill_id, bill):
        if send_bill_reminder_email(recipient, bill):
            sent += 1
    return sent


def send_bill_reminder_email(recipient: dict, bill: dict) -> bool:
    if not recipient.get('email'):
        return False
    subject = f"Reminder: {bill['bill_name']} due soon"
    body = f"""Hello {recipient.get('first_name') or 'Member'},

This is a friendly reminder that the recurring bill "{bill['bill_name']}" is due soon.

Typical amount: ${bill.get('typical_amount') or 'N/A'}
Due date: {bill.get('next_due_date') or 'Not set'}

{bill.get('payment_url') and ('Payment URL: ' + bill['payment_url']) or ''}

Please log in to view bill details.

Thank you!
"""
    return _safe_send(recipient['email'], subject, body, 'bill_reminder')