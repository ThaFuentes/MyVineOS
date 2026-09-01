# MYVINECHURCH.ONLINE/app/routes/the_gathering/events/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/events/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and cleaning specifically for the Events section
# of the Gathering Place Manager.
# - Validates create/edit event forms, potluck signups, and comment moderation.
# - Performs server-side censored word checks.
# - 100% consistent with the_gathering style.
# - Only this file was rebuilt.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_event_form(form_data):
    """Validate and clean event create/edit form."""
    event_name = form_data.get('event_name', '').strip()
    event_date = form_data.get('event_date', '').strip()
    event_time = form_data.get('event_time', '').strip() or None
    location = form_data.get('location', '').strip()
    description = form_data.get('description', '').strip()
    visibility = form_data.get('visibility', 'public').strip()

    if not event_name or not event_date:
        flash('Event name and date are required.', 'error')
        return None

    combined = f"{event_name} {description or ''} {location or ''}"
    if contains_censored_word(combined):
        flash('Event contains a prohibited word or phrase.', 'error')
        return None

    return {
        'event_name': event_name,
        'event_date': event_date,
        'event_time': event_time,
        'location': location,
        'description': description,
        'visibility': visibility if visibility in ('public', 'private') else 'public',
        'potluck_enabled': 1 if form_data.get('potluck_enabled') else 0,
    }


def validate_potluck_edit_form(form_data):
    """Validate potluck signup add/edit (manager). Matches potluck_signups schema."""
    name = form_data.get('name', '').strip()
    item = form_data.get('item', '').strip()
    quantity = form_data.get('quantity', '').strip() or None
    note = form_data.get('note', '').strip() or None

    if not name:
        flash('Name is required for potluck signup.', 'error')
        return None
    if not item:
        flash('Item is required for potluck signup.', 'error')
        return None

    return {
        'name': name,
        'item': item,
        'quantity': quantity,
        'note': note,
    }


def validate_comment_moderation(form_data):
    """Validate comment moderation actions for events."""
    action = form_data.get('action', '').strip()
    comment_id = form_data.get('comment_id', '').strip()

    if not action or not comment_id:
        flash('Invalid moderation request.', 'error')
        return None

    if action not in ('approve', 'delete', 'edit'):
        flash('Unknown moderation action.', 'error')
        return None

    return {
        'action': action,
        'comment_id': int(comment_id) if comment_id.isdigit() else None
    }


def validate_search_filter(form_data):
    """Clean search and filter parameters for events listing."""
    search = form_data.get('search', '').strip()
    filter_type = form_data.get('filter', 'all').strip()

    return {
        'search': search[:100] if search else None,
        'filter': filter_type if filter_type in ('all', 'public', 'private') else 'all'
    }


# print(" MYVINECHURCH.ONLINE the_gathering/events/forms.py loaded successfully (validation + censorship ready)")