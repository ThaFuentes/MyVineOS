# myvinechurchonline/app/routes/dreams_tgp.py
# Full path: myvinechurchonline/app/routes/dreams_tgp.py
# File name: dreams_tgp.py
# Brief, detailed purpose: Blueprint for dreams_tgp & visions module – FULL REBUILD.
# Visibility levels:
#   - 'public'   : visible to everyone (including guests)
#   - 'private'  : visible to all logged-in members
#   - 'personal' : visible ONLY to the submitter
# • /dreams_tgp → listing:
#     - Guests: only public dreams_tgp
#     - Logged-in: public + private + own personal dreams_tgp
# • /dreams_tgp/<int:dream_id> → single dream detail view (visibility enforced)
# • /dreams_tgp/submit → submit new dream (logged-in only)
# • /dreams_tgp/edit/<int:dream_id> → edit dream (owner or Admin/Owner)
# • /dreams_tgp/delete/<int:dream_id> → delete dream (owner or Admin/Owner)
# • Comments: logged-in only, with censorship
# All text censored server-side on display and checked before save.
# All significant actions audit-logged.
# Single template for detail view (visibility enforced in route).

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.db import get_db
from app.models.log import log_change
from app.utils.decorators import login_required
from app.utils.helpers import contains_censored_word, censor_text
import pymysql
import traceback

dreams_bp = Blueprint('dreams_tgp', __name__, url_prefix='/dreams_tgp')

ADMIN_ROLES = ['Admin', 'Owner']


# ----------------------------------------------------------------------
# Main Listing – /dreams_tgp (single URL)
# ----------------------------------------------------------------------
@dreams_bp.route('/')
def dreams():
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    search_query = request.args.get('q', '').strip().lower()

    sql = """
        SELECT d.id, d.title, d.description, d.notes, d.category, d.date_occurred,
               d.date_posted, d.visibility, d.user_id,
               COALESCE(u.username, d.contributor_name, 'Anonymous') AS poster_name
        FROM dreams_tgp d
        LEFT JOIN users u ON d.user_id = u.id
    """
    params = []

    if is_logged_in:
        sql += """
            WHERE d.visibility IN ('public', 'private')
               OR (d.visibility = 'personal' AND d.user_id = %s)
        """
        params.append(user_id)
    else:
        sql += " WHERE d.visibility = 'public'"

    if search_query:
        like_param = '%' + search_query + '%'
        sql += " AND (LOWER(d.title) LIKE %s OR LOWER(d.description) LIKE %s)"
        params.extend([like_param, like_param])

    sql += " ORDER BY d.date_posted DESC"

    cur.execute(sql, params)
    dreams_list = cur.fetchall()

    for dream in dreams_list:
        dream['title'] = censor_text(dream['title'])
        dream['description'] = censor_text(dream['description'] or '')
        dream['notes'] = censor_text(dream['notes'] or '')

    if user_id:
        log_change(user_id, 'view', change_details='Viewed dreams_tgp & visions list')

    template = 'public/dreams_tgp/dreams_tgp.html' if not is_logged_in else 'dreams_tgp/dreams_tgp.html'
    return render_template(template, dream_data=dreams_list, search_query=search_query, is_logged_in=is_logged_in)


# ----------------------------------------------------------------------
# Single Dream Detail View – /dreams_tgp/<int:dream_id>
# ----------------------------------------------------------------------
@dreams_bp.route('/<int:dream_id>')
def view_dream(dream_id):
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')
    role = session.get('user_role', '')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT d.*,
               COALESCE(u.username, d.contributor_name, 'Anonymous') AS poster_name
        FROM dreams_tgp d
        LEFT JOIN users u ON d.user_id = u.id
        WHERE d.id = %s
    """, (dream_id,))
    dream = cur.fetchone()
    if not dream:
        flash('Dream not found.', 'error')
        return redirect(url_for('dreams_tgp.dreams_tgp'))

    # Visibility enforcement (unchanged)
    if dream['visibility'] == 'personal' and (not is_logged_in or dream['user_id'] != user_id):
        flash('This is a personal dream – visible only to the submitter.', 'error')
        return redirect(url_for('dreams_tgp.dreams_tgp'))
    if dream['visibility'] == 'private' and not is_logged_in:
        flash('This is a private dream – login required.', 'error')
        return redirect(url_for('dreams_tgp.dreams_tgp'))

    # Display censorship
    dream['title'] = censor_text(dream['title'])
    dream['description'] = censor_text(dream['description'] or '')
    dream['notes'] = censor_text(dream['notes'] or '')

    # Load comments.html
    cur.execute("""
        SELECT dc.id, dc.comment, dc.date_posted, dc.user_id,
               COALESCE(u.username, dc.contributor_name, 'Anonymous') AS commenter_name
        FROM dream_comments dc
        LEFT JOIN users u ON dc.user_id = u.id
        WHERE dc.dream_id = %s
        ORDER BY dc.date_posted ASC
    """, (dream_id,))
    comments = cur.fetchall()
    for c in comments:
        c['comment'] = censor_text(c['comment'])

    # Permissions (to match your template variables)
    can_edit = is_logged_in and (dream['user_id'] == user_id or role in ADMIN_ROLES)
    can_delete = role in ADMIN_ROLES
    current_user_id = user_id
    is_admin_owner = role in ADMIN_ROLES

    if user_id:
        log_change(user_id, 'view_dream', target_id=dream_id,
                   change_details=f"Viewed dream {dream_id}")

    return render_template('dreams_tgp/view_dream.html',
                           dream=dream,
                           comments=comments,
                           is_logged_in=is_logged_in,
                           can_edit=can_edit,
                           can_delete=can_delete,
                           current_user_id=current_user_id,
                           is_admin_owner=is_admin_owner)


# ----------------------------------------------------------------------
# Submit New Dream – /dreams_tgp/submit
# ----------------------------------------------------------------------
@dreams_bp.route('/submit', methods=['GET', 'POST'])
@login_required
def submit_dream():
    user_id = session['user_id']

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        notes = request.form.get('notes', '').strip()
        category = request.form.get('category', '').strip()
        date_occurred = request.form.get('date_occurred') or None
        visibility = request.form.get('visibility', 'private')

        if visibility not in ['public', 'private', 'personal']:
            visibility = 'private'

        combined = f"{title} {description} {notes} {category}"
        if contains_censored_word(combined):
            flash('Dream contains a prohibited word or phrase.', 'error')
        elif not title or not description:
            flash('Title and description are required.', 'error')
        else:
            try:
                db = get_db()
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO dreams_tgp
                    (user_id, title, description, notes, category, date_occurred, visibility)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, title, description, notes or None, category or None, date_occurred, visibility))
                dream_id = cur.lastrowid
                db.commit()

                log_change(user_id, 'create_dream', target_id=dream_id,
                           change_details=f"Submitted dream '{title}' (visibility: {visibility})")
                flash('Dream submitted successfully.', 'success')
                return redirect(url_for('dreams_tgp.dreams_tgp'))
            except Exception as e:
                db.rollback()
                flash('Failed to submit dream.', 'error')

        return render_template('dreams_tgp/add_dream.html',
                               title=title, description=description, notes=notes,
                               category=category, date_occurred=date_occurred,
                               visibility=visibility)

    return render_template('dreams_tgp/add_dream.html')


# ----------------------------------------------------------------------
# Edit Dream – /dreams_tgp/edit/<int:dream_id>
# ----------------------------------------------------------------------
@dreams_bp.route('/edit/<int:dream_id>', methods=['GET', 'POST'])
@login_required
def edit_dream(dream_id):
    user_id = session['user_id']
    role = session.get('user_role', '')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM dreams_tgp WHERE id = %s", (dream_id,))
    dream = cur.fetchone()

    if not dream:
        flash('Dream not found.', 'error')
        return redirect(url_for('dreams_tgp.dreams_tgp'))

    if dream['user_id'] != user_id and role not in ADMIN_ROLES:
        flash('Not authorized to edit this dream.', 'error')
        return redirect(url_for('dreams_tgp.dreams_tgp'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        notes = request.form.get('notes', '').strip()
        category = request.form.get('category', '').strip()
        date_occurred = request.form.get('date_occurred') or None
        visibility = request.form.get('visibility', dream['visibility'])

        if visibility not in ['public', 'private', 'personal']:
            visibility = dream['visibility']

        combined = f"{title} {description} {notes} {category}"
        if contains_censored_word(combined):
            flash('Dream contains a prohibited word or phrase.', 'error')
        elif not title or not description:
            flash('Title and description are required.', 'error')
        else:
            try:
                cur = db.cursor()
                cur.execute("""
                    UPDATE dreams_tgp
                    SET title = %s, description = %s, notes = %s, category = %s,
                        date_occurred = %s, visibility = %s
                    WHERE id = %s
                """, (title, description, notes or None, category or None,
                      date_occurred, visibility, dream_id))
                db.commit()

                log_change(user_id, 'update_dream', target_id=dream_id,
                           change_details=f"Updated dream '{title}' (visibility: {visibility})")
                flash('Dream updated successfully.', 'success')
                return redirect(url_for('dreams_tgp.dreams_tgp'))
            except Exception as e:
                db.rollback()
                flash('Failed to update dream.', 'error')

        dream.update({
            'title': title, 'description': description, 'notes': notes,
            'category': category, 'date_occurred': date_occurred, 'visibility': visibility
        })

    return render_template('dreams_tgp/edit_dream.html', dream=dream)


# ----------------------------------------------------------------------
# Delete Dream – /dreams_tgp/delete/<int:dream_id>
# ----------------------------------------------------------------------
@dreams_bp.route('/delete/<int:dream_id>', methods=['POST'])
@login_required
def delete_dream(dream_id):
    user_id = session['user_id']
    role = session.get('user_role', '')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT title, user_id FROM dreams_tgp WHERE id = %s", (dream_id,))
    dream = cur.fetchone()

    if not dream:
        flash('Dream not found.', 'error')
        return redirect(url_for('dreams_tgp.dreams_tgp'))

    if dream['user_id'] != user_id and role not in ADMIN_ROLES:
        flash('Not authorized to delete this dream.', 'error')
        return redirect(url_for('dreams_tgp.dreams_tgp'))

    try:
        cur = db.cursor()
        cur.execute("DELETE FROM dreams_tgp WHERE id = %s", (dream_id,))
        db.commit()

        log_change(user_id, 'delete_dream', target_id=dream_id,
                   change_details=f"Deleted dream '{dream['title']}'")
        flash('Dream deleted successfully.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to delete dream.', 'error')

    return redirect(url_for('dreams_tgp.dreams_tgp'))


# ----------------------------------------------------------------------
# Add Comment – /dreams_tgp/comment/add/<int:dream_id>
# ----------------------------------------------------------------------
@dreams_bp.route('/comment/add/<int:dream_id>', methods=['POST'])
@login_required
def add_comment(dream_id):
    comment_text = request.form.get('comment', '').strip()
    if not comment_text:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))

    if contains_censored_word(comment_text):
        flash('Comment contains a prohibited word or phrase.', 'error')
        return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO dream_comments (dream_id, user_id, comment)
            VALUES (%s, %s, %s)
        """, (dream_id, session['user_id'], comment_text))
        db.commit()

        log_change(session['user_id'], 'add_comment', target_id=dream_id,
                   change_details='Added comment to dream')
        flash('Comment added.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to add comment.', 'error')

    return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))


# ----------------------------------------------------------------------
# Update Comment – /dreams_tgp/comment/update/<int:dream_id>/<int:comment_id>
# ----------------------------------------------------------------------
@dreams_bp.route('/comment/update/<int:dream_id>/<int:comment_id>', methods=['POST'])
@login_required
def update_comment(dream_id, comment_id):
    new_text = request.form.get('comment', '').strip()
    if not new_text:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))

    if contains_censored_word(new_text):
        flash('Comment contains a prohibited word or phrase.', 'error')
        return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id FROM dream_comments WHERE id = %s", (comment_id,))
    comment = cur.fetchone()

    if not comment or comment['user_id'] != session['user_id']:
        flash('Not authorized to edit this comment.', 'error')
        return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))

    try:
        cur = db.cursor()
        cur.execute("UPDATE dream_comments SET comment = %s WHERE id = %s", (new_text, comment_id))
        db.commit()
        log_change(session['user_id'], 'update_comment', target_id=dream_id,
                   change_details='Updated dream comment')
        flash('Comment updated.', 'success')
    except Exception as e:
        db.rollback()
        flash('Error updating comment.', 'error')

    return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))


# ----------------------------------------------------------------------
# Delete Comment – /dreams_tgp/comment/delete/<int:dream_id>/<int:comment_id>
# ----------------------------------------------------------------------
@dreams_bp.route('/comment/delete/<int:dream_id>/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(dream_id, comment_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT user_id FROM dream_comments WHERE id = %s", (comment_id,))
    comment = cur.fetchone()

    if not comment or (comment['user_id'] != session['user_id'] and session.get('user_role') not in ADMIN_ROLES):
        flash('Not authorized to delete this comment.', 'error')
        return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))

    try:
        cur = db.cursor()
        cur.execute("DELETE FROM dream_comments WHERE id = %s", (comment_id,))
        db.commit()
        log_change(session['user_id'], 'delete_comment', target_id=dream_id,
                   change_details='Deleted dream comment')
        flash('Comment deleted.', 'success')
    except Exception as e:
        db.rollback()
        flash('Error deleting comment.', 'error')

    return redirect(url_for('dreams_tgp.view_dream', dream_id=dream_id))