# app/routes/emailer/forms.py
# Full path: MyVineChurch/app/routes/emailer/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Emailer module.
# • Validates the manual email send form (required fields: to_email, subject, body).
# • Performs server-side censored word check on subject + body.
# • Returns clean dict on success, or None + flash message + repopulates form on error (keeps views.py clean).
# • 100% matches the original emailer.py validation and repopulation logic.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_manual_email_form(form_data):
    """
    Validate and clean the manual email send form.
    Returns clean dict on success, or None + flash + repopulates form on error.
    """
    to_email = form_data.get('to_email', '').strip()
    subject = form_data.get('subject', '').strip()
    body = form_data.get('body', '').strip()

    if not to_email or not subject or not body:
        flash('All fields (To, Subject, Body) are required.', 'error')
        return None

    # Censored word check on subject + body
    combined_text = f"{subject} {body}"
    if contains_censored_word(combined_text):
        flash('Email contains a prohibited word or phrase.', 'error')
        return None

    return {
        'to_email': to_email,
        'subject': subject,
        'body': body
    }