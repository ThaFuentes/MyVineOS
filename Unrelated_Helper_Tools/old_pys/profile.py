# myvinechurchonline/app/routes/profile.py
# Full path: myvinechurchonline/app/routes/profile.py
# File name: profile.py
# Brief, detailed purpose: Handles user profile viewing/editing (personal info, password, birthday visibility, new privacy preferences, check-in PIN)
#          and full family relationship management:
#            - View approved family and pending incoming requests
#            - Search/send family link requests (with relation type) – respects allow_family_search = 1
#            - Approve/reject incoming requests
#            - Remove approved relationships
#            - Suggest potential family (same last name, no existing relation, respects allow_family_search = 1)
#          Enforces authentication, prevents self-linking/duplicates, cleans rejected requests on resend,
#          and logs all relationship actions for audit.
#          FULL REBUILD: Added form fields and update logic for new privacy preferences:
#            - allow_proxy_checkin (checkbox, default 1)
#            - allow_group_add (checkbox, default 1)
#            - allow_family_search (checkbox, default 1)
#            - checkin_pin (optional 4-6 digit PIN, hashed with Werkzeug for kiosk self check-in)
#          Censored word check on visible text fields (first_name, last_name, email, phone, address) and relation_type.
#          Family search and suggested users now respect allow_family_search = 1 (opt-out users hidden).
#          PIN validated (4-6 digits or empty, stored hashed).
#          Preserved every existing feature/logic exactly.
#          MariaDB/pymysql compatible: DictCursor, %s placeholders.

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from app.models.db import get_db
from app.models.log import log_change
from app.utils.decorators import login_required
from app.utils.helpers import contains_censored_word
import pymysql
import traceback

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')


@profile_bp.route('/', methods=['GET', 'POST'])
@login_required
def profile():
    """View and update personal profile; manage family relationships including search (respects allow_family_search)."""
    user_id = session['user_id']

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        search_results = []

        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'search':
                search_query = request.form['search_query'].strip().lower()
                like_param = '%' + search_query + '%'
                cur.execute('''
                    SELECT id, first_name, last_name
                    FROM users
                    WHERE (LOWER(first_name) LIKE %s OR LOWER(last_name) LIKE %s OR LOWER(email) LIKE %s)
                      AND id != %s
                      AND allow_family_search = 1
                      AND id NOT IN (
                          SELECT relative_id FROM family_relations WHERE user_id = %s AND status IN ('pending', 'approved')
                          UNION
                          SELECT user_id FROM family_relations WHERE relative_id = %s AND status IN ('pending', 'approved')
                      )
                ''', (like_param, like_param, like_param, user_id, user_id, user_id))
                search_results = cur.fetchall()

            else:  # Profile update
                first_name = request.form['first_name'].strip()
                last_name = request.form['last_name'].strip()
                email = request.form['email'].strip()
                phone = request.form['phone'].strip()
                address = request.form['address'].strip()
                birthday = request.form.get('birthday', '').strip() or None
                show_birthday = 1 if request.form.get('show_birthday') == 'on' else 0

                # New privacy preferences
                allow_proxy_checkin = 1 if request.form.get('allow_proxy_checkin') == 'on' else 0
                allow_group_add = 1 if request.form.get('allow_group_add') == 'on' else 0
                allow_family_search = 1 if request.form.get('allow_family_search') == 'on' else 0
                checkin_pin = request.form.get('checkin_pin', '').strip()

                # Validate PIN (4-6 digits or empty)
                if checkin_pin:
                    if not (checkin_pin.isdigit() and 4 <= len(checkin_pin) <= 6):
                        flash('Check-in PIN must be 4-6 digits.', 'error')
                        return redirect(url_for('profile.profile'))
                    hashed_pin = generate_password_hash(checkin_pin)
                else:
                    hashed_pin = None  # Clear PIN if left empty

                old_password = request.form.get('old_password', '').strip()
                new_password = request.form.get('new_password', '').strip()
                confirm_pw = request.form.get('confirm_password', '').strip()

                # Censored words check on visible fields
                visible_text = f"{first_name} {last_name} {email} {phone} {address}"
                if contains_censored_word(visible_text):
                    flash('Profile contains a prohibited word or phrase.', 'error')
                    return redirect(url_for('profile.profile'))

                if new_password and new_password != confirm_pw:
                    flash('New passwords do not match.', 'error')
                    return redirect(url_for('profile.profile'))
                if new_password and not old_password:
                    flash('Old password required to set a new one.', 'error')
                    return redirect(url_for('profile.profile'))

                # Update basic fields + new preferences + PIN
                cur.execute('''
                    UPDATE users
                    SET first_name = %s, last_name = %s, email = %s, phone = %s, address = %s,
                        birthday = %s, show_birthday = %s,
                        allow_proxy_checkin = %s, allow_group_add = %s, allow_family_search = %s,
                        checkin_pin = %s
                    WHERE id = %s
                ''', (first_name, last_name, email, phone, address, birthday, show_birthday,
                      allow_proxy_checkin, allow_group_add, allow_family_search,
                      hashed_pin, user_id))

                # Password update
                if old_password and new_password:
                    cur.execute('SELECT password FROM users WHERE id = %s', (user_id,))
                    current_hash = cur.fetchone()['password']
                    if check_password_hash(current_hash, old_password):
                        hashed_new = generate_password_hash(new_password)
                        cur.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_new, user_id))
                        flash('Password updated successfully.', 'success')
                    else:
                        flash('Old password is incorrect.', 'error')
                        return redirect(url_for('profile.profile'))

                db.commit()
                flash('Profile updated successfully.', 'success')
                log_change(user_id, 'update', target_id=user_id, change_details='Updated personal profile and privacy preferences')

        # Load current user (including new fields)
        cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()

        # Pending incoming requests
        cur.execute('''
            SELECT fr.id, CONCAT(u.first_name, ' ', u.last_name) AS name, fr.relation_type
            FROM family_relations fr
            JOIN users u ON fr.user_id = u.id
            WHERE fr.relative_id = %s AND fr.status = 'pending'
            ORDER BY fr.requested_at DESC
        ''', (user_id,))
        pending_requests = cur.fetchall()

        # Approved family (both directions)
        cur.execute('''
            SELECT fr.id,
                   CASE
                     WHEN fr.user_id = %s THEN CONCAT(u2.first_name, ' ', u2.last_name)
                     ELSE CONCAT(u1.first_name, ' ', u1.last_name)
                   END AS name,
                   fr.relation_type
            FROM family_relations fr
            LEFT JOIN users u1 ON fr.user_id = u1.id
            LEFT JOIN users u2 ON fr.relative_id = u2.id
            WHERE fr.status = 'approved' AND %s IN (fr.user_id, fr.relative_id)
            ORDER BY name
        ''', (user_id, user_id))
        family = cur.fetchall()

        # Suggested family (same last name, no relation, respects allow_family_search)
        cur.execute('''
            SELECT u.id, u.first_name, u.last_name
            FROM users u
            WHERE LOWER(u.last_name) = LOWER((SELECT last_name FROM users WHERE id = %s))
              AND u.id != %s
              AND u.allow_family_search = 1
              AND u.id NOT IN (
                  SELECT relative_id FROM family_relations WHERE user_id = %s AND status IN ('pending', 'approved')
                  UNION
                  SELECT user_id FROM family_relations WHERE relative_id = %s AND status IN ('pending', 'approved')
              )
            ORDER BY u.first_name
        ''', (user_id, user_id, user_id, user_id))
        suggested_users = cur.fetchall()

    except Exception as e:
        flash('Database error occurred.', 'error')
        print(f"Profile error: {e}\n{traceback.format_exc()}")
        return redirect(url_for('dashboard_tgp.dashboard_tgp'))

    return render_template(
        'profile/profile.html',
        user=user,
        pending_requests=pending_requests,
        family=family,
        suggested_users=suggested_users,
        search_results=search_results
    )


@profile_bp.route('/family/request', methods=['POST'])
@login_required
def request_family():
    user_id     = session['user_id']
    relative_id = int(request.form['relative_id'])
    relation    = request.form['relation_type'].strip()

    if user_id == relative_id:
        flash('You cannot request a relationship with yourself.', 'error')
        return redirect(url_for('profile.profile'))

    # Censored words check on relation_type
    if contains_censored_word(relation):
        flash('Relation type contains a prohibited word or phrase.', 'error')
        return redirect(url_for('profile.profile'))

    try:
        db = get_db()
        cur = db.cursor()

        # Clean rejected
        cur.execute('''
            DELETE FROM family_relations
            WHERE ((user_id = %s AND relative_id = %s) OR
                   (user_id = %s AND relative_id = %s))
              AND status = 'rejected'
        ''', (user_id, relative_id, relative_id, user_id))

        # Check duplicate
        cur.execute('''
            SELECT 1 FROM family_relations
            WHERE ((user_id = %s AND relative_id = %s) OR
                   (user_id = %s AND relative_id = %s))
              AND status IN ('pending', 'approved')
        ''', (user_id, relative_id, relative_id, user_id))
        if cur.fetchone():
            flash('A relationship request already exists.', 'error')
            return redirect(url_for('profile.profile'))

        # Insert pending
        cur.execute('''
            INSERT INTO family_relations (user_id, relative_id, relation_type, status)
            VALUES (%s, %s, %s, 'pending')
        ''', (user_id, relative_id, relation))
        db.commit()

        log_change(user_id, 'create', change_details=f'Sent family request ({relation}) to user {relative_id}')
        flash('Family request sent—awaiting approval.', 'success')

    except Exception as e:
        db.rollback()
        flash('Failed to send request.', 'error')
        print(f"Request family error: {e}")

    return redirect(url_for('profile.profile'))


@profile_bp.route('/family/approve/<int:fr_id>', methods=['POST'])
@login_required
def approve_family(fr_id):
    user_id = session['user_id']

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute('''
            UPDATE family_relations
            SET status = 'approved', responded_at = CURRENT_TIMESTAMP, approved_by = %s
            WHERE id = %s AND relative_id = %s AND status = 'pending'
        ''', (user_id, fr_id, user_id))

        if cur.rowcount:
            db.commit()
            log_change(user_id, 'update', target_id=fr_id, change_details='Approved family request')
            flash('Family request approved.', 'success')
        else:
            flash('Invalid or already processed request.', 'error')

    except Exception as e:
        db.rollback()
        flash('Failed to approve request.', 'error')
        print(f"Approve family error: {e}")

    return redirect(url_for('profile.profile'))


@profile_bp.route('/family/reject/<int:fr_id>', methods=['POST'])
@login_required
def reject_family(fr_id):
    user_id = session['user_id']

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute('''
            UPDATE family_relations
            SET status = 'rejected', responded_at = CURRENT_TIMESTAMP
            WHERE id = %s AND relative_id = %s AND status = 'pending'
        ''', (fr_id, user_id))

        if cur.rowcount:
            db.commit()
            log_change(user_id, 'update', target_id=fr_id, change_details='Rejected family request')
            flash('Family request rejected.', 'info')
        else:
            flash('Invalid or already processed request.', 'error')

    except Exception as e:
        db.rollback()
        flash('Failed to reject request.', 'error')
        print(f"Reject family error: {e}")

    return redirect(url_for('profile.profile'))


@profile_bp.route('/family/remove/<int:fr_id>', methods=['POST'])
@login_required
def remove_family(fr_id):
    user_id = session['user_id']

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute('''
            DELETE FROM family_relations
            WHERE id = %s AND status = 'approved'
              AND (user_id = %s OR relative_id = %s)
        ''', (fr_id, user_id, user_id))

        if cur.rowcount:
            db.commit()
            log_change(user_id, 'delete', target_id=fr_id, change_details='Removed family relationship')
            flash('Family relationship removed.', 'success')
        else:
            flash('Could not remove relationship.', 'error')

    except Exception as e:
        db.rollback()
        flash('Failed to remove relationship.', 'error')
        print(f"Remove family error: {e}")

    return redirect(url_for('profile.profile'))