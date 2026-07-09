# app/routes/announcements/forms.py
# Full path: MyVineChurch/app/routes/announcements/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Announcements module.
# - Takes raw request.form data, strips whitespace, sets defaults, checks required fields.
# - Calls censorship check (from utils – we’ll connect it next).
# - Returns a clean dict of values OR flashes error + returns None (keeps views.py super clean).
# - 100% matches your original create/edit logic but now reusable and easy to grow (add more fields later).

from flask import flash
from app.utils.helpers import contains_censored_word   # your existing helper


def validate_and_clean_announcement_form(form_data):
    """
    Validate and clean form for create OR edit announcement.
    Returns cleaned dict on success, or None + flash message on error.
    """
    title = form_data.get('title', '').strip()
    content = form_data.get('content', '').strip()
    visibility = form_data.get('visibility', 'private')
    is_active = 1 if 'is_active' in form_data else 0
    comments_enabled = 1 if 'comments_enabled' in form_data else 0

    # Required fields
    if not title:
        flash('Title is required.', 'error')
        return None
    if not content:
        flash('Content is required.', 'error')
        return None

    # Censorship (will move to utils.py next)
    if contains_censored_word(title + ' ' + content):
        flash('Announcement contains a prohibited word or phrase.', 'error')
        return None

    # Return clean data
    return {
        'title': title,
        'content': content,
        'visibility': visibility,
        'is_active': is_active,
        'comments_enabled': comments_enabled
    }


def validate_comment_form(form_data):
    """
    Simple validation for adding a comment.
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


def validate_email_form(form_data):
    """
    Validate email announcement form.
    Returns (subject, message) or None + flash.
    """
    subject = form_data.get('subject', '').strip()
    message = form_data.get('message', '').strip()

    if not subject:
        flash('Subject is required.', 'error')
        return None

    return subject, message