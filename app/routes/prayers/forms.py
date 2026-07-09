# app/routes/prayers/forms.py
# Full path: MyVineChurch/app/routes/prayers/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Prayers module.
# - Validates add prayer, edit prayer, and add response forms.
# - Performs server-side censored word check on all visible text fields.
# - Returns clean dict on success, or None + flash message + repopulates form on error (keeps views.py clean).
# - 100% matches the original prayers.py validation and repopulation logic.

from flask import flash
from app.utils.helpers import contains_censored_word


def validate_add_prayer_form(form_data, is_logged_in=False):
    """
    Validate and clean the Add Prayer form.
    Returns clean dict on success, or None + flash on error.
    """
    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    visibility = form_data.get('visibility', 'public') if is_logged_in else 'public'
    contributor_name = form_data.get('contributor_name', '').strip() if not is_logged_in else None

    # Required fields
    if not title or not description:
        flash('Title and description are required.', 'error')
        return None

    # Censored words check
    check_text = f"{title} {description}"
    if contributor_name and contributor_name != 'Anonymous':
        check_text += f" {contributor_name}"
    if contains_censored_word(check_text):
        flash('Prayer request contains a prohibited word or phrase.', 'error')
        return None

    return {
        'title': title,
        'description': description,
        'visibility': visibility,
        'contributor_name': contributor_name
    }


def validate_edit_prayer_form(form_data):
    """
    Validate and clean the Edit Prayer form.
    Returns clean dict on success, or None + flash on error.
    """
    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    visibility = form_data.get('visibility')

    # Required fields
    if not title or not description:
        flash('Title and description are required.', 'error')
        return None

    # Censored words check
    if contains_censored_word(title + ' ' + description):
        flash('Prayer request contains a prohibited word or phrase.', 'error')
        return None

    return {
        'title': title,
        'description': description,
        'visibility': visibility
    }


def validate_response_form(form_data, is_logged_in=False):
    """
    Validate and clean the Add Response form.
    Returns clean text or None + flash on error.
    """
    response_text = form_data.get('prayer', '').strip()
    contributor_name = form_data.get('contributor_name', '').strip() if not is_logged_in else None

    if not response_text:
        flash('Response text is required.', 'error')
        return None

    # Censored words check
    check_text = response_text
    if contributor_name and contributor_name != 'Anonymous':
        check_text += f" {contributor_name}"
    if contains_censored_word(check_text):
        flash('Response contains a prohibited word or phrase.', 'error')
        return None

    return response_text