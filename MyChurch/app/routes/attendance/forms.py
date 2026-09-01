# app/routes/attendance/forms.py
# Full path: MyVineChurch/app/routes/attendance/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Attendance module.
# - Takes raw request.form data, strips whitespace, sets defaults, checks required fields.
# - Returns clean data OR flashes error + returns None (keeps views.py super clean).
# - Handles kiosk check-in (member_id + optional PIN) and self-checkin (client time).
# - 100% matches the original validation logic from the flat attendance.py file.

from flask import flash


def validate_kiosk_checkin_form(form_data):
    """
    Validate kiosk check-in form.
    Returns (member_id, pin) tuple on success, or None + flash on error.
    """
    member_id = form_data.get('member_id')
    pin = form_data.get('pin', '').strip()

    if not member_id:
        flash('No member selected.', 'error')
        return None

    return member_id, pin


def validate_self_checkin_form(form_data):
    """
    Validate self-checkin form (client timestamp).
    Returns client_iso string (or None) - always succeeds unless malformed.
    """
    client_iso = form_data.get('client_checkin')
    return client_iso