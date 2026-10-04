# app/routes/events/event_management.py
# Full path: MyVineChurch/app/routes/events/event_management.py
# File name: event_management.py
# Brief, detailed purpose: Contains only the add, edit, and delete event routes.
# Restricted to Staff/Admin/Owner (add/edit) and Admin/Owner (delete).
# Full server-side censorship check on all text fields during create/update.
# Preserves every field, logs all actions, flashes feedback.
# Renders add_event.html (GET/POST) and edit_event.html (GET/POST).
# No other routes or logic - pure extraction from the original monolithic events.py.

from flask import render_template, request, redirect, url_for, flash, session
from app.utils.decorators import login_required, role_required
from app.utils.helpers import contains_censored_word
from app.models.db import get_db
from app.models.log import log_change
import pymysql

REQUIRED_ROLES = ['Staff', 'Admin', 'Owner']
ADMIN_OWNER_ONLY = ['Admin', 'Owner']

# Field logic lives in app/services/church_events.py (shared with Maya's API).
from app.services.church_events import TEXT_FIELDS  # noqa: E402,F401

def _giving_options():
    try:
        from app.utils.event_payments import list_giving_options
        return list_giving_options(enabled_only=True)
    except Exception:
        return []


def _payment_option_ids_from_form(form):
    ids = [str(v) for v in form.getlist('payment_option_ids') if str(v).isdigit()]
    return ','.join(ids) if ids else '0'


def register_management_routes(bp):
    @bp.route('/add', methods=['GET', 'POST'])
    @login_required
    @role_required(REQUIRED_ROLES)
    def add_event():
        if request.method == 'GET':
            return render_template('events/add_event.html', giving_options=_giving_options())

        from app.services.church_events import create_event

        event_id, err = create_event(request.form, session['user_id'])
        if err:
            flash(err if 'prohibited' in err else 'Failed to create event.', 'error')
            return render_template('events/add_event.html', giving_options=_giving_options())
        flash('Event created successfully.', 'success')
        return redirect(url_for('events.events'))

    @bp.route('/edit/<int:event_id>', methods=['GET', 'POST'])
    @login_required
    @role_required(REQUIRED_ROLES)
    def edit_event(event_id):
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = cur.fetchone()

        if not event:
            flash('Event not found.', 'error')
            return redirect(url_for('events.events'))

        if request.method == 'GET':
            return render_template('events/edit_event.html', event=event, giving_options=_giving_options())

        from app.services.church_events import update_event

        ok, err, _before = update_event(event_id, request.form, session['user_id'])
        if not ok and err and 'prohibited' in err:
            flash(err, 'error')
            return render_template('events/edit_event.html', event=event, giving_options=_giving_options())
        if ok:
            flash('Event updated successfully.', 'success')
        else:
            flash('Failed to update event.', 'error')

        return redirect(url_for('events.events'))

    @bp.route('/delete/<int:event_id>', methods=['POST'])
    @login_required
    @role_required(ADMIN_OWNER_ONLY)
    def delete_event(event_id):
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)

        cur.execute("SELECT event_name FROM events WHERE id = %s", (event_id,))
        row = cur.fetchone()
        if not row:
            flash('Event not found.', 'error')
            return redirect(url_for('events.events'))

        from app.services.church_events import hard_delete_event

        ok, _msg = hard_delete_event(event_id, session['user_id'])
        if ok:
            flash('Event deleted successfully.', 'success')
        else:
            flash('Failed to delete event.', 'error')

        return redirect(url_for('events.events'))
