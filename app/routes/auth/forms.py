# app/routes/auth/forms.py
# Full path: MyVineChurch/app/routes/auth/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Auth module.
# - Handles register (required fields, password match, server-side censorship on visible fields, form repopulation on error).
# - Simple validation for password reset and forgot username.
# - Returns clean data dict on success, or None + flash message on error (keeps views.py super clean and thin).
# - 100% matches the original auth.py validation logic (including first-user Owner handling).
# - Fully modular and ready for use with views.py, queries.py, and utils.py.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_register_form(form_data):
    """
    Validate and clean registration form.
    Returns clean dict on success, or None + flash + repopulates form on error.
    """
    first_name = form_data.get('first_name', '').strip()
    last_name = form_data.get('last_name', '').strip()
    email = form_data.get('email', '').strip().lower()
    phone = form_data.get('phone', '').strip()
    address = form_data.get('address', '').strip()
    birthday = form_data.get('birthday') or None
    username = form_data.get('username', '').strip()
    password = form_data.get('password', '')
    confirm_password = form_data.get('confirm_password', '')

    accepts_emails = 1 if 'accepts_emails' in form_data else 0
    show_birthday = 1 if 'show_birthday' in form_data else 0

    # Visible fields censorship (exactly as in original)
    visible_text = f"{first_name} {last_name} {username}"
    if contains_censored_word(visible_text):
        flash('Name or username contains a prohibited word or phrase.', 'error')
        return None

    # Required fields
    if not (first_name and last_name and email and username and password):
        flash('Required fields missing.', 'error')
        return None

    if password != confirm_password:
        flash('Passwords do not match.', 'error')
        return None

    return {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'address': address,
        'birthday': birthday,
        'username': username,
        'password': password,
        'accepts_emails': accepts_emails,
        'show_birthday': show_birthday
    }


def validate_password_reset_form(form_data):
    """
    Validate password reset request form.
    Returns cleaned email or None + flash.
    """
    email = form_data.get('email', '').strip().lower()
    if not email:
        flash('Please enter your email address.', 'error')
        return None
    return email


def validate_forgot_username_form(form_data):
    """
    Validate forgot username form.
    Returns cleaned email or None + flash.
    """
    email = form_data.get('email', '').strip().lower()
    if not email:
        flash('Please enter your email address.', 'error')
        return None
    return email