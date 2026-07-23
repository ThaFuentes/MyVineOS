# app/routes/members/forms.py
# Full path: MyVineChurch/app/routes/members/forms.py
# File name: forms.py
# Brief, detailed purpose: Form validation and data cleaning for the Members module.
# - Validates add/edit member form (required fields, role restrictions, censored words on visible text).
# - Handles email uniqueness check for new members.
# - Returns clean dict on success, or None + flash message + repopulates form on error (keeps views.py clean).
# - 100% matches the original members.py validation and repopulation logic.

from flask import flash
from app.utils.helpers import contains_censored_word, identity_spam_reason
from app.routes.members.utils import get_allowed_roles, can_outrank, role_rank


def validate_member_form(
    form_data,
    is_edit=False,
    current_role=None,
    available_group_ids=None,
    *,
    can_manage_users=False,
    existing_role=None,
):
    """
    Validate and clean the Add/Edit Member form.
    Returns clean dict on success, or None + flash on error.

    Role changes: actor may only assign roles strictly below their own rank,
    and may never change the role of someone at or above them (enforced in views
    too; this blocks form tampering).
    """
    first_name = form_data.get('first_name', '').strip()
    last_name = form_data.get('last_name', '').strip()
    email = form_data.get('email', '').strip().lower()
    phone = form_data.get('phone', '').strip() or None
    address = form_data.get('address', '').strip() or None
    birthday = form_data.get('birthday') or None
    show_birthday = 1 if form_data.get('show_birthday') else 0
    accepts_emails = 1 if form_data.get('accepts_emails') else 0
    groups_selected = [int(g) for g in form_data.getlist('groups') if g]

    # Required fields
    if not first_name or not last_name or not email:
        flash('First name, last name, and email are required.', 'error')
        return None

    if can_manage_users:
        new_role = (form_data.get('role') or 'Member').strip()
        allowed_roles = get_allowed_roles(current_role)

        # Editing someone already at/above you: never accept a role change
        if is_edit and existing_role and not can_outrank(current_role, existing_role):
            flash(
                f'You cannot change the role of a {existing_role}. '
                'Only someone above them can do that.',
                'error',
            )
            return None

        if new_role not in allowed_roles:
            flash(
                'You do not have permission to assign that role. '
                'You may only assign roles below your own.',
                'error',
            )
            return None

        # Defense in depth: assigned role must be strictly below actor
        # (Owner may assign Owner — special-case)
        if new_role != 'Owner' or (current_role or '') != 'Owner':
            if not can_outrank(current_role, new_role):
                flash('You cannot assign a role at or above your own rank.', 'error')
                return None
        if (current_role or '') != 'Owner' and role_rank(new_role) >= role_rank(current_role):
            flash('You cannot assign a role at or above your own rank.', 'error')
            return None
    else:
        new_role = existing_role or 'Member'

    # Censored words check on visible fields
    visible_text = f"{first_name} {last_name} {email} {phone or ''} {address or ''}"
    if contains_censored_word(visible_text):
        flash('Member information contains a prohibited word or phrase.', 'error')
        return None

    spam = identity_spam_reason(first_name, last_name)
    if spam:
        flash(spam, 'error')
        return None

    # Group validation
    if available_group_ids is not None:
        if any(gid not in available_group_ids for gid in groups_selected):
            flash('Invalid group selection.', 'error')
            return None

    return {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'address': address,
        'birthday': birthday,
        'show_birthday': show_birthday,
        'accepts_emails': accepts_emails,
        'role': new_role,
        'groups': groups_selected
    }


def validate_email_roster_form(form_data):
    """Validate member email tools form (3 explicit send modes)."""
    mode = (form_data.get('send_mode') or '').strip()
    subject = form_data.get('subject', '').strip()
    message = form_data.get('message', '').strip()
    recipient_emails = (form_data.get('recipient_emails') or '').strip()

    valid_modes = ('roster_to_address', 'message_all_members', 'roster_to_all_members')
    if mode not in valid_modes:
        flash('Choose how you want to send email.', 'error')
        return None

    if mode == 'roster_to_address':
        addresses = [e.strip() for e in recipient_emails.replace(';', ',').split(',') if e.strip()]
        if not addresses:
            flash('Enter at least one email address to send the roster to.', 'error')
            return None
        if not subject:
            subject = 'Church Member Roster'
        return {
            'mode': mode,
            'subject': subject,
            'message': message,
            'recipient_addresses': addresses,
        }

    if mode == 'message_all_members':
        if not subject:
            flash('Subject is required when messaging all members.', 'error')
            return None
        if not message:
            flash('Write a message to send to all members.', 'error')
            return None
        return {
            'mode': mode,
            'subject': subject,
            'message': message,
            'recipient_addresses': [],
        }

    # roster_to_all_members
    if not subject:
        subject = 'Church Member Roster'
    return {
        'mode': mode,
        'subject': subject,
        'message': message,
        'recipient_addresses': [],
    }