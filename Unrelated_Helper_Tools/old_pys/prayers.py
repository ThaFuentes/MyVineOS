# app/routes/prayers_tgp.py
# Full path: myvinechurchonline/app/routes/prayers_tgp.py
# File name: prayers_tgp.py
# Brief, detailed purpose: Blueprint for prayer requests and responses – PUBLIC FOCUS.
# • /prayers_tgp → listing:
#   - Guests: ONLY public prayers_tgp → renders public/prayers_tgp/prayers_tgp.html (simple grid, read-only).
#   - Logged-in: public + private prayers_tgp → renders prayers_tgp/prayers_dash.html (richer private view with management).
# • /prayers_tgp/add → add new prayer request (guests submit public only, logged-in can choose public/private, default public).
# • /prayers_tgp/<int:prayer_id> → GET: view detail + responses (visibility enforced).
# • /prayers_tgp/<int:prayer_id> → POST: add response (guests on public, logged-in on any visible).
# • /prayers_tgp/<int:prayer_id>/edit → edit (creator or Staff/Admin/Owner).
# • /prayers_tgp/<int:prayer_id>/delete → delete (Admin/Owner only).
# Visibility: public (all visitors) / private (logged-in only) – no 'personal' level for prayers_tgp (per spec public focus).
# All text censored server-side on display and before save.
# All significant actions audit-logged.
# FULL REBUILD: Separate listing templates, robust error handling + debug prints, MariaDB-safe.
# Added response_count to listing query (for template data-responses).

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word, censor_text
from app.models.db import get_db
from app.models.log import log_change
from app.utils.time_utils import format_church
import pymysql

prayers_bp = Blueprint('prayers_tgp', __name__, url_prefix='/prayers_tgp')

REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']
ADMIN_ROLES = ['Admin', 'Owner']


# ----------------------------------------------------------------------
# Prayers Listing – /prayers_tgp
# ----------------------------------------------------------------------
@prayers_bp.route('/')
def prayers():
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

    print(f"[DEBUG] Prayers listing accessed – logged_in={is_logged_in}, user_id={user_id}")

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        if is_logged_in:
            print("[DEBUG] Logged-in view – fetching public + private prayers_tgp")
            cur.execute("""
                SELECT p.id, p.title, p.description, p.date_posted, p.visibility,
                       COALESCE(CONCAT(u.first_name, ' ', u.last_name), p.contributor_name, 'Anonymous') AS creator_name,
                       (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS response_count
                FROM prayers_tgp p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.visibility IN ('public', 'private')
                ORDER BY p.date_posted DESC
            """)
            template = 'prayers_tgp/prayers_dash.html'
        else:
            print("[DEBUG] Guest view – fetching public prayers_tgp only")
            cur.execute("""
                SELECT p.id, p.title, p.description, p.date_posted,
                       COALESCE(p.contributor_name, 'Anonymous') AS creator_name,
                       (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS response_count
                FROM prayers_tgp p
                WHERE p.visibility = 'public'
                ORDER BY p.date_posted DESC
            """)
            template = 'public/prayers_tgp/prayers_tgp.html'

        prayers_list = cur.fetchall()
        print(f"[DEBUG] Fetched {len(prayers_list)} prayers_tgp")

        for p in prayers_list:
            p['title'] = censor_text(p['title'] or '')
            p['description'] = censor_text(p['description'] or '')
            p['creator_name'] = censor_text(p['creator_name'] or 'Anonymous')
            if p['date_posted']:
                p['formatted_date'] = format_church(p['date_posted'], '%B %d, %Y at %I:%M %p')

        if user_id:
            log_change(user_id, 'view', change_details='Viewed prayers_tgp listing')

        print("[DEBUG] Rendering template with prayers_tgp list")
        return render_template(template, prayers=prayers_list, is_logged_in=is_logged_in)

    except Exception as exc:
        print(f"[DEBUG] Prayers listing EXCEPTION: {exc}")
        import traceback
        traceback.print_exc()
        flash('Failed to load prayers_tgp.', 'error')
        return render_template(
            'prayers_tgp/prayers_dash.html' if is_logged_in else 'public/prayers_tgp/prayers_tgp.html',
            prayers=[],
            is_logged_in=is_logged_in
        )


# ----------------------------------------------------------------------
# Add New Prayer Request – /prayers_tgp/add
# ----------------------------------------------------------------------
@prayers_bp.route('/add', methods=['GET', 'POST'])
def add_prayer():
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

    print(f"[DEBUG] Add prayer accessed – logged_in={is_logged_in}, user_id={user_id}")

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

                cur.execute("""
                    INSERT INTO prayers_tgp
                    (title, description, visibility, user_id, contributor_name, ip_address, date_posted)
                    VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())
                """, (title, description, visibility, user_id, contributor_name, ip))

                prayer_id = cur.lastrowid
                db.commit()

                log_change(user_id or 0, 'create_prayer', target_id=prayer_id,
                           change_details=f"Created prayer '{title}' ({visibility})")

                flash('Prayer request submitted successfully!', 'success')
                return redirect(url_for('prayers_tgp.prayers_tgp'))

            return render_template(
                'prayers_tgp/add_prayer.html',
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
            return render_template('prayers_tgp/add_prayer.html', is_logged_in=is_logged_in)

    return render_template('prayers_tgp/add_prayer.html', is_logged_in=is_logged_in)


# ----------------------------------------------------------------------
# View Prayer + Add Response – /prayers_tgp/<int:prayer_id>
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>', methods=['GET', 'POST'])
def view_prayer(prayer_id):
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

    print(f"[DEBUG] View prayer ID {prayer_id} – logged_in={is_logged_in}")

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        if is_logged_in:
            cur.execute("""
                SELECT p.*,
                       COALESCE(CONCAT(u.first_name, ' ', u.last_name), p.contributor_name, 'Anonymous') AS creator_name
                FROM prayers_tgp p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.id = %s AND p.visibility IN ('public', 'private')
            """, (prayer_id,))
        else:
            cur.execute("""
                SELECT p.*,
                       COALESCE(p.contributor_name, 'Anonymous') AS creator_name
                FROM prayers_tgp p
                WHERE p.id = %s AND p.visibility = 'public'
            """, (prayer_id,))

        prayer = cur.fetchone()
        if not prayer:
            flash('Prayer request not found or not visible to you.', 'error')
            return redirect(url_for('prayers_tgp.prayers_tgp'))

        prayer['title'] = censor_text(prayer['title'] or '')
        prayer['description'] = censor_text(prayer['description'] or '')
        prayer['creator_name'] = censor_text(prayer['creator_name'] or 'Anonymous')
        if prayer['date_posted']:
            prayer['formatted_date'] = format_church(prayer['date_posted'], '%B %d, %Y at %I:%M %p')

        cur.execute("""
            SELECT pa.id, pa.prayer, pa.date_added,
                   COALESCE(CONCAT(u.first_name, ' ', u.last_name), pa.contributor_name, 'Anonymous') AS responder_name
            FROM prayers_added pa
            LEFT JOIN users u ON pa.user_id = u.id
            WHERE pa.prayer_request_id = %s
            ORDER BY pa.date_added ASC
        """, (prayer_id,))
        responses = cur.fetchall()
        for r in responses:
            r['prayer'] = censor_text(r['prayer'] or '')
            r['responder_name'] = censor_text(r['responder_name'] or 'Anonymous')
            if r['date_added']:
                r['formatted_date'] = format_church(r['date_added'], '%B %d, %Y at %I:%M %p')

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

            return redirect(url_for('prayers_tgp.view_prayer', prayer_id=prayer_id))

        if user_id:
            log_change(user_id, 'view', change_details=f"Viewed prayer request {prayer_id}")

        template = 'prayers_tgp/view_prayer.html' if is_logged_in else 'public/prayers_tgp/view_prayer.html'

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
        return redirect(url_for('prayers_tgp.prayers_tgp'))


# ----------------------------------------------------------------------
# Edit Prayer Request – /prayers_tgp/<int:prayer_id>/edit
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
        cur.execute("SELECT * FROM prayers_tgp WHERE id = %s", (prayer_id,))
        prayer = cur.fetchone()
        if not prayer:
            flash('Prayer request not found.', 'error')
            return redirect(url_for('prayers_tgp.prayers_tgp'))

        if prayer['user_id'] != user_id and not is_staff_plus:
            flash('You are not authorized to edit this prayer request.', 'error')
            return redirect(url_for('prayers_tgp.prayers_tgp'))

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
                    UPDATE prayers_tgp
                    SET title = %s, description = %s, visibility = %s
                    WHERE id = %s
                """, (title, description, visibility, prayer_id))
                db.commit()

                log_change(user_id, 'update_prayer', target_id=prayer_id,
                           change_details=f"Updated prayer '{title}'")

                flash('Prayer request updated successfully!', 'success')
                return redirect(url_for('prayers_tgp.prayers_tgp'))

        return render_template('prayers_tgp/edit_prayer.html', prayer=prayer)

    except Exception as exc:
        print(f"[DEBUG] Edit prayer EXCEPTION (ID {prayer_id}): {exc}")
        import traceback
        traceback.print_exc()
        flash('Failed to load/edit prayer request.', 'error')
        return redirect(url_for('prayers_tgp.prayers_tgp'))


# ----------------------------------------------------------------------
# Delete Prayer Request – /prayers_tgp/<int:prayer_id>/delete
# ----------------------------------------------------------------------
@prayers_bp.route('/<int:prayer_id>/delete', methods=['POST'])
@login_required
@role_required(ADMIN_ROLES)
def delete_prayer(prayer_id):
    user_id = session['user_id']

    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        cur.execute("SELECT title FROM prayers_tgp WHERE id = %s", (prayer_id,))
        row = cur.fetchone()
        if not row:
            flash('Prayer request not found.', 'error')
            return redirect(url_for('prayers_tgp.prayers_tgp'))
        title = row['title']

        cur = db.cursor()
        cur.execute("DELETE FROM prayers_added WHERE prayer_request_id = %s", (prayer_id,))
        cur.execute("DELETE FROM prayers_tgp WHERE id = %s", (prayer_id,))
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

    return redirect(url_for('prayers_tgp.prayers_tgp'))