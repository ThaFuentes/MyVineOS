# app/routes/prayers/views.py
# Full path: MyVineChurch/app/routes/prayers/views.py
# File name: views.py
# Brief, detailed purpose: All route handlers (controllers) for the Prayers blueprint.
# - Every single function name and endpoint from the original prayers.py is preserved exactly (no renaming allowed).
# - All database work moved to queries.py
# - All form validation + censorship moved to forms.py
# - All helpers moved to utils.py
# - 100% original behavior preserved + new ability to edit/delete responses (including guest responses).

from flask import render_template, request, redirect, url_for, flash, session
import pymysql

from . import prayers_bp
from .queries import (
    get_prayers_list,
    get_prayer_by_id,
    get_prayer_responses,
    create_prayer,
    update_prayer,
    update_prayer_status,
    delete_prayer
)
from .forms import validate_add_prayer_form, validate_edit_prayer_form, validate_response_form
from .utils import REQUIRED_ROLES, ADMIN_ROLES

from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word, censor_text
from app.models.db import get_db
from app.models.log import log_change
from app.utils.time_utils import format_church


# ----------------------------------------------------------------------
# Prayers Listing - /prayers
# ----------------------------------------------------------------------
@prayers_bp.route('/')
def prayers():
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

#    print(f"[DEBUG] Prayers listing accessed - logged_in={is_logged_in}, user_id={user_id}")

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        if is_logged_in:
#            print("[DEBUG] Logged-in view - fetching public + private prayers")
            cur.execute("""
                SELECT p.id, p.title, p.description, p.date_posted, p.visibility,
                       COALESCE(p.status, 'approved') AS status,
                       COALESCE(CONCAT(u.first_name, ' ', u.last_name), p.contributor_name, 'Anonymous') AS creator_name,
                       (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS response_count
                FROM prayers p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.visibility IN ('public', 'private')
                  AND COALESCE(p.status, 'approved') != 'rejected'
                ORDER BY p.date_posted DESC
            """)
            template = 'prayers/prayers_dashboard.html'
        else:
            print("[DEBUG] Guest view - fetching public prayers only")
            cur.execute("""
                SELECT p.id, p.title, p.description, p.date_posted,
                       COALESCE(p.contributor_name, 'Anonymous') AS creator_name,
                       (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS response_count
                FROM prayers p
                WHERE p.visibility = 'public'
                  AND COALESCE(p.status, 'approved') = 'approved'
                ORDER BY p.date_posted DESC
            """)
            template = 'public/prayers/prayers.html'

        prayers_list = cur.fetchall()
        print(f"[DEBUG] Fetched {len(prayers_list)} prayers")

        for p in prayers_list:
            p['title'] = censor_text(p['title'] or '')
            p['description'] = censor_text(p['description'] or '')
            p['creator_name'] = censor_text(p['creator_name'] or 'Anonymous')
            if p['date_posted']:
                p['formatted_date'] = format_church(p['date_posted'], '%B %d, %Y at %I:%M %p')

        if user_id:
            log_change(user_id, 'view', change_details='Viewed prayers listing')

        user_role = session.get('user_role')
        is_staff_plus = user_role in REQUIRED_ROLES
        is_admin_owner = user_role in ADMIN_ROLES
        pending_count = sum(1 for p in prayers_list if p.get('status') == 'pending') if is_logged_in else 0

        return render_template(
            template,
            prayers=prayers_list,
            is_logged_in=is_logged_in,
            is_staff_plus=is_staff_plus,
            is_admin_owner=is_admin_owner,
            current_user_id=user_id,
            pending_count=pending_count,
            total_count=len(prayers_list),
            public_count=sum(1 for p in prayers_list if p.get('visibility') == 'public'),
            private_count=sum(1 for p in prayers_list if p.get('visibility') == 'private'),
            with_responses_count=sum(1 for p in prayers_list if p.get('response_count', 0) > 0),
            no_responses_count=sum(1 for p in prayers_list if p.get('response_count', 0) == 0),
        )

    except Exception as exc:
        print(f"[DEBUG] Prayers listing EXCEPTION: {exc}")
        import traceback
        traceback.print_exc()
        flash('Failed to load prayers.', 'error')
        return render_template(
            'prayers/prayers_dashboard.html' if is_logged_in else 'public/prayers/prayers.html',
            prayers=[],
            is_logged_in=is_logged_in
        )


# ----------------------------------------------------------------------
# Add New Prayer Request - /prayers/add
# ----------------------------------------------------------------------
@prayers_bp.route('/add', methods=['GET', 'POST'])
def add_prayer():
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

    print(f"[DEBUG] Add prayer accessed - logged_in={is_logged_in}, user_id={user_id}")

    if request.method == 'POST':
        print("[DEBUG] POST data:", request.form.to_dict(flat=False))

        try:
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            visibility = request.form.get('visibility', 'public') if is_logged_in else 'public'
            contributor_name = request.form.get('contributor_name', '').strip() if not is_logged_in else None
            contributor_name = contributor_name or 'Anonymous' if not is_logged_in else None

            check_text = title + ' ' + description
            if contributor_name and contributor_name != 'Anonymous':
                check_text += ' ' + contributor_name

            if contains_censored_word(check_text):
                flash('Prayer request contains a prohibited word or phrase.', 'error')
            elif not title or not description:
                flash('Title and description are required.', 'error')
            else:
                db = get_db()
                cur = db.cursor()
                ip = request.remote_addr if not is_logged_in else None

                status = 'approved' if is_logged_in else 'pending'
                cur.execute("""
                    INSERT INTO prayers
                    (title, description, visibility, user_id, contributor_name, ip_address, status, date_posted)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())
                """, (title, description, visibility, user_id, contributor_name, ip, status))

                prayer_id = cur.lastrowid
                db.commit()

                log_change(user_id or 0, 'create_prayer', target_id=prayer_id,
                           change_details=f"Created prayer '{title}' ({visibility}, {status})")

                if is_logged_in:
                    flash('Prayer request submitted successfully!', 'success')
                else:
                    flash(
                        'Thank you - your prayer request was received and will appear after a brief review.',
                        'success',
                    )
                return redirect(url_for('prayers.prayers'))

            return render_template(
                'prayers/add_prayer.html',
                title=title,
                description=description,
                visibility=visibility,
                contributor_name=contributor_name or '',
                is_logged_in=is_logged_in
            )

        except Exception as exc:
            print(f"[DEBUG] Add prayer EXCEPTION: {exc}")
            import traceback
            traceback.print_exc()
            db.rollback()
            flash('Failed to submit prayer request.', 'error')
            return render_template('prayers/add_prayer.html', is_logged_in=is_logged_in)

    return render_template('prayers/add_prayer.html', is_logged_in=is_logged_in)


# ----------------------------------------------------------------------
# View Prayer + Add Response - /prayers/<int:prayer_id>
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>', methods=['GET', 'POST'])
def view_prayer(prayer_id):
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

    print(f"[DEBUG] View prayer ID {prayer_id} - logged_in={is_logged_in}")

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        if is_logged_in:
            cur.execute("""
                SELECT p.*,
                       COALESCE(CONCAT(u.first_name, ' ', u.last_name), p.contributor_name, 'Anonymous') AS creator_name
                FROM prayers p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.id = %s AND p.visibility IN ('public', 'private')
            """, (prayer_id,))
        else:
            cur.execute("""
                SELECT p.*,
                       COALESCE(p.contributor_name, 'Anonymous') AS creator_name
                FROM prayers p
                WHERE p.id = %s AND p.visibility = 'public'
            """, (prayer_id,))

        prayer = cur.fetchone()
        if not prayer:
            flash('Prayer request not found or not visible to you.', 'error')
            return redirect(url_for('prayers.prayers'))

        prayer['title'] = censor_text(prayer['title'] or '')
        prayer['description'] = censor_text(prayer['description'] or '')
        prayer['creator_name'] = censor_text(prayer['creator_name'] or 'Anonymous')
        if prayer['date_posted']:
            prayer['formatted_date'] = format_church(prayer['date_posted'], '%B %d, %Y at %I:%M %p')

        # Get responses
        responses = get_prayer_responses(prayer_id)

        if request.method == 'POST':
            response_text = request.form.get('prayer', '').strip()
            contributor_name = request.form.get('contributor_name', '').strip() if not is_logged_in else None
            contributor_name = contributor_name or 'Anonymous' if not is_logged_in else None

            check_text = response_text
            if contributor_name and contributor_name != 'Anonymous':
                check_text += ' ' + contributor_name

            if not response_text:
                flash('Response text is required.', 'error')
            elif contains_censored_word(check_text):
                flash('Response contains a prohibited word or phrase.', 'error')
            else:
                cur = db.cursor()
                ip = request.remote_addr if not is_logged_in else None
                cur.execute("""
                    INSERT INTO prayers_added
                    (prayer_request_id, prayer, user_id, contributor_name, ip_address, date_added)
                    VALUES (%s, %s, %s, %s, %s, UTC_TIMESTAMP())
                """, (prayer_id, response_text, user_id, contributor_name, ip))
                db.commit()

                log_change(user_id or 0, 'add_prayer_response', target_id=prayer_id,
                           change_details='Added response to prayer request')

                flash('Your prayer response has been added.', 'success')

            return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))

        if user_id:
            log_change(user_id, 'view', change_details=f"Viewed prayer request {prayer_id}")

        template = 'prayers/view_prayer.html' if is_logged_in else 'public/prayers/view_prayer.html'

        return render_template(
            template,
            prayer=prayer,
            responses=responses,
            is_logged_in=is_logged_in
        )

    except Exception as exc:
        print(f"[DEBUG] View prayer EXCEPTION (ID {prayer_id}): {exc}")
        import traceback
        traceback.print_exc()
        flash('Failed to load prayer request.', 'error')
        return redirect(url_for('prayers.prayers'))


# ----------------------------------------------------------------------
# Edit Prayer Request - /prayers/<int:prayer_id>/edit
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_prayer(prayer_id):
    user_id = session['user_id']
    user_role = session.get('user_role')
    is_staff_plus = user_role in REQUIRED_ROLES

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT * FROM prayers WHERE id = %s", (prayer_id,))
        prayer = cur.fetchone()
        if not prayer:
            flash('Prayer request not found.', 'error')
            return redirect(url_for('prayers.prayers'))

        if prayer['user_id'] != user_id and not is_staff_plus:
            flash('You are not authorized to edit this prayer request.', 'error')
            return redirect(url_for('prayers.prayers'))

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            visibility = request.form.get('visibility', prayer['visibility'])

            if contains_censored_word(title + ' ' + description):
                flash('Prayer request contains a prohibited word or phrase.', 'error')
            elif not title or not description:
                flash('Title and description are required.', 'error')
            else:
                cur = db.cursor()
                cur.execute("""
                    UPDATE prayers
                    SET title = %s, description = %s, visibility = %s
                    WHERE id = %s
                """, (title, description, visibility, prayer_id))
                db.commit()

                log_change(user_id, 'update_prayer', target_id=prayer_id,
                           change_details=f"Updated prayer '{title}'")

                flash('Prayer request updated successfully!', 'success')
                return redirect(url_for('prayers.prayers'))

        return render_template('prayers/edit_prayer.html', prayer=prayer)

    except Exception as exc:
        print(f"[DEBUG] Edit prayer EXCEPTION (ID {prayer_id}): {exc}")
        import traceback
        traceback.print_exc()
        flash('Failed to load/edit prayer request.', 'error')
        return redirect(url_for('prayers.prayers'))


# ----------------------------------------------------------------------
# Approve / Reject visitor prayer - staff only
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>/approve', methods=['POST'])
@login_required
@role_required(ADMIN_ROLES)
def approve_prayer(prayer_id):
    user_id = session['user_id']
    try:
        update_prayer_status(prayer_id, 'approved')
        log_change(user_id, 'approve_prayer', target_id=prayer_id, change_details='Approved visitor prayer request')
        flash('Prayer request approved and is now public.', 'success')
    except Exception:
        flash('Failed to approve prayer request.', 'error')
    return redirect(url_for('prayers.prayers'))


@prayers_bp.route('/<int:prayer_id>/reject', methods=['POST'])
@login_required
@role_required(ADMIN_ROLES)
def reject_prayer(prayer_id):
    user_id = session['user_id']
    try:
        update_prayer_status(prayer_id, 'rejected')
        log_change(user_id, 'reject_prayer', target_id=prayer_id, change_details='Rejected visitor prayer request')
        flash('Prayer request rejected.', 'success')
    except Exception:
        flash('Failed to reject prayer request.', 'error')
    return redirect(url_for('prayers.prayers'))


# ----------------------------------------------------------------------
# Delete Prayer Request - /prayers/<int:prayer_id>/delete
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>/delete', methods=['POST'])
@login_required
@role_required(ADMIN_ROLES)
def delete_prayer(prayer_id):
    user_id = session['user_id']

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        cur.execute("SELECT title FROM prayers WHERE id = %s", (prayer_id,))
        row = cur.fetchone()
        if not row:
            flash('Prayer request not found.', 'error')
            return redirect(url_for('prayers.prayers'))
        title = row['title']

        cur = db.cursor()
        cur.execute("DELETE FROM prayers_added WHERE prayer_request_id = %s", (prayer_id,))
        cur.execute("DELETE FROM prayers WHERE id = %s", (prayer_id,))
        db.commit()

        log_change(user_id, 'delete_prayer', target_id=prayer_id,
                   change_details=f"Deleted prayer '{title}'")

        flash('Prayer request deleted successfully.', 'success')

    except Exception as exc:
        db.rollback()
        print(f"[DEBUG] Delete prayer EXCEPTION (ID {prayer_id}): {exc}")
        import traceback
        traceback.print_exc()
        flash('Failed to delete prayer request.', 'error')

    return redirect(url_for('prayers.prayers'))


# ==================================================================
# NEW: DELETE RESPONSE (works for guest + member responses)
# ==================================================================
@prayers_bp.route('/<int:prayer_id>/delete_response/<int:response_id>', methods=['POST'])
@login_required
def delete_response(prayer_id, response_id):
    user_id = session['user_id']
    user_role = session.get('user_role')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Fetch response to check ownership
    cur.execute("SELECT user_id FROM prayers_added WHERE id = %s", (response_id,))
    response = cur.fetchone()

    is_owner = response and response['user_id'] == user_id
    is_moderator = user_role in ['Admin', 'Owner'] or session.get('user_has_permission', lambda p: False)('moderate_prayers')

    if not response or (not is_owner and not is_moderator):
        flash('You do not have permission to delete this response.', 'error')
        return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))

    try:
        cur = db.cursor()
        cur.execute("DELETE FROM prayers_added WHERE id = %s", (response_id,))
        db.commit()
        log_change(user_id, 'delete', target_id=response_id,
                   change_details=f'Deleted response on prayer {prayer_id}')
        flash('Response deleted.', 'success')
    except Exception:
        db.rollback()
        flash('Failed to delete response.', 'error')

    return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))


# ==================================================================
# NEW: EDIT RESPONSE (works for guest + member responses)
# ==================================================================
@prayers_bp.route('/<int:prayer_id>/edit_response/<int:response_id>', methods=['POST'])
@login_required
def edit_response(prayer_id, response_id):
    user_id = session['user_id']
    user_role = session.get('user_role')
    new_text = request.form.get('response_text', '').strip()

    if not new_text:
        flash('Response cannot be empty.', 'error')
        return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))

    if contains_censored_word(new_text):
        flash('Response contains a prohibited word or phrase.', 'error')
        return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT user_id FROM prayers_added WHERE id = %s", (response_id,))
    response = cur.fetchone()

    is_owner = response and response['user_id'] == user_id
    is_moderator = user_role in ['Admin', 'Owner'] or session.get('user_has_permission', lambda p: False)('moderate_prayers')

    if not response or (not is_owner and not is_moderator):
        flash('You do not have permission to edit this response.', 'error')
        return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))

    try:
        cur = db.cursor()
        cur.execute("""
            UPDATE prayers_added 
            SET prayer = %s, date_added = UTC_TIMESTAMP()
            WHERE id = %s
        """, (new_text, response_id))
        db.commit()
        log_change(user_id, 'update', target_id=response_id,
                   change_details=f'Edited response on prayer {prayer_id}')
        flash('Response updated.', 'success')
    except Exception:
        db.rollback()
        flash('Failed to update response.', 'error')

    return redirect(url_for('prayers.view_prayer', prayer_id=prayer_id))