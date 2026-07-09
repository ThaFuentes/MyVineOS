# app/routes/prophecies/views.py
# Full path: MyVineChurch/app/routes/prophecies/views.py
# File name: views.py
# Brief, detailed purpose: All route handlers for the Prophecies blueprint.
# • 100% rebuilt
# • Guests are FORCED to the public page (no access to private list or view)
# • Logged-in users see full private experience (public + private + personal)
# • All original behavior preserved
# • FIXED: Correct full public endpoint names for guest redirects

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word, censor_text
from app.models.db import get_db
from app.models.log import log_change
import pymysql

from . import prophecies_bp

REQUIRED_ROLES = ['Admin', 'Owner']


# ----------------------------------------------------------------------
# Main Listing – /prophecies
# ----------------------------------------------------------------------
@prophecies_bp.route('/')
def list_prophecies():
    if 'user_id' not in session:
        # Guest → go to public page (FULL CORRECT NAME)
        return redirect(url_for('public.public_prophecies.public_prophecies'))

    is_logged_in = True
    user_id = session.get('user_id')
    role = session.get('user_role', '')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    search_query = request.args.get('q', '').strip().lower()

    sql = """
        SELECT p.id, p.title, p.description, p.created_at AS date_posted, p.visibility,
               p.user_id,
               COALESCE(u.username, 'Anonymous') AS poster_name,
               (SELECT COUNT(*) FROM prophecy_comments pc WHERE pc.prophecy_id = p.id) AS comment_count
        FROM prophecies p
        LEFT JOIN users u ON p.user_id = u.id
    """
    params = []

    sql += """
        WHERE p.visibility IN ('public', 'private')
           OR (p.visibility = 'personal' AND p.user_id = %s)
    """
    params.append(user_id)

    if search_query:
        like_param = '%' + search_query + '%'
        sql += " AND (LOWER(p.title) LIKE %s OR LOWER(p.description) LIKE %s)"
        params.extend([like_param, like_param])

    sql += " ORDER BY p.created_at DESC"

    cur.execute(sql, params)
    prophecy_data = cur.fetchall()

    for p in prophecy_data:
        p['title'] = censor_text(p['title'])
        p['description'] = censor_text(p['description'] or '')
        p['poster_name'] = censor_text(p['poster_name'])

    return render_template('prophecies/prophecies.html',
                           prophecy_data=prophecy_data,
                           search_query=search_query,
                           is_logged_in=True,
                           current_user_id=user_id,
                           is_admin_owner=(role in REQUIRED_ROLES))


# ----------------------------------------------------------------------
# Single Prophecy View
# ----------------------------------------------------------------------
@prophecies_bp.route('/<int:prophecy_id>')
def view_prophecy(prophecy_id):
    if 'user_id' not in session:
        # Guest → go to public detail page (FULL CORRECT NAME)
        return redirect(url_for('public.public_prophecies.public_prophecy_detail', prophecy_id=prophecy_id))

    is_logged_in = True
    user_id = session.get('user_id')
    role = session.get('user_role', '')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT p.*,
               COALESCE(u.username, 'Anonymous') AS poster_name
        FROM prophecies p
        LEFT JOIN users u ON p.user_id = u.id
        WHERE p.id = %s
    """, (prophecy_id,))
    prophecy = cur.fetchone()

    if not prophecy:
        flash('Prophecy not found.', 'error')
        return redirect(url_for('prophecies.list_prophecies'))

    # Visibility enforcement for logged-in users
    visibility = prophecy.get('visibility')
    if visibility == 'personal' and prophecy['user_id'] != user_id:
        flash('This is a personal prophecy – visible only to the submitter.', 'error')
        return redirect(url_for('prophecies.list_prophecies'))

    # Server-side censorship
    prophecy['title'] = censor_text(prophecy['title'])
    prophecy['description'] = censor_text(prophecy.get('description') or '')

    # Load comments.html
    cur.execute("""
        SELECT pc.id, pc.comment, pc.date_added, pc.user_id,
               COALESCE(u.username, 'Anonymous') AS commenter_name
        FROM prophecy_comments pc
        LEFT JOIN users u ON pc.user_id = u.id
        WHERE pc.prophecy_id = %s
        ORDER BY pc.date_added ASC
    """, (prophecy_id,))
    comments = cur.fetchall()
    for c in comments:
        c['comment'] = censor_text(c['comment'])

    can_edit = (prophecy['user_id'] == user_id) or (role in REQUIRED_ROLES)
    can_delete = role in REQUIRED_ROLES

    if user_id:
        log_change(user_id, 'view_prophecy', target_id=prophecy_id,
                   change_details=f"Viewed prophecy {prophecy_id}")

    return render_template('prophecies/view_prophecy.html',
                           prophecy=prophecy,
                           comments=comments,
                           is_logged_in=True,
                           can_edit=can_edit,
                           can_delete=can_delete,
                           current_user_id=user_id,
                           is_admin_owner=(role in REQUIRED_ROLES))


# ----------------------------------------------------------------------
# Add, Edit, Delete, Comments (already require login)
# ----------------------------------------------------------------------
@prophecies_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_prophecy():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        visibility = request.form.get('visibility', 'private')

        if not title or not description:
            flash('Title and description are required.', 'error')
            return redirect(url_for('prophecies.add_prophecy'))

        if visibility not in ('public', 'private', 'personal'):
            flash('Invalid visibility setting.', 'error')
            return redirect(url_for('prophecies.add_prophecy'))

        if contains_censored_word(title) or contains_censored_word(description):
            flash('Content contains prohibited words.', 'error')
            return redirect(url_for('prophecies.add_prophecy'))

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO prophecies (title, description, visibility, user_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (title, description, visibility, session['user_id']))
            db.commit()
            prophecy_id = cur.lastrowid
            log_change(session['user_id'], 'create_prophecy', target_id=prophecy_id,
                       change_details=f"Added prophecy '{title}'")
            flash('Prophecy submitted successfully.', 'success')
            return redirect(url_for('prophecies.list_prophecies'))
        except Exception as e:
            db.rollback()
            flash('Failed to submit prophecy.', 'error')
            print(f"Add prophecy error: {e}")

    return render_template('prophecies/add_prophecy.html')


@prophecies_bp.route('/edit/<int:prophecy_id>', methods=['GET', 'POST'])
@login_required
def edit_prophecy(prophecy_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM prophecies WHERE id = %s", (prophecy_id,))
    prophecy = cur.fetchone()

    if not prophecy or (prophecy['user_id'] != session['user_id'] and session.get('user_role') not in REQUIRED_ROLES):
        flash('Not authorized to edit this prophecy.', 'error')
        return redirect(url_for('prophecies.list_prophecies'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        visibility = request.form.get('visibility', prophecy['visibility'])

        if not title or not description:
            flash('Title and description are required.', 'error')
            return redirect(url_for('prophecies.edit_prophecy', prophecy_id=prophecy_id))

        if visibility not in ('public', 'private', 'personal'):
            flash('Invalid visibility setting.', 'error')
            return redirect(url_for('prophecies.edit_prophecy', prophecy_id=prophecy_id))

        if contains_censored_word(title) or contains_censored_word(description):
            flash('Content contains prohibited words.', 'error')
            return redirect(url_for('prophecies.edit_prophecy', prophecy_id=prophecy_id))

        try:
            cur.execute("""
                UPDATE prophecies 
                SET title = %s, description = %s, visibility = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (title, description, visibility, prophecy_id))
            db.commit()
            log_change(session['user_id'], 'update_prophecy', target_id=prophecy_id,
                       change_details=f"Edited prophecy '{title}'")
            flash('Prophecy updated successfully.', 'success')
            return redirect(url_for('prophecies.list_prophecies'))
        except Exception as e:
            db.rollback()
            flash('Failed to update prophecy.', 'error')
            print(f"Edit prophecy error: {e}")

    prophecy['title'] = censor_text(prophecy['title'])
    prophecy['description'] = censor_text(prophecy['description'])

    return render_template('prophecies/edit_prophecy.html', prophecy=prophecy)


@prophecies_bp.route('/delete/<int:prophecy_id>', methods=['POST'])
@login_required
@role_required(REQUIRED_ROLES)
def delete_prophecy(prophecy_id):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM prophecies WHERE id = %s", (prophecy_id,))
        db.commit()
        if cur.rowcount:
            log_change(session['user_id'], 'delete_prophecy', target_id=prophecy_id,
                       change_details='Deleted prophecy')
            flash('Prophecy deleted successfully.', 'success')
        else:
            flash('Prophecy not found.', 'error')
    except Exception as e:
        db.rollback()
        flash('Failed to delete prophecy.', 'error')
        print(f"Delete prophecy error: {e}")

    return redirect(url_for('prophecies.list_prophecies'))


# Comment routes (already protected by @login_required)
@prophecies_bp.route('/comment/add/<int:prophecy_id>', methods=['POST'])
@login_required
def add_comment(prophecy_id):
    comment_text = request.form.get('comment', '').strip()
    if not comment_text:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('prophecies.view_prophecy', prophecy_id=prophecy_id))

    if contains_censored_word(comment_text):
        flash('Comment contains a prohibited word or phrase.', 'error')
        return redirect(url_for('prophecies.view_prophecy', prophecy_id=prophecy_id))

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO prophecy_comments (prophecy_id, user_id, comment, date_added)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (prophecy_id, session['user_id'], comment_text))
        db.commit()
        log_change(session['user_id'], 'add_comment', target_id=prophecy_id,
                   change_details='Added prophecy comment')
        flash('Comment added.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to add comment.', 'error')
        print(f"Add comment error: {e}")

    return redirect(url_for('prophecies.view_prophecy', prophecy_id=prophecy_id))


@prophecies_bp.route('/comment/edit/<int:comment_id>', methods=['POST'])
@login_required
def edit_comment(comment_id):
    comment_text = request.form.get('comment', '').strip()
    prophecy_id = request.form.get('prophecy_id')

    if not comment_text or not prophecy_id:
        flash('Invalid request.', 'error')
        return redirect(url_for('prophecies.list_prophecies'))

    if contains_censored_word(comment_text):
        flash('Comment contains a prohibited word or phrase.', 'error')
        return redirect(url_for('prophecies.list_prophecies'))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id, prophecy_id FROM prophecy_comments WHERE id = %s", (comment_id,))
    comment = cur.fetchone()

    if not comment or (comment['user_id'] != session['user_id'] and session.get('user_role') not in REQUIRED_ROLES):
        flash('Not authorized to edit this comment.', 'error')
        return redirect(url_for('prophecies.list_prophecies'))

    try:
        cur.execute("UPDATE prophecy_comments SET comment = %s WHERE id = %s", (comment_text, comment_id))
        db.commit()
        log_change(session['user_id'], 'update_comment', target_id=comment['prophecy_id'],
                   change_details='Updated prophecy comment')
        flash('Comment updated.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to update comment.', 'error')
        print(f"Edit comment error: {e}")

    return redirect(url_for('prophecies.view_prophecy', prophecy_id=comment['prophecy_id']))


@prophecies_bp.route('/comment/delete/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    prophecy_id = request.form.get('prophecy_id')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id, prophecy_id FROM prophecy_comments WHERE id = %s", (comment_id,))
    comment = cur.fetchone()

    if not comment or (comment['user_id'] != session['user_id'] and session.get('user_role') not in REQUIRED_ROLES):
        flash('Not authorized to delete this comment.', 'error')
        return redirect(url_for('prophecies.list_prophecies'))

    try:
        cur.execute("DELETE FROM prophecy_comments WHERE id = %s", (comment_id,))
        db.commit()
        log_change(session['user_id'], 'delete_comment', target_id=comment['prophecy_id'],
                   change_details='Deleted prophecy comment')
        flash('Comment deleted.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to delete comment.', 'error')
        print(f"Delete comment error: {e}")

    return redirect(url_for('prophecies.view_prophecy', prophecy_id=comment['prophecy_id']))