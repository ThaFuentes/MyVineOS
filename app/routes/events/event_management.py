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

# All text fields that must be checked for censored words
TEXT_FIELDS = [
    'event_name', 'location', 'description', 'speaker_host', 'special_guests',
    'theme', 'agenda', 'registration_info', 'contact_info', 'childcare_availability',
    'accessibility', 'promotional_materials', 'announcements_reminders',
    'live_streaming_details', 'feedback_form', 'event_sponsor', 'event_coordinator',
    'volunteer_opportunities', 'donation_info', 'safety_protocols', 'follow_up',
    'event_objectives', 'social_media_hashtag', 'parking_info', 'dress_code',
    'food_beverages'
]

def register_management_routes(bp):
    @bp.route('/add', methods=['GET', 'POST'])
    @login_required
    @role_required(REQUIRED_ROLES)
    def add_event():
        if request.method == 'GET':
            return render_template('events/add_event.html')

        form = request.form

        # Censorship check on all text fields
        if any(contains_censored_word(form.get(field, '')) for field in TEXT_FIELDS):
            flash('Event contains prohibited content.', 'error')
            return render_template('events/add_event.html')

        data = {
            'event_name': form.get('event_name'),
            'event_date': form.get('event_date'),
            'event_time': form.get('event_time') or None,
            'visibility': form.get('visibility', 'private'),
            'potluck_enabled': 1 if 'potluck_enabled' in form else 0,
            'location': form.get('location') or None,
            'description': form.get('description') or None,
            'speaker_host': form.get('speaker_host') or None,
            'special_guests': form.get('special_guests') or None,
            'theme': form.get('theme') or None,
            'agenda': form.get('agenda') or None,
            'registration_info': form.get('registration_info') or None,
            'cost_fees': form.get('cost_fees') or None,
            'contact_info': form.get('contact_info') or None,
            'childcare_availability': form.get('childcare_availability') or None,
            'accessibility': form.get('accessibility') or None,
            'promotional_materials': form.get('promotional_materials') or None,
            'announcements_reminders': form.get('announcements_reminders') or None,
            'live_streaming_details': form.get('live_streaming_details') or None,
            'feedback_form': form.get('feedback_form') or None,
            'event_sponsor': form.get('event_sponsor') or None,
            'event_coordinator': form.get('event_coordinator') or None,
            'volunteer_opportunities': form.get('volunteer_opportunities') or None,
            'donation_info': form.get('donation_info') or None,
            'safety_protocols': form.get('safety_protocols') or None,
            'follow_up': form.get('follow_up') or None,
            'event_objectives': form.get('event_objectives') or None,
            'social_media_hashtag': form.get('social_media_hashtag') or None,
            'parking_info': form.get('parking_info') or None,
            'dress_code': form.get('dress_code') or None,
            'food_beverages': form.get('food_beverages') or None,
            'created_by': session['user_id'],
            'updated_by': session['user_id']
        }

        try:
            db = get_db()
            cur = db.cursor()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            cur.execute(f"INSERT INTO events ({columns}) VALUES ({placeholders})", list(data.values()))
            event_id = cur.lastrowid
            db.commit()

            log_change(session['user_id'], 'create_event', target_id=event_id,
                       change_details=f"Created event: {data['event_name']}")
            flash('Event created successfully.', 'success')
            return redirect(url_for('events.events'))
        except Exception as exc:
            db.rollback()
            flash('Failed to create event.', 'error')
            return render_template('events/add_event.html')

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
            return render_template('events/edit_event.html', event=event)

        form = request.form

        # Censorship check on all text fields
        if any(contains_censored_word(form.get(field, '')) for field in TEXT_FIELDS):
            flash('Event contains prohibited content.', 'error')
            return render_template('events/edit_event.html', event=event)

        data = {
            field: form.get(field) or None for field in TEXT_FIELDS
        }
        data.update({
            'event_date': form.get('event_date'),
            'event_time': form.get('event_time') or None,
            'visibility': form.get('visibility', 'private'),
            'potluck_enabled': 1 if 'potluck_enabled' in form else 0,
            'cost_fees': form.get('cost_fees') or None,
            'updated_by': session['user_id']
        })

        try:
            set_clause = ', '.join(f"{k} = %s" for k in data)
            values = list(data.values()) + [event_id]
            cur.execute(f"UPDATE events SET {set_clause} WHERE id = %s", values)
            db.commit()

            log_change(session['user_id'], 'update_event', target_id=event_id,
                       change_details=f"Updated event: {event['event_name']}")
            flash('Event updated successfully.', 'success')
        except Exception:
            db.rollback()
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

        event_name = row['event_name']

        try:
            cur = db.cursor()
            cur.execute("DELETE FROM potluck_signups WHERE event_id = %s", (event_id,))
            cur.execute("DELETE FROM events WHERE id = %s", (event_id,))
            db.commit()

            log_change(session['user_id'], 'delete_event', target_id=event_id,
                       change_details=f"Deleted event: {event_name}")
            flash('Event deleted successfully.', 'success')
        except Exception:
            db.rollback()
            flash('Failed to delete event.', 'error')

        return redirect(url_for('events.events'))