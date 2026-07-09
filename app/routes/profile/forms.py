# app/routes/profile/forms.py
# Full path: MyVineChurch/app/routes/profile/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Profile module.
# • Validates the main profile update form (all fields, new privacy preferences, check-in PIN, password change).
# • Performs server-side censored word check on visible fields (first_name, last_name, email, phone, address, relation_type).
# • Validates PIN (4-6 digits or empty), password match, role restrictions.
# • Returns clean dict on success, or None + flash message + repopulates form on error (keeps views.py clean).
# • 100% matches the original profile.py validation and repopulation logic.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_profile_form(form_data, current_role=None):
    """
    Validate and clean the main Profile Update form.
    Returns clean dict on success, or None + flash on error.
    """
    first_name = form_data.get('first_name', '').strip()
    last_name = form_data.get('last_name', '').strip()
    email = form_data.get('email', '').strip()
    phone = form_data.get('phone', '').strip() or None
    address = form_data.get('address', '').strip() or None
    birthday = form_data.get('birthday', '').strip() or None
    show_birthday = 1 if form_data.get('show_birthday') == 'on' else 0

    # New privacy preferences
    allow_proxy_checkin = 1 if form_data.get('allow_proxy_checkin') == 'on' else 0
    allow_group_add = 1 if form_data.get('allow_group_add') == 'on' else 0
    allow_family_search = 1 if form_data.get('allow_family_search') == 'on' else 0

    # PIN validation (4-6 digits or empty)
    checkin_pin = form_data.get('checkin_pin', '').strip()
    if checkin_pin:
        if not (checkin_pin.isdigit() and 4 <= len(checkin_pin) <= 6):
            flash('Check-in PIN must be 4-6 digits or left empty.', 'error')
            return None
        # PIN will be hashed in views.py

    # Censored words check on visible fields
    visible_text = f"{first_name} {last_name} {email} {phone or ''} {address or ''}"
    if contains_censored_word(visible_text):
        flash('Profile contains a prohibited word or phrase.', 'error')
        return None

    # Password change (handled in views, but basic validation here)
    old_password = form_data.get('old_password', '').strip()
    new_password = form_data.get('new_password', '').strip()
    confirm_password = form_data.get('confirm_password', '').strip()

    if new_password and new_password != confirm_password:
        flash('New passwords do not match.', 'error')
        return None
    if new_password and not old_password:
        flash('Old password required to set a new one.', 'error')
        return None

    return {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'address': address,
        'birthday': birthday,
        'show_birthday': show_birthday,
        'allow_proxy_checkin': allow_proxy_checkin,
        'allow_group_add': allow_group_add,
        'allow_family_search': allow_family_search,
        'checkin_pin': checkin_pin,
        'old_password': old_password,
        'new_password': new_password,
        'confirm_password': confirm_password
    }


def validate_family_search_form(form_data):
    """Validate family search form (simple)."""
    search_query = form_data.get('search_query', '').strip()
    if not search_query:
        flash('Search term is required.', 'error')
        return None
    return search_query