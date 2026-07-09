# app/routes/prophecies/forms.py
# Full path: MyVineChurch/app/routes/prophecies/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Prophecies module.
# - Validates add prophecy, edit prophecy, add comment, and edit comment forms.
# - Performs server-side censored word check on all visible text fields.
# - Returns clean dict on success, or None + flash message + repopulates form on error (keeps views.py clean).
# - 100% matches the original prophecies.py validation logic.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_add_prophecy_form(form_data):
    """Validate and clean the Add Prophecy form."""
    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    visibility = form_data.get('visibility', 'private')

    if not title or not description:
        flash('Title and description are required.', 'error')
        return None

    if visibility not in ('public', 'private', 'personal'):
        flash('Invalid visibility setting.', 'error')
        return None

    if contains_censored_word(title) or contains_censored_word(description):
        flash('Content contains prohibited words.', 'error')
        return None

    return {
        'title': title,
        'description': description,
        'visibility': visibility
    }


def validate_edit_prophecy_form(form_data):
    """Validate and clean the Edit Prophecy form."""
    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    visibility = form_data.get('visibility')

    if not title or not description:
        flash('Title and description are required.', 'error')
        return None

    if visibility not in ('public', 'private', 'personal'):
        flash('Invalid visibility setting.', 'error')
        return None

    if contains_censored_word(title) or contains_censored_word(description):
        flash('Content contains prohibited words.', 'error')
        return None

    return {
        'title': title,
        'description': description,
        'visibility': visibility
    }


def validate_comment_form(form_data):
    """Validate and clean the Add/Edit Comment form."""
    comment_text = form_data.get('comment', '').strip()

    if not comment_text:
        flash('Comment cannot be empty.', 'error')
        return None

    if contains_censored_word(comment_text):
        flash('Comment contains a prohibited word or phrase.', 'error')
        return None

    return comment_text