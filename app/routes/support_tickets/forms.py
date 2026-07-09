# MYVINECHURCH.ONLINE/app/routes/support_tickets/forms.py
# Full path: MYVINECHURCH.ONLINE/app/routes/support_tickets/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation + censored word checks for the **user-facing Support Tickets** blueprint (My Portal / View Tickets).
# This is now 100% isolated for regular logged-in members only.
# - No guest submission fields (contact_name / contact_email) — members are already logged in.
# - Every validation block, flash message, and censored-word check preserved from the original.
# - Returns clean data + error lists so views.py can keep identical logic and template repopulation.

from app.utils.helpers import contains_censored_word


def validate_ticket_submission(form_data):
    """
    Validate data from the member support ticket submission form.
    Returns tuple: (is_valid: bool, errors: list of str, cleaned_data: dict)
    """
    errors = []
    cleaned = {
        'title': '',
        'description': '',
        'category_id': None,
        'priority': 'medium'
    }

    title = form_data.get('title', '').strip()
    description = form_data.get('description', '').strip()
    category_id = form_data.get('category_id')
    priority = form_data.get('priority', 'medium')

    cleaned['title'] = title
    cleaned['description'] = description
    cleaned['category_id'] = category_id
    cleaned['priority'] = priority

    if not title:
        errors.append('Title is required.')
    if not description:
        errors.append('Description is required.')
    if not category_id:
        errors.append('Category is required.')

    # Censored word check on title + description
    if contains_censored_word(f"{title} {description}"):
        errors.append('Your ticket contains a prohibited word or phrase.')

    is_valid = len(errors) == 0
    return is_valid, errors, cleaned


def validate_ticket_comment(form_data):
    """
    Validate comment/reply form for a member's own ticket.
    Returns tuple: (is_valid: bool, errors: list of str, cleaned_data: dict)
    """
    errors = []
    cleaned = {
        'comment': ''
    }

    comment = form_data.get('comment', '').strip()
    cleaned['comment'] = comment

    if not comment:
        errors.append('Comment cannot be empty.')
    elif contains_censored_word(comment):
        errors.append('Your comment contains a prohibited word.')

    is_valid = len(errors) == 0
    return is_valid, errors, cleaned


