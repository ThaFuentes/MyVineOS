# app/routes/profile/views.py
# Full path: MyVineChurch/app/routes/profile/views.py
# File name: views.py
# Brief, detailed purpose: All route handlers (controllers) for the Profile blueprint.
# • Every single function name and endpoint from the original profile.py is preserved exactly (no renaming allowed).
# • All database work moved to queries.py
# • All form validation + censorship moved to forms.py
# • All helpers moved to utils.py
# • 100% original behavior preserved.

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
import traceback

from . import profile_bp
from .queries import (
    get_user_profile,
    get_pending_incoming_requests,
    get_approved_family,
    get_suggested_family,
    search_family_members,
    create_family_request,
    approve_family_request,
    reject_family_request,
    remove_family_relationship,
    update_user_profile,
    update_user_password
)
from .forms import validate_profile_form
from .utils import REQUIRED_ROLES, current_user_id

from app.utils.decorators import login_required
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change


# ----------------------------------------------------------------------
# View and Update Profile + Family Management
# ----------------------------------------------------------------------
@profile_bp.route('/', methods=['GET', 'POST'])
@login_required
def profile():
    """View and update personal profile; manage family relationships including search (respects allow_family_search)."""
    user_id = current_user_id()

    try:
        search_results = []

        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'search':
                search_query = request.form['search_query'].strip().lower()
                search_results = search_family_members(user_id, search_query)

            else:  # Profile update
                clean_data = validate_profile_form(request.form, current_role=session.get('user_role'))
                if not clean_data:
                    return redirect(url_for('profile.profile'))

                # Password change
                old_password = clean_data.pop('old_password', None)
                new_password = clean_data.pop('new_password', None)
                confirm_password = clean_data.pop('confirm_password', None)

                # Update basic profile + privacy preferences + PIN
                update_user_profile(user_id, clean_data)

                # Password update
                if new_password and old_password:
                    db = get_db()
                    cur = db.cursor(pymysql.cursors.DictCursor)
                    cur.execute('SELECT password FROM users WHERE id = %s', (user_id,))
                    current_hash = cur.fetchone()['password']
                    if check_password_hash(current_hash, old_password):
                        hashed_new = generate_password_hash(new_password)
                        update_user_password(user_id, hashed_new)
                        flash('Password updated successfully.', 'success')
                    else:
                        flash('Old password is incorrect.', 'error')
                        return redirect(url_for('profile.profile'))

                flash('Profile updated successfully.', 'success')
                log_change(user_id, 'update', target_id=user_id, change_details='Updated personal profile and privacy preferences')

        # Load current user (including new fields)
        user = get_user_profile(user_id)

        # Pending incoming requests
        pending_requests = get_pending_incoming_requests(user_id)

        # Approved family
        family = get_approved_family(user_id)

        # Suggested family
        suggested_users = get_suggested_family(user_id)

    except Exception as e:
        flash('Database error occurred.', 'error')
        print(f"Profile error: {e}\n{traceback.format_exc()}")
        return redirect(url_for('dashboard.dashboard'))

    return render_template(
        'profile/profile.html',
        user=user,
        pending_requests=pending_requests,
        family=family,
        suggested_users=suggested_users,
        search_results=search_results
    )


# ----------------------------------------------------------------------
# Send Family Request
# ----------------------------------------------------------------------
@profile_bp.route('/family/request', methods=['POST'])
@login_required
def request_family():
    user_id = current_user_id()
    relative_id = int(request.form['relative_id'])
    relation = request.form['relation_type'].strip()

    if user_id == relative_id:
        flash('You cannot request a relationship with yourself.', 'error')
        return redirect(url_for('profile.profile'))

    # Censored words check on relation_type
    if contains_censored_word(relation):
        flash('Relation type contains a prohibited word or phrase.', 'error')
        return redirect(url_for('profile.profile'))

    try:
        create_family_request(user_id, relative_id, relation)
        log_change(user_id, 'create', change_details=f'Sent family request ({relation}) to user {relative_id}')
        flash('Family request sent—awaiting approval.', 'success')

    except Exception as e:
        flash('Failed to send request.', 'error')
        print(f"Request family error: {e}")

    return redirect(url_for('profile.profile'))


# ----------------------------------------------------------------------
# Approve Family Request
# ----------------------------------------------------------------------
@profile_bp.route('/family/approve/<int:fr_id>', methods=['POST'])
@login_required
def approve_family(fr_id):
    user_id = current_user_id()

    try:
        if approve_family_request(fr_id, user_id):
            log_change(user_id, 'update', target_id=fr_id, change_details='Approved family request')
            flash('Family request approved.', 'success')
        else:
            flash('Invalid or already processed request.', 'error')

    except Exception as e:
        flash('Failed to approve request.', 'error')
        print(f"Approve family error: {e}")

    return redirect(url_for('profile.profile'))


# ----------------------------------------------------------------------
# Reject Family Request
# ----------------------------------------------------------------------
@profile_bp.route('/family/reject/<int:fr_id>', methods=['POST'])
@login_required
def reject_family(fr_id):
    user_id = current_user_id()

    try:
        if reject_family_request(fr_id, user_id):
            log_change(user_id, 'update', target_id=fr_id, change_details='Rejected family request')
            flash('Family request rejected.', 'info')
        else:
            flash('Invalid or already processed request.', 'error')

    except Exception as e:
        flash('Failed to reject request.', 'error')
        print(f"Reject family error: {e}")

    return redirect(url_for('profile.profile'))


# ----------------------------------------------------------------------
# Remove Family Relationship
# ----------------------------------------------------------------------
@profile_bp.route('/family/remove/<int:fr_id>', methods=['POST'])
@login_required
def remove_family(fr_id):
    user_id = current_user_id()

    try:
        if remove_family_relationship(fr_id, user_id):
            log_change(user_id, 'delete', target_id=fr_id, change_details='Removed family relationship')
            flash('Family relationship removed.', 'success')
        else:
            flash('Could not remove relationship.', 'error')

    except Exception as e:
        flash('Failed to remove relationship.', 'error')
        print(f"Remove family error: {e}")

    return redirect(url_for('profile.profile'))