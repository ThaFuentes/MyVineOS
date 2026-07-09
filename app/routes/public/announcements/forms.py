# MYVINECHURCH.ONLINE/app/routes/public/announcements/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/announcements/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning specifically for the Public Announcements module.
# - Validates guest comment / reply form (contributor_name, comment, optional parent_id).
# - Performs server-side censored word check on all visible fields.
# - Returns clean dict on success, or None + flash message on error.
# - 100% rebuilt to match the exact style and behavior of dreams/forms.py, events/forms.py, prayers/forms.py, and prophecies/forms.py for full consistency.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_guest_comment_form(form_data):
    """Validate and clean the public guest comment / reply form used on announcements."""
    name         = form_data.get('contributor_name', '').strip()
    comment_text = form_data.get('comment', '').strip()
    parent_id    = form_data.get('parent_id') or None

    if not name or not comment_text:
        flash('Name and comment are required.', 'error')
        return None

    # Censored words check on all fields
    combined_text = f"{name} {comment_text}"
    if contains_censored_word(combined_text):
        flash('Your comment contains prohibited content.', 'error')
        return None

    return {
        'name': name,
        'comment': comment_text,
        'parent_id': parent_id
    }


