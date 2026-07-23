# app/routes/groups/forms.py
# Full path: MyVineChurch/app/routes/groups/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Groups module.
# - Validates create group and edit group forms.
# - Performs server-side censored word check on visible fields (name + description).
# - Handles permissions list from checkboxes.
# - Returns clean dict on success, or None + flash message + repopulates form on error (keeps views.py clean).
# - 100% matches the original groups.py validation logic.

from flask import flash
from app.utils.helpers import contains_censored_word
from app.utils.permission_matrix import keys_from_form_levels
from app.utils.permissions import is_valid_permission_key


def _permissions_from_form(form_data):
    """
    Prefer area matrix selects (area_level_*); also accept classic checkboxes.
    """
    keys = keys_from_form_levels(form_data)
    # If matrix was empty but checkboxes present, keys_from_form_levels already merged checkboxes.
    return [p for p in keys if is_valid_permission_key(p)]


def validate_create_group_form(form_data):
    """
    Validate and clean the Create Group form.
    Returns clean dict on success, or None + flash on error.
    """
    name = form_data.get('name', '').strip()
    description = form_data.get('description', '').strip()
    visibility = form_data.get('visibility', 'private')

    # Required fields
    if not name:
        flash('Group name is required.', 'error')
        return None

    # Censored words check on visible fields (name + description)
    combined_text = f"{name} {description}"
    if contains_censored_word(combined_text):
        flash('Group name or description contains a prohibited word or phrase.', 'error')
        return None

    permissions = _permissions_from_form(form_data)

    return {
        'name': name,
        'description': description,
        'visibility': visibility,
        'permissions': permissions
    }


def validate_edit_group_form(form_data):
    """
    Validate and clean the Edit Group form.
    Returns clean dict on success, or None + flash on error.
    """
    name = form_data.get('name', '').strip()
    description = form_data.get('description', '').strip()
    visibility = form_data.get('visibility', 'private')

    # Required fields
    if not name:
        flash('Group name is required.', 'error')
        return None

    # Censored words check on visible fields (name + description)
    combined_text = f"{name} {description}"
    if contains_censored_word(combined_text):
        flash('Group name or description contains a prohibited word or phrase.', 'error')
        return None

    permissions = _permissions_from_form(form_data)

    return {
        'name': name,
        'description': description,
        'visibility': visibility,
        'permissions': permissions
    }