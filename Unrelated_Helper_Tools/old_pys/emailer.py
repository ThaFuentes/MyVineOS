# myvinechurchonline/app/routes/emailer.py
# Full path: myvinechurchonline/app/routes/emailer.py
# File name: emailer.py
# Brief, detailed purpose: Blueprint for manual email sending functionality.
#          Provides a web form for authorized users (Staff/Admin/Owner) to send individual emails.
#          Restricted access, uses centralized send_email utility from utils.emailer.
#          Audit logs successful sends for accountability.
#          FULL REBUILD: Added server-side censored word check on subject + body before sending.
#          If prohibited word/phrase detected, flash error and repopulate form (no send).
#          Uses contains_censored_word() from helpers (fresh DB query).
#          Clears form on success.
#          Preserved all original logic exactly.

from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word
from app.utils.emailer import send_email
from app.models.log import log_change

emailer_bp = Blueprint('emailer', __name__, url_prefix='/emailer')


# ----------------------------------------------------------------------
# Manual Email Send Form – /emailer/send
# ----------------------------------------------------------------------
@emailer_bp.route('/send', methods=['GET', 'POST'])
@login_required
@role_required(['Staff', 'Admin', 'Owner'])
def send_email_route():
    """Render manual email form or process send request."""
    to_email = ''
    subject = ''
    body = ''

    if request.method == 'POST':
        to_email = request.form.get('to_email', '').strip()
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()

        if not to_email or not subject or not body:
            flash('All fields (To, Subject, Body) are required.', 'error')
        else:
            # Censored words check on subject + body
            combined_text = f"{subject} {body}"
            if contains_censored_word(combined_text):
                flash('Email contains a prohibited word or phrase.', 'error')
            else:
                try:
                    send_email(to_email, subject, body)
                    log_change(
                        user_id=session['user_id'],
                        action='email',
                        change_details=f"Manual email sent to {to_email} – Subject: {subject}"
                    )
                    flash('Email sent successfully!', 'success')
                    # Clear form on success
                    to_email = subject = body = ''
                except Exception as e:
                    flash(f'Failed to send email: {str(e)}', 'error')

    return render_template(
        'email/send_email.html',
        to_email=to_email,
        subject=subject,
        body=body
    )