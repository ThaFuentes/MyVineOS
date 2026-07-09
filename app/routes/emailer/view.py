# app/routes/emailer/views.py
# Full path: MyVineChurch/app/routes/emailer/views.py
# File name: views.py
# Brief, detailed purpose: Clean, thin route handlers for the Emailer blueprint.
# - All form validation + censorship moved to forms.py
# - All logging moved to queries.py
# - All helpers moved to utils.py
# - 100% original behavior preserved: manual email form, censorship on subject/body, audit logging, Staff/Admin/Owner restriction.
# - Ready for future expansion (bulk emails, templates, scheduling, etc.).

from flask import render_template, request, redirect, url_for, flash, session

from . import emailer_bp
from .forms import validate_manual_email_form
from .queries import log_email_send
from .utils import REQUIRED_ROLES

from app.utils.decorators import login_required, role_required
from app.utils.emailer import send_email


# ----------------------------------------------------------------------
# Manual Email Send Form – /emailer/send
# ----------------------------------------------------------------------
@emailer_bp.route('/send', methods=['GET', 'POST'])
@login_required
@role_required(REQUIRED_ROLES)
def send_email_route():
    """Render manual email form or process send request."""
    to_email = ''
    subject = ''
    body = ''

    if request.method == 'POST':
        clean_data = validate_manual_email_form(request.form)
        if not clean_data:
            return render_template(
                'email/send_email.html',
                to_email=request.form.get('to_email', ''),
                subject=request.form.get('subject', ''),
                body=request.form.get('body', '')
            )

        to_email = clean_data['to_email']
        subject = clean_data['subject']
        body = clean_data['body']

        try:
            send_email(to_email, subject, body)
            log_email_send(session['user_id'], to_email, subject, success=True)
            flash('Email sent successfully!', 'success')
            # Clear form on success
            to_email = subject = body = ''
        except Exception as e:
            log_email_send(session['user_id'], to_email, subject, success=False)
            flash(f'Failed to send email: {str(e)}', 'error')

    return render_template(
        'email/send_email.html',
        to_email=to_email,
        subject=subject,
        body=body
    )