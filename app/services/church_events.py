"""Event create/edit/delete shared by the Events pages and Maya's API.

Pulled out of app/routes/events/event_management.py so the web form and the
bot call the exact same code (same fields, censorship check, change log).
"""
from __future__ import annotations

import pymysql

from app.models.db import get_db
from app.models.log import log_change
from app.utils.helpers import contains_censored_word

# All text fields that must be checked for censored words
TEXT_FIELDS = [
    'event_name', 'location', 'description', 'speaker_host', 'special_guests',
    'theme', 'agenda', 'registration_info', 'contact_info', 'childcare_availability',
    'accessibility', 'promotional_materials', 'announcements_reminders',
    'live_streaming_details', 'feedback_form', 'event_sponsor', 'event_coordinator',
    'volunteer_opportunities', 'donation_info', 'safety_protocols', 'follow_up',
    'event_objectives', 'social_media_hashtag', 'parking_info', 'dress_code',
    'food_beverages', 'payment_url', 'payment_note',
]


def payment_option_ids_from_form(form):
    ids = [str(v) for v in form.getlist('payment_option_ids') if str(v).isdigit()]
    return ','.join(ids) if ids else '0'


def has_censored(form) -> bool:
    return any(contains_censored_word(form.get(field, '') or '') for field in TEXT_FIELDS)


def get_event(event_id: int) -> dict | None:
    cur = get_db().cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM events WHERE id = %s", (int(event_id),))
    return cur.fetchone()


def _create_data(form, user_id: int) -> dict:
    data = {field: form.get(field) or None for field in TEXT_FIELDS}
    data.update({
        'event_name': form.get('event_name'),
        'event_date': form.get('event_date'),
        'event_time': form.get('event_time') or None,
        'visibility': form.get('visibility', 'private'),
        'potluck_enabled': 1 if 'potluck_enabled' in form else 0,
        'cost_fees': form.get('cost_fees') or None,
        'payment_required': 1 if form.get('payment_required') else 0,
        'payment_option_ids': payment_option_ids_from_form(form),
        'capacity': form.get('capacity') or None,
        'created_by': user_id,
        'updated_by': user_id,
    })
    return data


def _edit_data(form, user_id: int) -> dict:
    data = {field: form.get(field) or None for field in TEXT_FIELDS}
    data.update({
        'event_date': form.get('event_date'),
        'event_time': form.get('event_time') or None,
        'visibility': form.get('visibility', 'private'),
        'potluck_enabled': 1 if 'potluck_enabled' in form else 0,
        'cost_fees': form.get('cost_fees') or None,
        'payment_required': 1 if form.get('payment_required') else 0,
        'payment_url': form.get('payment_url') or None,
        'payment_note': form.get('payment_note') or None,
        'payment_option_ids': payment_option_ids_from_form(form),
        'capacity': form.get('capacity') or None,
        'updated_by': user_id,
    })
    return data


def create_event(form, user_id: int) -> tuple[int | None, str | None]:
    """(event_id, error). Same insert and change log as the Add event page."""
    if has_censored(form):
        return None, 'Event contains prohibited content.'
    if not (form.get('event_name') or '').strip() or not (form.get('event_date') or '').strip():
        return None, 'event_name and event_date are required.'
    data = _create_data(form, user_id)
    db = get_db()
    cur = db.cursor()
    try:
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        cur.execute(f"INSERT INTO events ({columns}) VALUES ({placeholders})", list(data.values()))
        event_id = cur.lastrowid
        db.commit()
    except Exception:
        db.rollback()
        return None, 'Failed to create event.'
    log_change(user_id, 'create_event', target_id=event_id, change_details=f"Created event: {data['event_name']}")
    return int(event_id), None


def update_event(event_id: int, form, user_id: int) -> tuple[bool, str | None, dict | None]:
    """(ok, error, old_row). Same update and change log as the Edit event page."""
    event = get_event(event_id)
    if not event:
        return False, 'Event not found.', None
    if has_censored(form):
        return False, 'Event contains prohibited content.', event
    data = _edit_data(form, user_id)
    db = get_db()
    cur = db.cursor()
    try:
        set_clause = ', '.join(f"{k} = %s" for k in data)
        cur.execute(f"UPDATE events SET {set_clause} WHERE id = %s", list(data.values()) + [int(event_id)])
        db.commit()
    except Exception:
        db.rollback()
        return False, 'Failed to update event.', event
    log_change(user_id, 'update_event', target_id=event_id, change_details=f"Updated event: {event['event_name']}")
    return True, None, event


def hard_delete_event(event_id: int, user_id: int) -> tuple[bool, str]:
    """Permanent delete (Admin/Owner page action). Maya needs the high-risk switch."""
    event = get_event(event_id)
    if not event:
        return False, 'Event not found.'
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM potluck_signups WHERE event_id = %s", (int(event_id),))
        cur.execute("DELETE FROM events WHERE id = %s", (int(event_id),))
        db.commit()
    except Exception:
        db.rollback()
        return False, 'Failed to delete event.'
    log_change(user_id, 'delete_event', target_id=event_id, change_details=f"Deleted event: {event['event_name']}")
    return True, f"Deleted event: {event['event_name']}"


def row_as_form(row: dict):
    """MultiDict of an event row, so a partial edit keeps every field it did not send."""
    from werkzeug.datastructures import MultiDict

    out = MultiDict()
    for key, val in (row or {}).items():
        if key in ('potluck_enabled', 'payment_required'):
            if val:
                out[key] = '1'
            continue
        if key == 'payment_option_ids':
            for part in str(val or '').split(','):
                if part.isdigit() and part != '0':
                    out.add('payment_option_ids', part)
            continue
        if val is not None:
            out[key] = str(val)
    return out
