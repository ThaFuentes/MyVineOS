# MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and cleaning specifically for the Announcements section
# of the Gathering Place Manager.
# - Validates create/edit announcement forms (title, content, visibility, is_pinned, expiration).
# - Performs server-side censored word checks on all visible fields.
# - Includes moderation validation for comments.html (approve/delete).
# - Returns clean dict on success or None + flash message on error.
# - 100% consistent with the_gathering/forms.py and public/events/forms.py patterns.
# - Only this file was rebuilt — everything else on the site remains untouched.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_announcement_form(form_data):
    """Validate and clean announcement create/edit form."""
    title = form_data.get('title', '').strip()
    content = form_data.get('content', '').strip()
    visibility = form_data.get('visibility', 'public').strip()
    is_pinned = bool(form_data.get('is_pinned'))
    expiration_date = form_data.get('expiration_date', '').strip() or None

    if not title or not content:
        flash('Title and content are required for announcements.', 'error')
        return None

    # Censored word check on all visible fields
    combined = f"{title} {content}"
    if contains_censored_word(combined):
        flash('Announcement contains a prohibited word or phrase.', 'error')
        return None

    return {
        'title': title,
        'content': content,
        'visibility': visibility if visibility in ('public', 'private') else 'public',
        'is_pinned': is_pinned,
        'expiration_date': expiration_date
    }


def validate_comment_moderation(form_data):
    """Validate comment moderation actions (approve, delete, edit) for announcements."""
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
    """Clean search and filter parameters for announcements listing."""
    search = form_data.get('search', '').strip()
    filter_type = form_data.get('filter', 'all').strip()

    return {
        'search': search[:100] if search else None,
        'filter': filter_type if filter_type in ('all', 'active', 'expired', 'pinned') else 'all'
    }


# print(" MYVINECHURCH.ONLINE the_gathering/announcements/forms.py loaded successfully (validation + censorship ready)")