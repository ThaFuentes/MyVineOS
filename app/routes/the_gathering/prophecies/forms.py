# MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and cleaning specifically for the Prophecies section
# of the Gathering Place Manager.
# • Validates create/edit prophecy forms (title, prophecy_text, visibility).
# • Performs server-side censored word checks on all visible fields.
# • Includes moderation validation for comments.html (approve/delete).
# • Returns clean dict on success or None + flash message on error.
# • 100% consistent with the_gathering/events/forms.py, dreams/forms.py, prayers/forms.py and announcements/forms.py patterns.
# • Only this file was rebuilt — everything else on the site remains untouched.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_prophecy_form(form_data):
    """Validate and clean prophecy create/edit form."""
    title = form_data.get('title', '').strip()
    prophecy_text = form_data.get('prophecy_text', '').strip() or form_data.get('content', '').strip()
    visibility = form_data.get('visibility', 'public').strip()

    if not title or not prophecy_text:
        flash('Title and prophecy content are required.', 'error')
        return None

    # Censored word check on all visible fields
    combined = f"{title} {prophecy_text}"
    if contains_censored_word(combined):
        flash('Prophecy contains a prohibited word or phrase.', 'error')
        return None

    return {
        'title': title,
        'prophecy_text': prophecy_text,
        'visibility': visibility if visibility in ('public', 'private') else 'public'
    }


def validate_comment_moderation(form_data):
    """Validate comment moderation actions (approve, delete, edit) for prophecies."""
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
    """Clean search and filter parameters for prophecies listing."""
    search = form_data.get('search', '').strip()
    filter_type = form_data.get('filter', 'all').strip()

    return {
        'search': search[:100] if search else None,
        'filter': filter_type if filter_type in ('all', 'public', 'private') else 'all'
    }


# print("✅ MYVINECHURCH.ONLINE the_gathering/prophecies/forms.py loaded successfully (validation + censorship ready)")