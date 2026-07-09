# app/routes/events/event_email.py
# Full path: MyVineChurch/app/routes/events/event_email.py
# File name: event_email.py
# Brief, detailed purpose: Contains only the event email invitations route (/events/email POST).
# Restricted to Staff/Admin/Owner. Sends invitations to selected members or all who accept emails.
# Builds simple email body with event name and detail link.
# Logs the action and flashes success/error.
# No other routes or logic – pure extraction from the original monolithic events.py.

from flask import request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.models.db import get_db
from app.models.log import log_change
from app.utils.emailer import send_email
import pymysql

REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']

def register_email_routes(bp):
    @bp.route('/email', methods=['POST'])
    @login_required
    @role_required(REQUIRED_ROLES)
    def email_event():
        user_id = session['user_id']
        event_id = request.form.get('event_id')
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not subject or not event_id:
            flash('Subject and event are required.', 'error')
            return redirect(url_for('events.events'))

        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        cur.execute("SELECT event_name FROM events WHERE id = %s", (event_id,))
        row = cur.fetchone()
        if not row:
            flash('Event not found.', 'error')
            return redirect(url_for('events.events'))
        event_name = row['event_name']

        # Determine recipients
        if 'sendAll' in request.form:
            cur.execute("SELECT email FROM users WHERE accepts_event_emails = 1")
        else:
            member_ids = request.form.getlist('member_ids')
            if not member_ids:
                flash('No recipients selected.', 'error')
                return redirect(url_for('events.events'))
            placeholders = ','.join(['%s'] * len(member_ids))
            cur.execute(
                f"SELECT email FROM users WHERE id IN ({placeholders}) AND accepts_event_emails = 1",
                member_ids
            )

        emails = [r['email'] for r in cur.fetchall()]

        if not emails:
            flash('No valid recipients found.', 'error')
            return redirect(url_for('events.events'))

        body = f"{message}\n\nEvent: {event_name}\nView details at myvinechurch.online/events/{event_id}"

        for email_addr in emails:
            send_email(email_addr, subject, body)

        log_change(
            user_id,
            'email_event',
            target_id=event_id,
            change_details=f"Sent invitations for event: {event_name}"
        )
        flash('Invitations sent successfully!', 'success')

        return redirect(url_for('events.events'))