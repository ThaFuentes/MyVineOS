# app/routes/dreams/forms.py
# Full path: MyVineChurch/app/routes/dreams/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Dreams module.
# • Validates submit dream, edit dream, and comment forms.
# • Performs server-side censored word check on all visible fields.
# • Returns clean dict on success, or None + flash message on error (keeps views.py clean).
# • 100% matches the original censorship + repopulation logic from dreams.py.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_submit_dream_form(form_data):
    """
    Validate and clean the Submit Dream form.
    Returns clean dict on success, or None + flash on error.
    """
    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    notes = form_data.get('notes', '').strip()
    category = form_data.get('category', '').strip()
    date_occurred = form_data.get('date_occurred') or None
    visibility = form_data.get('visibility', 'private')

    if visibility not in ['public', 'private', 'personal']:
        visibility = 'private'

    # Censored word check on all visible fields
    combined = f"{title} {description} {notes} {category}"
    if contains_censored_word(combined):
        flash('Dream contains a prohibited word or phrase.', 'error')
        return None

    if not title or not description:
        flash('Title and description are required.', 'error')
        return None

    return {
        'title': title,
        'description': description,
        'notes': notes,
        'category': category,
        'date_occurred': date_occurred,
        'visibility': visibility
    }


def validate_edit_dream_form(form_data):
    """
    Validate and clean the Edit Dream form.
    Returns clean dict on success, or None + flash on error.
    """
    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    notes = form_data.get('notes', '').strip()
    category = form_data.get('category', '').strip()
    date_occurred = form_data.get('date_occurred') or None
    visibility = form_data.get('visibility')

    if visibility not in ['public', 'private', 'personal']:
        visibility = None  # keep original if not provided

    combined = f"{title} {description} {notes} {category}"
    if contains_censored_word(combined):
        flash('Dream contains a prohibited word or phrase.', 'error')
        return None

    if not title or not description:
        flash('Title and description are required.', 'error')
        return None

    return {
        'title': title,
        'description': description,
        'notes': notes,
        'category': category,
        'date_occurred': date_occurred,
        'visibility': visibility
    }


def validate_comment_form(form_data):
    """
    Validate comment form (add or update).
    Returns cleaned comment text or None + flash.
    """
    comment_text = form_data.get('comment', '').strip()

    if not comment_text:
        flash('Comment cannot be empty.', 'error')
        return None

    if contains_censored_word(comment_text):
        flash('Comment contains a prohibited word or phrase.', 'error')
        return None

    return comment_text