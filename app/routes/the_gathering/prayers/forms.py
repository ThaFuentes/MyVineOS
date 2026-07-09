# MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prayers/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and cleaning specifically for the Prayers section
# of the Gathering Place Manager.
# • Validates create/edit prayer forms (title, prayer_text, visibility).
# • Performs server-side censored word checks on all visible fields.
# • Includes moderation validation for comments.html (approve/delete).
# • Returns clean dict on success or None + flash message on error.
# • 100% consistent with the_gathering/announcements/forms.py and dreams/forms.py patterns.
# • Only this file was fixed to match the views expectations.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_prayer_form(form_data):
    """Validate and clean prayer create/edit form."""
    title = form_data.get('title', '').strip()
    prayer_text = form_data.get('prayer_text', '').strip()
    visibility = form_data.get('visibility', 'public').strip()

    if not title or not prayer_text:
        flash('Title and prayer text are required for prayers.', 'error')
        return None

    # Censored word check on all visible fields
    combined = f"{title} {prayer_text}"
    if contains_censored_word(combined):
        flash('Prayer contains a prohibited word or phrase.', 'error')
        return None

    return {
        'title': title,
        'prayer_text': prayer_text,
        'visibility': visibility if visibility in ('public', 'private') else 'public',
    }


def validate_comment_moderation(form_data):
    """Validate comment moderation actions (approve, delete, edit) for prayers."""
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
    """Clean search and filter parameters for prayers listing."""
    search = form_data.get('search', '').strip()
    filter_type = form_data.get('filter', 'all').strip()

    return {
        'search': search[:100] if search else None,
        'filter': filter_type if filter_type in ('all', 'public', 'private', 'pending') else 'all'
    }


print("✅ MYVINECHURCH.ONLINE the_gathering/prayers/forms.py loaded successfully (validation + censorship ready)")


