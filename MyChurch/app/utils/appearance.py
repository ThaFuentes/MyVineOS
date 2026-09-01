# Welcome / login hero images, featured spots, and church-facing copy.

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

from flask import current_app, url_for
from werkzeug.utils import secure_filename

from app.models.db import get_db
from app.utils.html_sanitize import sanitize_plain_text
import pymysql

ALLOWED_HERO_EXT = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
HERO_SUBDIR = os.path.join('uploads', 'heroes')
FEATURE_SUBDIR = os.path.join('uploads', 'welcome_features')
MAX_HEROES_PER_SURFACE = 8
MAX_WELCOME_FEATURES = 8


def hero_upload_dir():
    static_root = current_app.static_folder
    path = os.path.join(static_root, HERO_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def feature_upload_dir():
    static_root = current_app.static_folder
    path = os.path.join(static_root, FEATURE_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def safe_url_for(endpoint, fallback='', **kwargs):
    """Build a URL without raising. Missing endpoints must never break a page."""
    try:
        return url_for(endpoint, **kwargs)
    except Exception:
        return fallback or ''


def hero_url(filename):
    if not filename:
        return ''
    return safe_url_for('static', filename=f'{HERO_SUBDIR}/{filename}')


def feature_url(filename):
    if not filename:
        return ''
    return safe_url_for('static', filename=f'{FEATURE_SUBDIR}/{filename}')


def allowed_hero_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_HERO_EXT


def sanitize_public_href(value):
    raw = sanitize_plain_text(value or '')
    if not raw:
        return ''
    if raw.startswith('/') and not raw.startswith('//'):
        return raw[:500]
    parsed = urlparse(raw)
    if parsed.scheme in ('http', 'https') and parsed.netloc:
        return raw[:500]
    return ''


def _flag(settings, key, default=True):
    if not settings or key not in settings or settings.get(key) is None:
        return bool(default)
    return str(settings.get(key)).strip() not in ('0', '', 'false', 'False', 'off')


def get_appearance(settings=None):
    settings = settings or {}
    try:
        welcome_interval = int(settings.get('welcome_hero_interval_sec') or 6)
    except (TypeError, ValueError):
        welcome_interval = 6
    try:
        login_interval = int(settings.get('login_hero_interval_sec') or 8)
    except (TypeError, ValueError):
        login_interval = 8
    return {
        'welcome_tagline': (settings.get('welcome_tagline') or '').strip()
            or 'A loving community rooted in faith, growing together in Christ.',
        'welcome_verse': (settings.get('welcome_verse') or '').strip()
            or '"I am the vine; you are the branches. If you remain in me and I in you, you will bear much fruit." — John 15:5',
        'welcome_kicker': (settings.get('welcome_kicker') or '').strip(),
        'welcome_hero_mode': (settings.get('welcome_hero_mode') or 'theme').strip() or 'theme',
        'welcome_hero_interval_sec': welcome_interval,
        'login_hero_mode': (settings.get('login_hero_mode') or 'theme').strip() or 'theme',
        'login_hero_interval_sec': login_interval,
        'welcome_show_services': _flag(settings, 'welcome_show_services'),
        'welcome_show_about': _flag(settings, 'welcome_show_about'),
        'welcome_show_events': _flag(settings, 'welcome_show_events'),
        'welcome_show_verse': _flag(settings, 'welcome_show_verse'),
        'welcome_show_featured': _flag(settings, 'welcome_show_featured'),
        'welcome_show_quick_links': _flag(settings, 'welcome_show_quick_links'),
        'welcome_show_ctas': _flag(settings, 'welcome_show_ctas'),
        'welcome_featured_heading': (settings.get('welcome_featured_heading') or '').strip()
            or 'This week at our church',
        'welcome_cta1_label': (settings.get('welcome_cta1_label') or '').strip(),
        'welcome_cta1_url': sanitize_public_href(settings.get('welcome_cta1_url')),
        'welcome_cta2_label': (settings.get('welcome_cta2_label') or '').strip(),
        'welcome_cta2_url': sanitize_public_href(settings.get('welcome_cta2_url')),
    }


def list_hero_images(surface, enabled_only=True):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        sql = "SELECT * FROM site_hero_images WHERE surface = %s"
        params = [surface]
        if enabled_only:
            sql += " AND enabled = 1"
        sql += " ORDER BY sort_order ASC, id ASC"
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        for row in rows:
            row['url'] = hero_url(row.get('filename'))
        return rows
    except Exception:
        return []


def save_hero_image(surface, file_storage, caption=''):
    if not file_storage or not file_storage.filename:
        raise ValueError('Choose an image to upload.')
    if not allowed_hero_file(file_storage.filename):
        raise ValueError('Use a PNG, JPG, GIF, or WebP image.')
    existing = list_hero_images(surface, enabled_only=False)
    if len(existing) >= MAX_HEROES_PER_SURFACE:
        raise ValueError(f'You can keep up to {MAX_HEROES_PER_SURFACE} images here.')

    original = secure_filename(file_storage.filename)
    ext = original.rsplit('.', 1)[1].lower()
    filename = f'{surface}_{uuid.uuid4().hex[:12]}.{ext}'
    dest = os.path.join(hero_upload_dir(), filename)
    file_storage.save(dest)

    db = get_db()
    cur = db.cursor()
    next_order = (existing[-1]['sort_order'] + 1) if existing else 0
    cur.execute(
        """
        INSERT INTO site_hero_images (surface, filename, caption, sort_order, enabled)
        VALUES (%s, %s, %s, %s, 1)
        """,
        (surface, filename, (caption or '').strip()[:255] or None, next_order),
    )
    db.commit()
    return filename


def delete_hero_image(image_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM site_hero_images WHERE id = %s", (image_id,))
    row = cur.fetchone()
    if not row:
        return False
    cur.execute("DELETE FROM site_hero_images WHERE id = %s", (image_id,))
    db.commit()
    try:
        path = os.path.join(hero_upload_dir(), row['filename'])
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
    return True


def set_hero_enabled(image_id, enabled):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE site_hero_images SET enabled = %s WHERE id = %s",
        (1 if enabled else 0, image_id),
    )
    db.commit()


def _store_feature_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_hero_file(file_storage.filename):
        raise ValueError('Use a PNG, JPG, GIF, or WebP image.')
    original = secure_filename(file_storage.filename)
    ext = original.rsplit('.', 1)[1].lower()
    filename = f'feature_{uuid.uuid4().hex[:12]}.{ext}'
    file_storage.save(os.path.join(feature_upload_dir(), filename))
    return filename


def _delete_feature_file(filename):
    if not filename:
        return
    try:
        path = os.path.join(feature_upload_dir(), filename)
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def list_welcome_features(enabled_only=True):
    try:
        db = get_db()
        cur = db.cursor(pymysql.cursors.DictCursor)
        sql = "SELECT * FROM site_welcome_features"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY sort_order ASC, id ASC"
        cur.execute(sql)
        rows = cur.fetchall() or []
        for row in rows:
            row['url'] = feature_url(row.get('filename'))
            row['link_url'] = sanitize_public_href(row.get('link_url'))
        return rows
    except Exception:
        return []


def get_welcome_feature(feature_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM site_welcome_features WHERE id = %s", (feature_id,))
    row = cur.fetchone()
    if row:
        row['url'] = feature_url(row.get('filename'))
    return row


def save_welcome_feature(data, file_storage=None, feature_id=None):
    title = sanitize_plain_text(data.get('title'))[:160]
    if not title:
        raise ValueError('Give this highlight a title.')
    body = sanitize_plain_text(data.get('body'))[:800]
    link_url = sanitize_public_href(data.get('link_url'))
    link_label = sanitize_plain_text(data.get('link_label'))[:80]
    new_filename = _store_feature_image(file_storage) if file_storage and file_storage.filename else None

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    if feature_id:
        cur.execute("SELECT * FROM site_welcome_features WHERE id = %s", (feature_id,))
        existing = cur.fetchone()
        if not existing:
            _delete_feature_file(new_filename)
            raise ValueError('That highlight was not found.')
        filename = existing.get('filename')
        if new_filename:
            _delete_feature_file(filename)
            filename = new_filename
        cur.execute(
            """
            UPDATE site_welcome_features
            SET title = %s, body = %s, filename = %s, link_url = %s, link_label = %s
            WHERE id = %s
            """,
            (title, body or None, filename, link_url or None, link_label or None, feature_id),
        )
        db.commit()
        return feature_id

    existing = list_welcome_features(enabled_only=False)
    if len(existing) >= MAX_WELCOME_FEATURES:
        _delete_feature_file(new_filename)
        raise ValueError(f'You can keep up to {MAX_WELCOME_FEATURES} highlights on the welcome page.')
    next_order = (existing[-1]['sort_order'] + 1) if existing else 0
    cur.execute(
        """
        INSERT INTO site_welcome_features
            (title, body, filename, link_url, link_label, sort_order, enabled)
        VALUES (%s, %s, %s, %s, %s, %s, 1)
        """,
        (title, body or None, new_filename, link_url or None, link_label or None, next_order),
    )
    db.commit()
    return cur.lastrowid


def delete_welcome_feature(feature_id):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT * FROM site_welcome_features WHERE id = %s", (feature_id,))
    row = cur.fetchone()
    if not row:
        return False
    cur.execute("DELETE FROM site_welcome_features WHERE id = %s", (feature_id,))
    db.commit()
    _delete_feature_file(row.get('filename'))
    return True


def set_welcome_feature_enabled(feature_id, enabled):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE site_welcome_features SET enabled = %s WHERE id = %s",
        (1 if enabled else 0, feature_id),
    )
    db.commit()


def move_welcome_feature(feature_id, direction):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT id, sort_order FROM site_welcome_features WHERE id = %s", (feature_id,))
    current = cur.fetchone()
    if not current:
        return False
    delta = -1 if direction == 'up' else 1
    target_order = current['sort_order'] + delta
    cur.execute(
        """
        UPDATE site_welcome_features AS a
        JOIN site_welcome_features AS b ON b.sort_order = %s
        SET a.sort_order = b.sort_order, b.sort_order = a.sort_order
        WHERE a.id = %s
        """,
        (target_order, feature_id),
    )
    db.commit()
    return cur.rowcount > 0


def welcome_cta_list(settings=None):
    look = get_appearance(settings)
    if not look['welcome_show_ctas']:
        return []
    custom = []
    if look['welcome_cta1_label'] and look['welcome_cta1_url']:
        custom.append({'label': look['welcome_cta1_label'], 'url': look['welcome_cta1_url']})
    if look['welcome_cta2_label'] and look['welcome_cta2_url']:
        custom.append({'label': look['welcome_cta2_label'], 'url': look['welcome_cta2_url']})
    if custom:
        return custom
    links = [
        {
            'label': 'Upcoming events',
            'url': safe_url_for('public.public_events.public_events', '/public/events/'),
        },
        {
            'label': 'Sermons',
            'url': safe_url_for('public.public_sermons.public_sermons', '/public/sermons/'),
        },
    ]
    if (settings or {}).get('online_donations_enabled'):
        links.append({
            'label': 'Give',
            'url': safe_url_for('public.donate', '/public/donate'),
        })
    return [item for item in links if item.get('url')]


def welcome_quick_links(settings=None):
    settings = settings or {}
    links = [
        {
            'label': 'Events',
            'icon': 'fa-calendar-days',
            'url': safe_url_for('public.public_events.public_events', '/public/events/'),
        },
        {
            'label': 'Sermons',
            'icon': 'fa-book-open',
            'url': safe_url_for('public.public_sermons.public_sermons', '/public/sermons/'),
        },
        {
            'label': 'Prayers',
            'icon': 'fa-hands-praying',
            'url': safe_url_for('public.public_prayers.public_prayers', '/public/prayers/'),
        },
        {
            'label': 'Announcements',
            'icon': 'fa-bullhorn',
            'url': safe_url_for('public.public_announcements.public_announcements', '/public/announcements/'),
        },
        {
            'label': 'Bible',
            'icon': 'fa-book-bible',
            'url': safe_url_for('bible.member_study', '/bible/study'),
        },
    ]
    if settings.get('online_donations_enabled'):
        links.append({
            'label': 'Give',
            'icon': 'fa-heart',
            'url': safe_url_for('public.donate', '/public/donate'),
        })
    return [item for item in links if item.get('url')]


def appearance_context(settings=None, include_welcome_links=False):
    look = get_appearance(settings)
    welcome_images = list_hero_images('welcome') if look['welcome_hero_mode'] in ('image', 'rotating') else []
    login_images = list_hero_images('login') if look['login_hero_mode'] in ('image', 'rotating') else []
    if look['welcome_hero_mode'] == 'image':
        welcome_images = welcome_images[:1]
    if look['login_hero_mode'] == 'image':
        login_images = login_images[:1]
    features = list_welcome_features() if look['welcome_show_featured'] else []
    ctas = []
    quick_links = []
    if include_welcome_links:
        try:
            ctas = welcome_cta_list(settings)
        except Exception:
            ctas = []
        try:
            quick_links = welcome_quick_links(settings) if look['welcome_show_quick_links'] else []
        except Exception:
            quick_links = []
    return {
        'appearance': look,
        'welcome_hero_images': welcome_images,
        'login_hero_images': login_images,
        'welcome_features': features,
        'welcome_ctas': ctas,
        'welcome_quick_links': quick_links,
    }
