# MYVINECHURCH.ONLINE/app/routes/public/events/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/events/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning specifically for the Public Events module.
# - Validates public potluck signup form (name, item, quantity, note).
# - Performs server-side censored word check on all visible fields.
# - Returns clean dict on success, or None + flash message on error.
# - 100% matches the original public/forms.py potluck signup validation logic (moved here for modularity).

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_potluck_signup_form(form_data):
    """Validate and clean the public potluck signup form."""
    name = form_data.get('name', '').strip()
    item = form_data.get('item', '').strip()
    quantity = form_data.get('quantity', '').strip() or None
    note = form_data.get('note', '').strip() or None

    if not name or not item:
        flash('Name and item are required.', 'error')
        return None

    # Censored words check on all fields
    combined_text = f"{name} {item} {quantity or ''} {note or ''}"
    if contains_censored_word(combined_text):
        flash('Your submission contains a prohibited word or phrase.', 'error')
        return None

    return {
        'name': name,
        'item': item,
        'quantity': quantity,
        'note': note
    }


