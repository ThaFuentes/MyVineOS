# Unified compose dispatcher — reuses existing create validators/inserts.

from __future__ import annotations

from flask import flash, session, url_for, request

from app.models.log import log_change
from app.utils.community_participation import can_create_community_content
from app.utils.helpers import contains_censored_word
from app.models.db import get_db


COMPOSE_TYPES = (
    ('prayer', 'Prayer', 'prayers'),
    ('announcement', 'Announcement', 'announcements'),
    ('event', 'Event', 'events'),
    ('prophecy', 'Prophecy', 'prophecies'),
    ('dream', 'Dream', 'dreams'),
    ('sermon', 'Sermon', 'sermons'),
)


def available_compose_types():
    from app.models.module_toggles import get_module_toggles, is_module_enabled

    toggles = get_module_toggles()
    out = []
    for key, label, area in COMPOSE_TYPES:
        if key in ('dream', 'prophecy') and not is_module_enabled(
            'dreams' if key == 'dream' else 'prophecies', toggles
        ):
            continue
        if can_create_community_content(area):
            out.append({'key': key, 'label': label, 'area': area})
    return out


def _visibility(form, default='public'):
    vis = (form.get('visibility') or default).strip()
    if vis not in ('public', 'private', 'personal'):
        return default
    return vis


def create_from_compose(form):
    """
    Create one community item from the composer.
    Returns (ok, redirect_url).
    """
    kind = (form.get('compose_type') or '').strip()
    allowed = {item['key'] for item in available_compose_types()}
    if kind not in allowed:
        flash('You cannot post that type right now.', 'error')
        return False, None

    if kind == 'prayer':
        from app.routes.prayers.forms import validate_add_prayer_form
        from app.routes.prayers.queries import create_prayer

        clean = validate_add_prayer_form(form, is_logged_in=bool(session.get('user_id')))
        if not clean:
            return False, None
        prayer_id = create_prayer(
            clean['title'],
            clean['description'],
            clean['visibility'],
            session.get('user_id'),
            clean.get('contributor_name') or session.get('username') or 'Member',
            request.remote_addr,
            status='approved',
        )
        log_change(session.get('user_id'), 'create_prayer', target_id=prayer_id,
                   change_details=f"Composed prayer: {clean['title']}")
        flash('Prayer posted.', 'success')
        return True, url_for('prayers.view_prayer', prayer_id=prayer_id)

    if kind == 'announcement':
        from app.routes.announcements.queries import create_announcement

        title = (form.get('title') or '').strip()
        content = (form.get('body') or form.get('description') or '').strip()
        if not title or not content:
            flash('Title and message are required.', 'error')
            return False, None
        if contains_censored_word(f'{title} {content}'):
            flash('Content contains a prohibited word or phrase.', 'error')
            return False, None
        ann_id = create_announcement(
            title, content, _visibility(form, 'public'), 1, 1, session.get('user_id')
        )
        log_change(session.get('user_id'), 'create_announcement', target_id=ann_id,
                   change_details=f"Composed announcement: {title}")
        flash('Announcement posted.', 'success')
        return True, url_for('announcements.view_announcement', ann_id=ann_id)

    if kind == 'prophecy':
        title = (form.get('title') or '').strip()
        description = (form.get('body') or form.get('description') or '').strip()
        if not title or not description:
            flash('Title and description are required.', 'error')
            return False, None
        if contains_censored_word(f'{title} {description}'):
            flash('Content contains a prohibited word or phrase.', 'error')
            return False, None
        db = get_db()
        cur = db.cursor()
        cur.execute(
            """
            INSERT INTO prophecies (title, description, visibility, user_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (title, description, _visibility(form, 'private'), session.get('user_id')),
        )
        db.commit()
        prophecy_id = cur.lastrowid
        log_change(session.get('user_id'), 'create_prophecy', target_id=prophecy_id,
                   change_details=f"Composed prophecy: {title}")
        flash('Prophecy posted.', 'success')
        return True, url_for('prophecies.view_prophecy', prophecy_id=prophecy_id)

    if kind == 'dream':
        from app.routes.dreams.forms import validate_submit_dream_form
        from app.routes.dreams.queries import create_dream

        clean = validate_submit_dream_form(form)
        if not clean:
            return False, None
        dream_id = create_dream(session['user_id'], **clean)
        log_change(session.get('user_id'), 'create_dream', target_id=dream_id,
                   change_details=f"Composed dream: {clean['title']}")
        flash('Dream posted.', 'success')
        return True, url_for('dreams.view_dream', dream_id=dream_id)

    if kind == 'event':
        name = (form.get('event_name') or form.get('title') or '').strip()
        date = (form.get('event_date') or '').strip()
        if not name or not date:
            flash('Event name and date are required.', 'error')
            return False, None
        if contains_censored_word(name + ' ' + (form.get('description') or '')):
            flash('Event contains a prohibited word or phrase.', 'error')
            return False, None
        fee = form.get('cost_fees') or None
        pay_required = 1 if form.get('payment_required') or fee else 0
        db = get_db()
        cur = db.cursor()
        values = (
            name,
            date,
            (form.get('event_time') or None),
            'public' if form.get('visibility') == 'public' else 'private',
            (form.get('location') or None),
            (form.get('description') or None),
            fee,
            pay_required,
            (form.get('payment_url') or None),
            (form.get('payment_note') or None),
            session.get('user_id'),
            session.get('user_id'),
        )
        try:
            cur.execute(
                """
                INSERT INTO events
                    (event_name, event_date, event_time, visibility, location, description,
                     cost_fees, payment_required, payment_url, payment_note, created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                values,
            )
        except Exception:
            db.rollback()
            cur.execute(
                """
                INSERT INTO events
                    (event_name, event_date, event_time, visibility, location, description,
                     cost_fees, created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                values[:7] + values[-2:],
            )
        db.commit()
        event_id = cur.lastrowid
        log_change(session.get('user_id'), 'create_event', target_id=event_id,
                   change_details=f"Composed event: {name}")
        flash('Event posted.', 'success')
        return True, url_for('events.view_event', event_id=event_id)

    if kind == 'sermon':
        flash('Sermons need the full upload page so you can attach audio or a manuscript.', 'info')
        return False, url_for('sermons.upload_sermon')

    flash('Unknown post type.', 'error')
    return False, None
