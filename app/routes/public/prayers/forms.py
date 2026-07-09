# MYVINECHURCH.ONLINE/app/routes/public/prayers/forms.py
# Form validation for public Prayers: guest responses and new prayer requests.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_guest_comment_form(form_data):
    """Validate and clean the public guest response / reply form used on prayers."""
    name         = form_data.get('name', '').strip()
    comment_text = form_data.get('comment', '').strip()
    parent_id    = form_data.get('parent_id') or None

    if not name or not comment_text:
        flash('Name and comment are required.', 'error')
        return None

    combined_text = f"{name} {comment_text}"
    if contains_censored_word(combined_text):
        flash('Your comment contains prohibited content.', 'error')
        return None

    return {
        'name': name,
        'comment': comment_text,
        'parent_id': parent_id
    }


def validate_guest_prayer_request_form(form_data):
    """Validate a visitor prayer request before moderation queue."""
    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    contributor_name = form_data.get('contributor_name', '').strip() or 'Anonymous'

    if not title or not description:
        flash('Title and prayer details are required.', 'error')
        return None

    combined_text = f"{title} {description} {contributor_name}"
    if contains_censored_word(combined_text):
        flash('Your request contains prohibited content and cannot be submitted.', 'error')
        return None

    return {
        'title': title,
        'description': description,
        'contributor_name': contributor_name,
    }