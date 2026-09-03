# Unified compose dispatcher — reuses existing create validators/inserts.

from __future__ import annotations

from flask import flash, session, url_for, request

from app.models.log import log_change
from app.utils.community_participation import can_create_community_content
from app.utils.helpers import contains_censored_word
from app.models.db import get_db


COMPOSE_TYPES = (
    ('post', 'Post', 'prayers'),
    ('quote', 'Quote', 'prayers'),
    ('verse', 'Verse', 'prayers'),
    ('prayer', 'Prayer', 'prayers'),
    ('announcement', 'Announcement', 'announcements'),
    ('event', 'Event', 'events'),
    ('prophecy', 'Prophecy', 'prophecies'),
    ('dream', 'Dream', 'dreams'),
    ('sermon', 'Sermon', 'sermons'),
    ('book', 'Book', 'prayers'),
)


def available_compose_types():
    try:
        from app.models.module_toggles import get_module_toggles, is_module_enabled

        toggles = get_module_toggles()
        out = []
        for key, label, area in COMPOSE_TYPES:
            if key in ('dream', 'prophecy') and not is_module_enabled(
                'dreams' if key == 'dream' else 'prophecies', toggles
            ):
                continue
            if key in ('post', 'quote', 'verse', 'book', 'sermon') or can_create_community_content(area):
                out.append({'key': key, 'label': label, 'area': area})
        return out
    except Exception as exc:
        print(f"available_compose_types: {exc}")
        return []


def _visibility(form, default='public'):
    vis = (form.get('visibility') or default).strip()
    if vis not in ('public', 'private', 'personal'):
        return default
    return vis


def _finish(kind, content_id, form, dest):
    """Stamp posting voice and send them to the matching page."""
    from app.models import church_community as cc

    voice = cc.resolve_compose_voice(form.get('posted_as'))
    cc.record_posting(
        kind, content_id, voice['posted_as'], voice.get('campus_id') or 0, session.get('user_id'),
    )
    try:
        session['compose_voice'] = voice['key']
    except Exception:
        pass
    nxt = (form.get('next') or dest or '').strip()
    if nxt.startswith('/') and not nxt.startswith('//'):
        dest = cc.landing_for_voice(voice, nxt) or dest
    else:
        dest = cc.landing_for_voice(voice, dest or '/')
    if voice['posted_as'] == 'church':
        flash(f"Posted as {voice.get('label') or 'the church'}.", 'success')
    elif voice['posted_as'] == 'campus':
        flash(f"Posted on the {voice.get('label') or 'branch'} page.", 'success')
    else:
        flash('Posted on your page.', 'success')
    return True, dest


def create_from_compose(form, files=None):
    """
    Create one community item from the composer.
    Returns (ok, redirect_url).
    """
    files = files or {}
    kind = (form.get('compose_type') or '').strip()
    allowed = {item['key'] for item in available_compose_types()}
    if kind not in allowed:
        flash('You cannot post that type right now.', 'error')
        return False, None

    if kind == 'prayer':
        from app.routes.prayers.forms import validate_add_prayer_form
        from app.routes.prayers.queries import create_prayer

        from werkzeug.datastructures import MultiDict
        prayer_form = MultiDict(form)
        if not (prayer_form.get('description') or '').strip() and (prayer_form.get('body') or '').strip():
            prayer_form['description'] = prayer_form.get('body')
        clean = validate_add_prayer_form(prayer_form, is_logged_in=bool(session.get('user_id')))
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
        return _finish('prayer', prayer_id, form, url_for('prayers.view_prayer', prayer_id=prayer_id))

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
        return _finish('announcement', ann_id, form, url_for('announcements.view_announcement', ann_id=ann_id))

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
        return _finish('prophecy', prophecy_id, form, url_for('prophecies.view_prophecy', prophecy_id=prophecy_id))

    if kind == 'dream':
        from app.routes.dreams.forms import validate_submit_dream_form
        from app.routes.dreams.queries import create_dream

        clean = validate_submit_dream_form(form)
        if not clean:
            return False, None
        dream_id = create_dream(session['user_id'], **clean)
        log_change(session.get('user_id'), 'create_dream', target_id=dream_id,
                   change_details=f"Composed dream: {clean['title']}")
        return _finish('dream', dream_id, form, url_for('dreams.view_dream', dream_id=dream_id))

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
        return _finish('event', event_id, form, url_for('events.view_event', event_id=event_id))

    if kind == 'sermon':
        from app.routes.sermons.queries import create_sermon
        from app.utils.appearance import sanitize_public_href

        title = (form.get('title') or '').strip()
        details = (form.get('body') or form.get('description') or form.get('details') or '').strip()
        link = sanitize_public_href(form.get('external_link') or form.get('url') or '')
        vis = _visibility(form, 'public')
        if not title:
            flash('Title is required.', 'error')
            return False, None
        if contains_censored_word(f'{title} {details}'):
            flash('Content contains a prohibited word or phrase.', 'error')
            return False, None
        if not link and not details:
            flash('Add a link, text, or use the full upload page for a file.', 'error')
            return False, url_for('sermons.upload_sermon')
        sermon_id = create_sermon(
            title, None, details or None, None, link or None, vis, session.get('user_id'),
        )
        log_change(session.get('user_id'), 'create_sermon', target_id=sermon_id,
                   change_details=f"Composed sermon: {title}")
        return _finish('sermon', sermon_id, form, url_for('sermons.view_sermon', sermon_id=sermon_id))

    if kind in ('post', 'book', 'quote', 'verse'):
        from app.models import social as social_model

        title = (form.get('title') or '').strip()
        body = (form.get('body') or form.get('description') or '').strip()
        url = form.get('url') or form.get('external_link') or ''
        vis = _visibility(form, 'public')
        image_path = None
        upload = None
        if hasattr(files, 'get'):
            upload = files.get('photo') or files.get('image')
        if upload and getattr(upload, 'filename', None):
            image_path = social_model.save_identity_file(upload, f"p{session['user_id']}")
            if image_path and kind == 'post' and not body:
                kind = 'image'
        post_id = social_model.create_post(
            session['user_id'], kind, title, body, url, vis, image_path=image_path,
            allow_comments=form.get('allow_comments') != '0',
            allow_share=form.get('allow_share') != '0',
        )
        if not post_id:
            flash('Write something, add a photo, or drop the banned words.', 'error')
            return False, None
        from app.models import church_community as cc
        voice = cc.resolve_compose_voice(form.get('posted_as'))
        if kind == 'book':
            if voice['posted_as'] == 'church':
                social_model.add_link('church', 0, 'book', title, url, body, session['user_id'])
            elif voice['posted_as'] == 'campus':
                social_model.add_link('campus', voice['campus_id'], 'book', title, url, body, session['user_id'])
            else:
                social_model.add_link(
                    'member', session['user_id'], 'book', title, url, body, session['user_id'],
                )
        log_change(session.get('user_id'), 'create_community_post', target_id=post_id,
                   change_details=f"Composed {kind}: {title}")
        user = session.get('username')
        fallback = url_for('church.member_page', username=user) if user else url_for('church.church_home')
        return _finish(kind, post_id, form, fallback)

    flash('Unknown post type.', 'error')
    return False, None
