# MYVINECHURCH.ONLINE/app/routes/tickets/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/tickets/forms.py
# File name: forms.py
# Brief, detailed purpose: All form validation + censored word checks + repopulation logic for the **Ticket Manager** blueprint ONLY (routes/tickets/).
# This file is now 100% isolated to administrative ticket management (ticket_managers group + Admins/Owner).
# • Managers use these forms for status updates, priority changes, assignment, and internal comments.html.
# • Guest/member submission logic has been removed (moved to the new support_tickets blueprint).
# • Every original validation block, flash message, and censored-word check preserved exactly where still relevant to managers.
# • Returns clean data + error lists so views.py can keep identical logic and template repopulation.

from app.utils.helpers import contains_censored_word


def validate_ticket_comment(form_data, can_manage=False):
    """
    Validate data from view_ticket comment form (Ticket Manager only).
    Returns tuple: (is_valid: bool, errors: list of str, cleaned_data: dict)
    """
    errors = []
    cleaned = {
        'comment': '',
        'notify_creator': False
    }

    comment = form_data.get('comment', '').strip()
    notify_creator = can_manage and 'notify_creator' in form_data

    cleaned['comment'] = comment
    cleaned['notify_creator'] = notify_creator

    if not comment:
        errors.append('Comment cannot be empty.')
    elif contains_censored_word(comment):
        errors.append('Comment contains a prohibited word.')

    is_valid = len(errors) == 0
    return is_valid, errors, cleaned


def validate_status_update(form_data):
    """Simple validation for status dropdown (Ticket Manager only)."""
    new_status = form_data.get('status')
    valid = ['open', 'in_progress', 'resolved', 'closed']
    if new_status not in valid:
        return False, 'Invalid status selected.'
    return True, None


def validate_priority_update(form_data):
    """Simple validation for priority dropdown (Ticket Manager only)."""
    new_priority = form_data.get('priority')
    valid = ['low', 'medium', 'high', 'urgent']
    if new_priority not in valid:
        return False, 'Invalid priority selected.'
    return True, None


def validate_assign_update(form_data):
    """No heavy validation needed for assign (staff list comes from DB)."""
    assigned_to = form_data.get('assigned_to')
    # empty string means unassign
    return True, None


