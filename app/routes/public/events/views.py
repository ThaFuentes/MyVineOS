# MYVINECHURCH.ONLINE/app/routes/public/events/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/events/views.py
# File name: views.py
# Brief, detailed purpose: Public Events routes for unauthenticated guests only.
# - Made 100% identical to the working sermon section (same comment handling, same debug, same success flow).
# - Listing shows only upcoming public events with potluck signups.
# - Detail page supports potluck + full guest comments.html/replies (one-level).
# - Logged-in users are redirected to private events.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from . import events_bp
from .queries import get_public_events, get_public_event
from .forms import validate_potluck_signup_form
from .utils import censor_public_content

from app.models.db import get_db
from app.utils.helpers import censor_text, contains_censored_word
from app.utils.time_utils import format_church
from app.utils.comment_moderation import (
    public_comments_enabled, fetch_public_comments, insert_public_comment,
)


# ----------------------------------------------------------------------
# Public Events Listing (Guests Only)
# ----------------------------------------------------------------------
@events_bp.route('/')
def public_events():
    """Public events listing – upcoming public events only."""
#    print(" [PUBLIC EVENTS] Route /public/events/ hit (sub-blueprint)")

    if 'user_id' in session:
#        print(" [PUBLIC EVENTS] Logged-in user → redirecting to private events")
        return redirect(url_for('events.events'))

    events = get_public_events()
#    print(f" [PUBLIC EVENTS] Raw events returned from query: {len(events)} records")

    events = censor_public_content(events)

    for e in events:
        e['datetime'] = format_church(e.get('created_at')) if e.get('created_at') else 'Unknown'
        e['posted_by'] = e.get('creator_name', 'Anonymous')

        if e.get('potluck_enabled'):
            try:
                db = get_db()
                cur = db.cursor(pymysql.cursors.DictCursor)
                cur.execute("SELECT name, item, quantity, note FROM potluck_signups WHERE event_id = %s ORDER BY id ASC", (e['id'],))
                e['signups'] = cur.fetchall()
                cur.close()
            except Exception:
                e['signups'] = []

    return render_template('public/events/events.html', events=events)


# ----------------------------------------------------------------------
# Public Single Event Detail (Guests Only + Potluck + Comments)
# ----------------------------------------------------------------------
@events_bp.route('/<int:event_id>', methods=['GET', 'POST'])
def public_event_detail(event_id):
    """Public single event detail with potluck signups + guest comments.html/replies."""
    print(f" [PUBLIC EVENT DETAIL] Route /public/events/{event_id} hit")

    if 'user_id' in session and request.method == 'GET':
        print(" [PUBLIC EVENT DETAIL] Logged-in user → redirecting to private view")
        return redirect(url_for('events.view_event', event_id=event_id))

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    event = get_public_event(event_id)
    if not event:
        print(f" [PUBLIC EVENT DETAIL] Event {event_id} not found or not public")
        abort(404)

    # Censor content for public view
    event['event_name']   = censor_text(event.get('event_name', ''))
    event['location']     = censor_text(event.get('location', ''))
    event['description']  = censor_text(event.get('description', ''))

    signups = []
    if event.get('potluck_enabled'):
        try:
            cur.execute("SELECT name, item, quantity, note FROM potluck_signups WHERE event_id = %s ORDER BY id ASC", (event_id,))
            signups = cur.fetchall()
            signups = censor_public_content(signups)
        except Exception:
            pass

    viewer_ip = request.remote_addr
    viewer_uid = session.get('user_id')
    comments = fetch_public_comments('event', event_id, viewer_ip, viewer_uid)
    comments_enabled = public_comments_enabled()

    # Handle POST - potluck or guest comment/reply
    if request.method == 'POST':
        action = request.form.get('action')
        print(f" [PUBLIC EVENT DETAIL] POST action = {action}")

        if action == 'potluck' and event.get('potluck_enabled'):
            clean = validate_potluck_signup_form(request.form)
            if not clean:
                return redirect(url_for('public.public_events.public_event_detail', event_id=event_id))
            ip = request.remote_addr or 'unknown'
            try:
                cur.execute("""
                    INSERT INTO potluck_signups 
                    (event_id, name, item, quantity, note, ip)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (event_id, clean['name'], clean['item'], clean['quantity'], clean['note'], ip))
                db.commit()
                flash('Thank you for signing up!', 'success')
            except Exception:
                flash('Signup failed – please try again.', 'error')

        elif action in ('comment', 'reply'):
            if not comments_enabled:
                flash('Comments are temporarily disabled.', 'error')
            else:
                name = request.form.get('name', '').strip()
                comment_text = request.form.get('comment', '').strip()
                parent_id = request.form.get('parent_id') if action == 'reply' else None

                if not name or not comment_text:
                    flash('Name and comment are required.', 'error')
                elif contains_censored_word(name + ' ' + comment_text):
                    flash('Your comment contains prohibited content.', 'error')
                elif insert_public_comment(
                    'event', event_id, name, comment_text, parent_id,
                    ip=viewer_ip, user_id=viewer_uid,
                ):
                    flash('Comment posted successfully!', 'success')
                else:
                    flash('Failed to post comment.', 'error')

        return redirect(url_for('public.public_events.public_event_detail', event_id=event_id))

    return render_template('public/events/event_detail.html',
                           event=event,
                           signups=signups,
                           comments=comments,
                           comments_enabled=comments_enabled)


