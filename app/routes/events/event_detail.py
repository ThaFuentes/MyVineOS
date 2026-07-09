# app/routes/events/event_detail.py
# Full path: MyVineChurch/app/routes/events/event_detail.py
# File name: event_detail.py
# Brief, detailed purpose: Public single event detail page with full comment support.
# - Guests (non-registered) can view events, add to potluck, and post comments.html.
# - Logged-in users can post, edit, and delete their own comments.html.
# - Admins / users with 'moderate_events' permission can edit/delete any comment.
# - Strong anti-spam: censored word check + rate limiting for guests.
# - All original potluck behavior preserved exactly.

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change
from app.utils.time_utils import format_church
import pymysql

def register_detail_routes(bp):
    @bp.route('/view/<int:event_id>', methods=['GET', 'POST'])
    def view_event(event_id):
        """Public event detail – guests and members can comment."""
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Fetch event
        cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = cur.fetchone()
        if not event:
            flash('Event not found.', 'error')
            return redirect(url_for('events.events'))

        is_logged_in = 'user_id' in session
        user_id = session.get('user_id')

        # Potluck signups (kept exactly as your original)
        signups = []
        if event.get('potluck_enabled'):
            try:
                cur.execute("""
                    SELECT *, created_at AS created_at_utc
                    FROM potluck_signups
                    WHERE event_id = %s
                    ORDER BY created_at DESC
                """, (event_id,))
                signups = cur.fetchall()
                for s in signups:
                    s['created_at_nice'] = format_church(s['created_at_utc'])
            except Exception:
                pass  # Old DB without table – ignore

        # ---------- POST: Potluck contribution (your original logic kept 100%) ----------
        if request.method == 'POST' and request.form.get('action') == 'potluck':
            if not event.get('potluck_enabled'):
                flash('Potluck is not enabled for this event.', 'error')
                return redirect(url_for('events.view_event', event_id=event_id))

            # Rate limiting for guests
            if not is_logged_in:
                if session.get('potluck_submissions', 0) >= 3:
                    flash('You have submitted too many contributions recently. Please wait a few minutes.', 'error')
                    return redirect(url_for('events.view_event', event_id=event_id))
                session['potluck_submissions'] = session.get('potluck_submissions', 0) + 1

            if is_logged_in:
                cur.execute("SELECT first_name, last_name FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()
                name = f"{user['first_name']} {user['last_name']}".strip()
            else:
                name = request.form.get('name', '').strip() or 'Guest'

            item = request.form.get('item', '').strip()
            quantity = request.form.get('quantity', '').strip()
            note = request.form.get('note', '').strip()

            if not item:
                flash('Item description is required.', 'error')
                return redirect(url_for('events.view_event', event_id=event_id))

            if any(contains_censored_word(field) for field in [name, item, quantity or '', note or '']):
                flash('Contribution contains a prohibited word or phrase.', 'error')
                return redirect(url_for('events.view_event', event_id=event_id))

            try:
                cur = db.cursor()
                ip = request.remote_addr or 'unknown'
                cur.execute("""
                    INSERT INTO potluck_signups
                    (event_id, name, item, quantity, note, ip)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (event_id, name, item, quantity or None, note or None, ip))
                db.commit()

                log_change(user_id or 0, 'potluck_contribution',
                           target_id=event_id,
                           change_details=f"Contributed {quantity or ''} {item}")

                flash('Thank you for your potluck contribution!', 'success')
            except Exception:
                db.rollback()
                flash('Failed to record contribution.', 'error')

            return redirect(url_for('events.view_event', event_id=event_id))

        # ---------- POST: New Comment ----------
        if request.method == 'POST' and request.form.get('action') == 'comment':
            comment_text = request.form.get('comment', '').strip()
            if not comment_text:
                flash('Comment cannot be empty.', 'error')
                return redirect(url_for('events.view_event', event_id=event_id))

            if contains_censored_word(comment_text):
                flash('Comment contains a prohibited word or phrase.', 'error')
                return redirect(url_for('events.view_event', event_id=event_id))

            # Rate limiting for guests
            if not is_logged_in:
                if session.get('comment_submissions', 0) >= 5:
                    flash('You have posted too many comments.html recently. Please wait a few minutes.', 'error')
                    return redirect(url_for('events.view_event', event_id=event_id))
                session['comment_submissions'] = session.get('comment_submissions', 0) + 1

            name = request.form.get('name', '').strip() or 'Guest'
            if is_logged_in:
                cur.execute("SELECT first_name, last_name FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()
                name = f"{user['first_name']} {user['last_name']}".strip()

            try:
                cur = db.cursor()
                ip = request.remote_addr or 'unknown'
                cur.execute("""
                    INSERT INTO event_comments (event_id, name, comment, ip, user_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (event_id, name, comment_text, ip, user_id if is_logged_in else None))
                db.commit()

                log_change(user_id or 0, 'event_comment',
                           target_id=event_id,
                           change_details=f"Posted comment on event {event_id}")

                flash('Comment posted!', 'success')
            except Exception:
                db.rollback()
                flash('Failed to post comment.', 'error')

            return redirect(url_for('events.view_event', event_id=event_id))

        # Fetch comments.html for display
        cur.execute("""
            SELECT *, comment AS comment_text, created_at AS created_at_utc
            FROM event_comments
            WHERE event_id = %s
            ORDER BY created_at DESC
        """, (event_id,))
        comments = cur.fetchall()
        for c in comments:
            c['created_at_nice'] = format_church(c['created_at_utc'])

        # Render (public template for guests, private for members)
        template = 'public/events/event_detail.html' if not is_logged_in else 'events/view_event.html'

        return render_template(
            template,
            event=event,
            signups=signups,
            comments=comments,
            is_logged_in=is_logged_in
        )

    # ==================================================================
    # NEW: DELETE COMMENT ROUTE
    # ==================================================================
    @bp.route('/view/<int:event_id>/delete_comment/<int:comment_id>', methods=['POST'])
    def delete_comment(event_id, comment_id):
        """Delete a comment – owner or moderate_events permission only."""
        if 'user_id' not in session:
            flash('You must be logged in to delete comments.html.', 'error')
            return redirect(url_for('events.view_event', event_id=event_id))

        user_id = session['user_id']
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Check ownership or permission
        cur.execute("SELECT user_id FROM event_comments WHERE id = %s", (comment_id,))
        comment = cur.fetchone()

        if not comment or (comment['user_id'] != user_id and not session.get('user_has_permission', lambda p: False)('moderate_events')):
            flash('You do not have permission to delete this comment.', 'error')
            return redirect(url_for('events.view_event', event_id=event_id))

        try:
            cur = db.cursor()
            cur.execute("DELETE FROM event_comments WHERE id = %s", (comment_id,))
            db.commit()
            log_change(user_id, 'delete', target_id=comment_id, change_details=f'Deleted comment on event {event_id}')
            flash('Comment deleted.', 'success')
        except Exception:
            db.rollback()
            flash('Failed to delete comment.', 'error')

        return redirect(url_for('events.view_event', event_id=event_id))

    # ==================================================================
    # NEW: EDIT COMMENT ROUTE
    # ==================================================================
    @bp.route('/view/<int:event_id>/edit_comment/<int:comment_id>', methods=['POST'])
    def edit_comment(event_id, comment_id):
        """Edit a comment – owner or moderate_events permission only."""
        if 'user_id' not in session:
            flash('You must be logged in to edit comments.html.', 'error')
            return redirect(url_for('events.view_event', event_id=event_id))

        user_id = session['user_id']
        new_text = request.form.get('comment_text', '').strip()

        if not new_text:
            flash('Comment cannot be empty.', 'error')
            return redirect(url_for('events.view_event', event_id=event_id))

        if contains_censored_word(new_text):
            flash('Comment contains a prohibited word or phrase.', 'error')
            return redirect(url_for('events.view_event', event_id=event_id))

        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        # Check ownership or permission
        cur.execute("SELECT user_id FROM event_comments WHERE id = %s", (comment_id,))
        comment = cur.fetchone()

        if not comment or (comment['user_id'] != user_id and not session.get('user_has_permission', lambda p: False)('moderate_events')):
            flash('You do not have permission to edit this comment.', 'error')
            return redirect(url_for('events.view_event', event_id=event_id))

        try:
            cur = db.cursor()
            cur.execute("""
                UPDATE event_comments 
                SET comment = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = %s
            """, (new_text, comment_id))
            db.commit()
            log_change(user_id, 'update', target_id=comment_id, change_details=f'Edited comment on event {event_id}')
            flash('Comment updated.', 'success')
        except Exception:
            db.rollback()
            flash('Failed to update comment.', 'error')

        return redirect(url_for('events.view_event', event_id=event_id))