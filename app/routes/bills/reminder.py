# app/routes/bills/reminder.py
# Full path: MyVineChurch/app/routes/bills/reminder.py
# File name: reminder.py
# Brief, detailed purpose: Send manual reminder route (/bills/send_reminder/<int:bill_id>).
# Restricted to Staff/Admin/Owner only.
# Sends personalized reminder emails to assigned users who have remind_me = 1 and accept emails.
# Updates last_reminder_sent timestamp.
# Full audit logging.

from flask import redirect, url_for, flash, session
from app.utils.decorators import login_required, permission_required
from app.models.db import get_db
from app.models.log import log_change
from app.utils.email_notifications import send_bill_reminders_for_bill
from app.utils.time_utils import utc_now
import pymysql

def register_reminder_routes(bp):
    @bp.route('/send_reminder/<int:bill_id>', methods=['POST'])
    @login_required
    @permission_required('manage_bills')
    def send_reminder(bill_id):
        try:
            db = get_db()
            cur = db.cursor(pymysql.cursors.DictCursor)

            # Fetch bill info
            cur.execute("SELECT * FROM recurring_bills WHERE id = %s", (bill_id,))
            bill_row = cur.fetchone()
            if not bill_row:
                flash('Bill not found.', 'error')
                return redirect(url_for('bills.bills'))

            bill = dict(bill_row)

            sent_count = send_bill_reminders_for_bill(bill)

            if sent_count == 0:
                flash('No eligible recipients for reminder. Assign users with reminders on, set a bill reminder email, or check email preferences.', 'info')
                return redirect(url_for('bills.view_bill', bill_id=bill_id))

            # Update last reminder timestamp
            reminder_time_utc = utc_now()
            cur.execute("UPDATE recurring_bills SET last_reminder_sent = %s WHERE id = %s",
                        (reminder_time_utc, bill_id))
            db.commit()

            log_change(session['user_id'], 'send_reminder', bill_id,
                       change_details=f"Sent manual reminder emails to {sent_count} recipients")

            flash(f'Reminder emails sent to {sent_count} recipient(s).', 'success')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))

        except Exception as exc:
            print(f"Send reminder error (ID {bill_id}): {exc}")
            flash('Failed to send reminder.', 'error')
            return redirect(url_for('bills.view_bill', bill_id=bill_id))