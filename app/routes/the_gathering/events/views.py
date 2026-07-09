# MYVINECHURCH.ONLINE/app/routes/the_gathering/events/views.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/events/views.py
# File name: views.py
# Brief, detailed purpose: All event routes for the Gathering Place Manager.
# - Dedicated sub-blueprint routes: listing, create/edit, view, delete, potluck management, comment moderation.
# - Uses events/forms.py, queries.py, and utils.py for clean separation.
# - Protected by the exact same session + DB role check pattern used everywhere else.
# - All url_for calls use the correct nested blueprint: 'the_gathering.events.*'
# - 100% rebuilt entire file — only this script was touched.

from flask import render_template, abort, request, flash, redirect, url_for, session
import pymysql

from ..permissions import gathering_place_required
from . import events_bp
from .queries import get_all_events, get_event, get_event_potluck_signups, get_event_comments
from .forms import validate_event_form, validate_potluck_edit_form, validate_search_filter
from app.utils.comment_moderation import handle_manager_comments_post
from .utils import censor_for_manager

from app.models.db import get_db
from app.models.log import log_change
from app.utils.helpers import censor_text


# ----------------------------------------------------------------------
# Events Listing / Dashboard
# ----------------------------------------------------------------------
@events_bp.route('/')
@gathering_place_required
def events_dashboard():
    """Main events management page with search + filters."""
    clean = validate_search_filter(request.args)
    filter_type = clean.get('filter', 'all')
    search = clean.get('search')

    events = get_all_events(filter_type=filter_type, search_query=search)
    events = censor_for_manager(events)

    return render_template('the_gathering/events/events_dashboard.html',
                           events=events,
                           filter_type=filter_type,
                           search=search or '',
                           page_title="Events Manager")


# ----------------------------------------------------------------------
# Create / Edit Event
# ----------------------------------------------------------------------
@events_bp.route('/new', methods=['GET', 'POST'])
@events_bp.route('/<int:event_id>/edit', methods=['GET', 'POST'])
@gathering_place_required
def edit_event(event_id=None):
    """Create new or edit existing event."""
    if request.method == 'POST':
        clean = validate_event_form(request.form)
        if not clean:
            return redirect(url_for('the_gathering.events.edit_event', event_id=event_id))

        db = get_db()
        cur = db.cursor()

        try:
            if event_id:  # UPDATE
                cur.execute("""
                    UPDATE events 
                    SET event_name=%s, event_date=%s, event_time=%s, location=%s,
                        description=%s, visibility=%s, potluck_enabled=%s,
                        updated_by=%s, updated_at=NOW()
                    WHERE id = %s
                """, (clean['event_name'], clean['event_date'], clean['event_time'],
                      clean['location'], clean['description'], clean['visibility'],
                      int(clean['potluck_enabled']), session['user_id'], event_id))
                flash('Event updated successfully.', 'success')
            else:  # INSERT
                cur.execute("""
                    INSERT INTO events 
                    (event_name, event_date, event_time, location, description,
                     visibility, potluck_enabled, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (clean['event_name'], clean['event_date'], clean['event_time'],
                      clean['location'], clean['description'], clean['visibility'],
                      int(clean['potluck_enabled']), session['user_id'], session['user_id']))
                flash('Event created successfully.', 'success')
            db.commit()
        except Exception:
            db.rollback()
            flash('Failed to save event.', 'error')

        return redirect(url_for('the_gathering.events.events_dashboard'))

    # GET - load existing or blank form
    event = get_event(event_id) if event_id else None
    return render_template('the_gathering/events/edit.html',
                           event=event,
                           page_title="Edit Event" if event_id else "Create New Event")


# ----------------------------------------------------------------------
# View Single Event
# ----------------------------------------------------------------------
@events_bp.route('/<int:event_id>/view')
@gathering_place_required
def view_event(event_id):
    """Read-only view of a single event."""
    event = get_event(event_id)
    if not event:
        abort(404)

    return render_template('the_gathering/events/view.html',
                           event=event,
                           comment_count=event.get('comment_count', 0),
                           page_title="View Event")


# ----------------------------------------------------------------------
# Delete Event
# ----------------------------------------------------------------------
@events_bp.route('/<int:event_id>/delete', methods=['POST'])
@gathering_place_required
def delete_event(event_id):
    """Delete event (with confirmation in template)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
        db.commit()
        flash('Event deleted permanently.', 'success')
    except Exception:
        flash('Failed to delete event.', 'error')
    return redirect(url_for('the_gathering.events.events_dashboard'))


# ----------------------------------------------------------------------
# Potluck Management for an Event
# ----------------------------------------------------------------------
@events_bp.route('/<int:event_id>/potluck', methods=['GET', 'POST'])
@gathering_place_required
def event_potluck(event_id):
    """Manage potluck contributions for a specific event."""
    event = get_event(event_id)
    if not event:
        abort(404)

    signups = get_event_potluck_signups(event_id)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_potluck':
            clean = validate_potluck_edit_form(request.form)
            if clean:
                db = get_db()
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO potluck_signups (event_id, name, item, quantity, note, ip)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (event_id, clean['name'], clean['item'], clean['quantity'], clean['note'], request.remote_addr))
                db.commit()
                flash('Potluck contribution added.', 'success')
        elif action == 'edit_potluck':
            clean = validate_potluck_edit_form(request.form)
            if clean:
                db = get_db()
                cur = db.cursor()
                cur.execute("""
                    UPDATE potluck_signups 
                    SET name=%s, item=%s, quantity=%s, note=%s
                    WHERE id = %s
                """, (clean['name'], clean['item'], clean['quantity'], clean['note'], request.form.get('signup_id')))
                db.commit()
                flash('Potluck contribution updated.', 'success')
        elif action == 'delete_potluck':
            db = get_db()
            cur = db.cursor()
            cur.execute("DELETE FROM potluck_signups WHERE id = %s", (request.form.get('signup_id'),))
            db.commit()
            flash('Potluck contribution deleted.', 'success')
        elif action == 'toggle_potluck':
            db = get_db()
            cur = db.cursor()
            enabled = 1 if request.form.get('enable') == '1' else 0
            cur.execute(
                "UPDATE events SET potluck_enabled = %s, updated_by = %s, updated_at = NOW() WHERE id = %s",
                (enabled, session['user_id'], event_id),
            )
            db.commit()
            log_change(
                session['user_id'], 'update_potluck_setting', event_id, event['event_name'],
                f"Potluck {'enabled' if enabled else 'disabled'} on public event page",
            )
            if enabled:
                flash('Potluck signups are now enabled on the public event page.', 'success')
            else:
                flash('Potluck signups hidden on the public site. Existing contributions are kept here for your records.', 'success')

        return redirect(url_for('the_gathering.events.event_potluck', event_id=event_id))

    return render_template('the_gathering/events/potluck.html',
                           event_id=event_id,
                           event_name=event['event_name'],
                           event=event,
                           signups=signups)


# ----------------------------------------------------------------------
# Comment Moderation for an Event
# ----------------------------------------------------------------------
@events_bp.route('/<int:event_id>/comments.html', methods=['GET', 'POST'])
@gathering_place_required
def event_comments(event_id):
    """Moderate comments on a specific event."""
    event = get_event(event_id)
    if not event:
        abort(404)

    search = request.args.get('search', '').strip() or None
    status_filter = request.args.get('filter', 'all')

    if request.method == 'POST':
        if handle_manager_comments_post('event', event_id, session['user_id'], request.form):
            return redirect(url_for('the_gathering.events.event_comments', event_id=event_id,
                                    search=search or '', filter=status_filter))

    comments = get_event_comments(event_id, search=search, status_filter=status_filter)

    return render_template('the_gathering/partials/comments_moderation.html',
                           parent_id=event_id,
                           parent_title=event['event_name'],
                           section_label='Event Comments',
                           comments_url=url_for('the_gathering.events.event_comments', event_id=event_id),
                           item_view_url=url_for('the_gathering.events.view_event', event_id=event_id),
                           public_url=url_for('public.public_events.public_event_detail', event_id=event_id),
                           comments=comments,
                           search=search or '',
                           filter=status_filter)


# print(" MYVINECHURCH.ONLINE the_gathering/events/views.py loaded successfully (full dedicated routes for events ready)")