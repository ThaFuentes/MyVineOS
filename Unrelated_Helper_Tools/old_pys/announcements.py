# app/routes/announcements_tgp.py
# Full path: MyVineChurch/app/routes/announcements_tgp.py
# File name: announcements_tgp.py
# Brief, detailed purpose: Fully rebuilt Announcements blueprint – 100% clean, MariaDB/pymysql compatible.
# • /announcements_tgp → dashboard_tgp (logged-in) or public list (guests)
# • /announcements_tgp/<int:ann_id> → clean separate detail page (view_annoucements.html)
# • Create/edit/delete/email: Staff/Admin/Owner only
# • Full server-side censorship, audit logging, formatted dates
# • No inline expansion – titles link to proper full view page

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import pymysql
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change
from app.utils.emailer import send_email
from app.utils.time_utils import format_church

announcements_bp = Blueprint('announcements_tgp', __name__, url_prefix='/announcements_tgp')

REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']


# ----------------------------------------------------------------------
# Main Listing – /announcements_tgp (dashboard_tgp for logged-in, public list for guests)
# ----------------------------------------------------------------------
@announcements_bp.route('/')
def announcements():
    is_logged_in = 'user_id' in session
    can_manage = is_logged_in and session.get('user_role') in REQUIRED_ROLES

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if is_logged_in:
        cur.execute("""
            SELECT a.id, a.title, a.content, a.created_at, a.visibility,
                   a.is_active, a.comments_enabled, a.created_by,
                   COALESCE(u.username, 'Unknown') AS creator_name
            FROM announcements_tgp a
            LEFT JOIN users u ON a.created_by = u.id
            ORDER BY a.created_at DESC
        """)
    else:
        cur.execute("""
            SELECT a.id, a.title, a.content, a.created_at,
                   a.visibility, a.is_active, a.comments_enabled,
                   COALESCE(u.username, 'Unknown') AS creator_name
            FROM announcements_tgp a
            LEFT JOIN users u ON a.created_by = u.id
            WHERE a.visibility = 'public' AND a.is_active = 1
            ORDER BY a.created_at DESC
        """)

    announcements_list = cur.fetchall()

    # Public view for guests
    if not is_logged_in:
        public_list = []
        for ann in announcements_list:
            a = dict(ann)
            created = ann['created_at']
            a['datetime'] = f"{created.strftime('%B')} {created.day}, {created.year}" if created else 'Unknown'
            a['posted_by'] = ann['creator_name']
            public_list.append(a)
        return render_template(
            'public/announcements_tgp/announcements_tgp.html',
            announcements=public_list
        )

    # Private dashboard_tgp for logged-in users
    for ann in announcements_list:
        cur.execute("SELECT COUNT(*) AS cnt FROM announcement_comments WHERE announcement_id = %s", (ann['id'],))
        ann['comment_count'] = cur.fetchone()['cnt'] or 0

        cur.execute("""
            SELECT c.comment, c.date_added,
                   COALESCE(u.username, 'Anonymous') AS commenter_name
            FROM announcement_comments c
            LEFT JOIN users u ON c.user_id = u.id
            WHERE c.announcement_id = %s
            ORDER BY c.date_added ASC
        """, (ann['id'],))
        ann['comments.html'] = cur.fetchall()

        ann['formatted_date'] = format_church(ann['created_at'], '%B %d, %Y') if ann['created_at'] else 'Unknown'

    # Summary counts
    cur.execute("SELECT COUNT(*) AS cnt FROM announcements_tgp")
    total_count = cur.fetchone()['cnt'] or 0
    cur.execute("SELECT COUNT(*) AS cnt FROM announcements_tgp WHERE is_active = 1")
    active_count = cur.fetchone()['cnt'] or 0
    cur.execute("SELECT COUNT(*) AS cnt FROM announcements_tgp WHERE visibility = 'public'")
    public_count = cur.fetchone()['cnt'] or 0

    # Members for email modal
    members = []
    if can_manage:
        cur.execute("""
            SELECT id, username AS name, email
            FROM users
            WHERE email IS NOT NULL AND email != ''
            ORDER BY username
        """)
        members = cur.fetchall()

    return render_template(
        'announcements_tgp/announcements_dash.html',
        announcements_list=announcements_list,
        total_count=total_count,
        active_count=active_count,
        public_count=public_count,
        members=members,
        is_logged_in=is_logged_in,
        can_manage=can_manage
    )


# ----------------------------------------------------------------------
# Single Announcement View – /announcements_tgp/<int:ann_id> (clean new page)
# ----------------------------------------------------------------------
@announcements_bp.route('/<int:ann_id>')
def view_announcement(ann_id):
    is_logged_in = 'user_id' in session
    user_id = session.get('user_id')
    role = session.get('user_role', '')

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT a.*,
               COALESCE(u.username, 'Unknown') AS creator_name
        FROM announcements_tgp a
        LEFT JOIN users u ON a.created_by = u.id
        WHERE a.id = %s
    """, (ann_id,))
    announcement = cur.fetchone()

    if not announcement:
        flash('Announcement not found.', 'error')
        return redirect(url_for('announcements_tgp.announcements_tgp'))

    # Visibility enforcement
    if announcement['visibility'] == 'private' and not is_logged_in:
        flash('This is a private announcement – login required.', 'error')
        return redirect(url_for('announcements_tgp.announcements_tgp'))

    # Server-side censorship
    announcement['title'] = censor_text(announcement['title'])
    announcement['content'] = censor_text(announcement['content'] or '')

    # Load comments.html
    cur.execute("""
        SELECT c.comment, c.date_added,
               COALESCE(u.username, 'Anonymous') AS commenter_name
        FROM announcement_comments c
        LEFT JOIN users u ON c.user_id = u.id
        WHERE c.announcement_id = %s
        ORDER BY c.date_added ASC
    """, (ann_id,))
    comments = cur.fetchall()
    for c in comments:
        c['comment'] = censor_text(c['comment'])

    if user_id:
        log_change(user_id, 'view_announcement', target_id=ann_id,
                   change_details=f"Viewed announcement {ann_id}")

    return render_template('announcements_tgp/view_annoucements.html',
                           announcement=announcement,
                           comments=comments,
                           is_logged_in=is_logged_in)


# ----------------------------------------------------------------------
# Create Announcement
# ----------------------------------------------------------------------
@announcements_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required(REQUIRED_ROLES)
def create_announcement():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        visibility = request.form.get('visibility', 'private')
        is_active = 1 if 'is_active' in request.form else 0
        comments_enabled = 1 if 'comments_enabled' in request.form else 0

        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('announcements_tgp/create_announcement.html', form_data=request.form, can_manage=True)

        if contains_censored_word(title + ' ' + content):
            flash('Announcement contains a prohibited word or phrase.', 'error')
            return render_template('announcements_tgp/create_announcement.html', form_data=request.form, can_manage=True)

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("""
                INSERT INTO announcements_tgp
                (title, content, visibility, is_active, comments_enabled, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (title, content, visibility, is_active, comments_enabled, session['user_id']))
            db.commit()
            ann_id = cur.lastrowid
            log_change(session['user_id'], 'create_announcement', ann_id, title, 'Created announcement')
            flash('Announcement created successfully.', 'success')
        except Exception as e:
            db.rollback()
            flash('Failed to create announcement.', 'error')
            print(f"Create announcement error: {e}")

        return redirect(url_for('announcements_tgp.announcements_tgp'))

    return render_template('announcements_tgp/create_announcement.html', form_data=None, can_manage=True)


# ----------------------------------------------------------------------
# Edit Announcement
# ----------------------------------------------------------------------
@announcements_bp.route('/edit/<int:ann_id>', methods=['GET', 'POST'])
@login_required
@role_required(REQUIRED_ROLES)
def edit_announcement(ann_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM announcements_tgp WHERE id = %s", (ann_id,))
    announcement = cur.fetchone()
    if not announcement:
        flash('Announcement not found.', 'error')
        return redirect(url_for('announcements_tgp.announcements_tgp'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        visibility = request.form.get('visibility', 'private')
        is_active = 1 if 'is_active' in request.form else 0
        comments_enabled = 1 if 'comments_enabled' in request.form else 0

        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('announcements_tgp/edit_announcement.html', announcement=announcement, can_manage=True)

        if contains_censored_word(title + ' ' + content):
            flash('Announcement contains a prohibited word or phrase.', 'error')
            return render_template('announcements_tgp/edit_announcement.html', announcement=announcement, can_manage=True)

        try:
            cur.execute("""
                UPDATE announcements_tgp
                SET title = %s, content = %s, visibility = %s,
                    is_active = %s, comments_enabled = %s, updated_by = %s
                WHERE id = %s
            """, (title, content, visibility, is_active, comments_enabled, session['user_id'], ann_id))
            db.commit()
            log_change(session['user_id'], 'update_announcement', ann_id, title, 'Updated announcement')
            flash('Announcement updated successfully.', 'success')
        except Exception as e:
            db.rollback()
            flash('Failed to update announcement.', 'error')
            print(f"Edit announcement error: {e}")

        return redirect(url_for('announcements_tgp.announcements_tgp'))

    return render_template('announcements_tgp/edit_announcement.html', announcement=announcement, can_manage=True)


# ----------------------------------------------------------------------
# Delete Announcement
# ----------------------------------------------------------------------
@announcements_bp.route('/delete/<int:ann_id>', methods=['POST'])
@login_required
@role_required(REQUIRED_ROLES)
def delete_announcement(ann_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT title FROM announcements_tgp WHERE id = %s", (ann_id,))
    row = cur.fetchone()
    title = row['title'] if row else 'Unknown'

    try:
        cur.execute("DELETE FROM announcement_comments WHERE announcement_id = %s", (ann_id,))
        cur.execute("DELETE FROM announcements_tgp WHERE id = %s", (ann_id,))
        db.commit()
        log_change(session['user_id'], 'delete_announcement', ann_id, title, 'Deleted announcement')
        flash('Announcement deleted successfully.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to delete announcement.', 'error')
        print(f"Delete announcement error: {e}")

    return redirect(url_for('announcements_tgp.announcements_tgp'))


# ----------------------------------------------------------------------
# Add Comment
# ----------------------------------------------------------------------
@announcements_bp.route('/comment/add/<int:ann_id>', methods=['POST'])
@login_required
def add_comment(ann_id):
    comment_text = request.form.get('comment', '').strip()
    if not comment_text:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('announcements_tgp.view_announcement', ann_id=ann_id))

    if contains_censored_word(comment_text):
        flash('Comment contains a prohibited word or phrase.', 'error')
        return redirect(url_for('announcements_tgp.view_announcement', ann_id=ann_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT title FROM announcements_tgp WHERE id = %s", (ann_id,))
    row = cur.fetchone()
    ann_title = row['title'] if row else 'Unknown'

    try:
        cur.execute("""
            INSERT INTO announcement_comments (announcement_id, user_id, comment)
            VALUES (%s, %s, %s)
        """, (ann_id, session['user_id'], comment_text))
        db.commit()
        log_change(session['user_id'], 'add_comment', ann_id, ann_title, 'Added comment')
        flash('Comment added.', 'success')
    except Exception as e:
        db.rollback()
        flash('Failed to add comment.', 'error')
        print(f"Add comment error: {e}")

    return redirect(url_for('announcements_tgp.view_announcement', ann_id=ann_id))


# ----------------------------------------------------------------------
# Email Announcement
# ----------------------------------------------------------------------
@announcements_bp.route('/email/<int:ann_id>', methods=['POST'])
@login_required
@role_required(REQUIRED_ROLES)
def email_announcement(ann_id):
    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()

    if not subject:
        flash('Subject is required.', 'error')
        return redirect(url_for('announcements_tgp.announcements_tgp'))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT title, content FROM announcements_tgp WHERE id = %s", (ann_id,))
    row = cur.fetchone()
    if not row:
        flash('Announcement not found.', 'error')
        return redirect(url_for('announcements_tgp.announcements_tgp'))

    body = f"{message}\n\n--- Announcement ---\nTitle: {row['title']}\n\n{row['content']}"

    if 'sendAll' in request.form:
        cur.execute("SELECT email FROM users WHERE email IS NOT NULL AND email != ''")
    else:
        member_ids = request.form.getlist('member_ids')
        if not member_ids:
            flash('No recipients selected.', 'error')
            return redirect(url_for('announcements_tgp.announcements_tgp'))
        placeholders = ','.join(['%s'] * len(member_ids))
        cur.execute(f"SELECT email FROM users WHERE id IN ({placeholders}) AND email IS NOT NULL AND email != ''",
                    [int(mid) for mid in member_ids])

    emails = [r['email'] for r in cur.fetchall()]

    if not emails:
        flash('No valid recipient emails found.', 'error')
        return redirect(url_for('announcements_tgp.announcements_tgp'))

    success_count = 0
    for email_addr in emails:
        try:
            send_email(email_addr, subject, body)
            success_count += 1
        except Exception as e:
            print(f"Email failed to {email_addr}: {e}")

    log_change(session['user_id'], 'email_announcement', ann_id, row['title'],
               f"Emailed to {success_count} recipients")

    flash(f'Announcement emailed to {success_count} members.', 'success')
    return redirect(url_for('announcements_tgp.announcements_tgp'))