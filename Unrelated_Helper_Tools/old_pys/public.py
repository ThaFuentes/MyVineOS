# myvinechurchonline/app/routes/public.py
# Full path: myvinechurchonline/app/routes/public.py
# File name: public.py
# Brief, detailed purpose: Blueprint for ALL public-facing pages.
# Handles public dashboard_tgp (welcome + conditional previews), full listings (/events_tgp, /sermons_tgp, etc.), donate page, and single public event detail with potluck signup.
# Visibility strictly 'public' – no login required.
# FULL REBUILD: Clean structure, reusable helpers for listings/previews.
# Added server-side censored word check on public potluck signup (name + item + quantity + note).
#   - If prohibited word/phrase detected, flash error and don't save.
#   - Uses contains_censored_word() from helpers.
# Server-side display censorship: applies censor_text() to all user-generated text in previews/listings (titles, descriptions, names, items, notes).
# Ensures no obscene content displayed publicly, even from old entries.
# Preserved every existing feature/logic exactly.
# MariaDB/PyMySQL compatible: %s placeholders, CONCAT, CURDATE(), DictCursor.

from flask import Blueprint, render_template, abort, request, flash, redirect, url_for
from app.models.db import get_db
from app.utils.helpers import contains_censored_word, censor_text
import pymysql

public_bp = Blueprint('public', __name__)


# --- Reusable Helpers ---
def _get_public_previews(limit=5):
    """Fetch limited public previews for dashboard_tgp – all text censored server-side."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    previews = {}

    # Upcoming Events
    try:
        cur.execute("""
            SELECT id, event_name AS title,
                   CONCAT(event_date, ' ', COALESCE(event_time, '')) AS datetime,
                   location
            FROM events_tgp
            WHERE visibility = 'public' AND event_date >= CURDATE()
            ORDER BY event_date ASC, event_time ASC
            LIMIT %s
        """, (limit,))
        events = cur.fetchall()
        for e in events:
            e['title'] = censor_text(e['title'])
            e['location'] = censor_text(e['location'])
        previews['events_tgp'] = events
    except Exception:
        previews['events_tgp'] = []

    # Recent Prayers
    try:
        cur.execute("""
            SELECT title, date_posted AS datetime
            FROM prayers_tgp
            WHERE visibility = 'public'
            ORDER BY date_posted DESC
            LIMIT %s
        """, (limit,))
        prayers = cur.fetchall()
        for p in prayers:
            p['title'] = censor_text(p['title'])
        previews['prayers_tgp'] = prayers
    except Exception:
        previews['prayers_tgp'] = []

    # Recent Dreams & Visions
    try:
        cur.execute("""
            SELECT d.title, d.date_posted AS datetime,
                   u.username AS posted_by
            FROM dreams_tgp d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE d.visibility = 'public'
            ORDER BY d.date_posted DESC
            LIMIT %s
        """, (limit,))
        dreams = cur.fetchall()
        for d in dreams:
            d['title'] = censor_text(d['title'])
            d['posted_by'] = censor_text(d.get('posted_by', ''))
        previews['dreams_tgp'] = dreams
    except Exception:
        previews['dreams_tgp'] = []

    # Recent Prophecies
    try:
        cur.execute("""
            SELECT p.title, p.date_posted AS datetime,
                   u.username AS posted_by
            FROM prophecies_tgp p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.visibility = 'public'
            ORDER BY p.date_posted DESC
            LIMIT %s
        """, (limit,))
        prophecies = cur.fetchall()
        for p in prophecies:
            p['title'] = censor_text(p['title'])
            p['posted_by'] = censor_text(p.get('posted_by', ''))
        previews['prophecies_tgp'] = prophecies
    except Exception:
        previews['prophecies_tgp'] = []

    # Recent Sermons
    try:
        cur.execute("""
            SELECT s.title, s.uploaded_at AS datetime,
                   u.username AS posted_by
            FROM sermons_tgp s
            LEFT JOIN users u ON s.uploaded_by = u.id
            WHERE s.visibility = 'public'
            ORDER BY s.uploaded_at DESC
            LIMIT %s
        """, (limit,))
        sermons = cur.fetchall()
        for s in sermons:
            s['title'] = censor_text(s['title'])
            s['posted_by'] = censor_text(s.get('posted_by', ''))
        previews['sermons_tgp'] = sermons
    except Exception:
        previews['sermons_tgp'] = []

    # Recent Announcements
    try:
        cur.execute("""
            SELECT a.title, a.content, a.created_at AS datetime,
                   u.username AS posted_by
            FROM announcements_tgp a
            LEFT JOIN users u ON a.created_by = u.id
            WHERE a.visibility = 'public' AND a.is_active = 1
            ORDER BY a.created_at DESC
            LIMIT 10
        """)
        announcements = cur.fetchall()
        for a in announcements:
            a['title'] = censor_text(a['title'])
            a['content'] = censor_text(a['content'])
            a['posted_by'] = censor_text(a.get('posted_by', ''))
        previews['announcements_tgp'] = announcements
    except Exception:
        previews['announcements_tgp'] = []

    return previews


def _get_public_list(table, where='1=1', order_by='created_at DESC'):
    """Generic helper for full public listings – text censored server-side."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    query = f"""
        SELECT * FROM {table}
        WHERE visibility = 'public' AND {where}
        ORDER BY {order_by}
    """
    try:
        cur.execute(query)
        items = cur.fetchall()
        # Generic censorship – assume 'title' and 'description'/'content' columns
        for item in items:
            if 'title' in item:
                item['title'] = censor_text(item['title'])
            if 'description' in item:
                item['description'] = censor_text(item['description'])
            if 'content' in item:
                item['content'] = censor_text(item['content'])
        return items
    except Exception:
        return []


# --- Routes ---
@public_bp.route('/')
@public_bp.route('/public')
def public_dashboard():
    """Public landing page – clean welcome + conditional previews."""
    previews = _get_public_previews()
    return render_template('public/public_dashboard.html', **previews)


@public_bp.route('/events_tgp')
def public_events():
    """Full public events_tgp listing (upcoming only)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute("""
            SELECT id, event_name AS title, event_date, event_time, location, description, potluck_enabled
            FROM events_tgp
            WHERE visibility = 'public' AND event_date >= CURDATE()
            ORDER BY event_date ASC, event_time ASC
        """)
        events = cur.fetchall()
        for e in events:
            e['title'] = censor_text(e['title'])
            e['location'] = censor_text(e['location'])
            e['description'] = censor_text(e.get('description', ''))
    except Exception:
        events = []
    return render_template('public/events_tgp/events_tgp.html', events=events)


@public_bp.route('/events_tgp/<int:event_id>', methods=['GET', 'POST'])
def public_event_detail(event_id):
    """Public single event detail page with potluck signup (if enabled)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Fetch event (public only)
    try:
        cur.execute("""
            SELECT * FROM events_tgp
            WHERE id = %s AND visibility = 'public'
        """, (event_id,))
        event = cur.fetchone()
        if not event:
            abort(404)
        # Server-side censorship
        event['event_name'] = censor_text(event['event_name'])
        event['location'] = censor_text(event.get('location', ''))
        event['description'] = censor_text(event.get('description', ''))
    except Exception:
        abort(404)

    # Fetch potluck signups
    signups = []
    if event.get('potluck_enabled'):
        try:
            cur.execute("""
                SELECT name, item, quantity, note
                FROM potluck_signups
                WHERE event_id = %s
                ORDER BY id ASC
            """, (event_id,))
            signups = cur.fetchall()
            # Server-side censorship on signups
            for s in signups:
                s['name'] = censor_text(s['name'])
                s['item'] = censor_text(s['item'])
                s['quantity'] = censor_text(s.get('quantity', ''))
                s['note'] = censor_text(s.get('note', ''))
        except Exception:
            signups = []

    # Handle guest potluck signup POST
    if request.method == 'POST' and event.get('potluck_enabled'):
        name = request.form.get('name', '').strip()
        item = request.form.get('item', '').strip()
        quantity = request.form.get('quantity', '').strip() or None
        note = request.form.get('note', '').strip() or None

        # Censored words check
        combined_text = f"{name} {item} {quantity or ''} {note or ''}"
        if contains_censored_word(combined_text):
            flash('Your submission contains a prohibited word or phrase.', 'error')
            return redirect(url_for('public.public_event_detail', event_id=event_id))

        if not name or not item:
            flash('Name and item are required.', 'error')
            return redirect(url_for('public.public_event_detail', event_id=event_id))

        ip = request.remote_addr or 'unknown'
        try:
            cur.execute("""
                INSERT INTO potluck_signups 
                (event_id, name, item, quantity, note, ip)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (event_id, name, item, quantity, note, ip))
            db.commit()
            flash('Thank you for signing up!', 'success')
        except Exception as e:
            print(f"Potluck signup error: {e}")
            flash('Signup failed – please try again.', 'error')

        return redirect(url_for('public.public_event_detail', event_id=event_id))

    return render_template('public/events_tgp/event_detail.html',
                           event=event,
                           signups=signups)


@public_bp.route('/sermons_tgp')
def public_sermons():
    """Full public sermons_tgp listing."""
    sermons = _get_public_list('sermons_tgp', order_by='uploaded_at DESC')
    return render_template('public/sermons_tgp/sermons_tgp.html', sermons=sermons)


@public_bp.route('/announcements_tgp')
def public_announcements():
    """Full public announcements_tgp listing (active only)."""
    announcements = _get_public_list(
        'announcements_tgp',
        where='is_active = 1',
        order_by='created_at DESC'
    )
    return render_template('public/announcements_tgp/announcements_tgp.html', announcements=announcements)


@public_bp.route('/prayers_tgp')
def public_prayers():
    """Full public prayer requests listing."""
    prayers = _get_public_list('prayers_tgp', order_by='date_posted DESC')
    return render_template('public/prayers_tgp/prayers_tgp.html', prayers=prayers)


@public_bp.route('/dreams_tgp')
def public_dreams():
    """Full public dreams_tgp & visions listing."""
    dreams = _get_public_list('dreams_tgp', order_by='date_posted DESC')
    return render_template('public/dreams_tgp/dreams_tgp.html', dreams=dreams)


@public_bp.route('/prophecies_tgp')
def public_prophecies():
    """Full public prophecies_tgp listing."""
    prophecies = _get_public_list('prophecies_tgp', order_by='date_posted DESC')
    return render_template('public/prophecies_tgp/prophecies_tgp.html', prophecies=prophecies)


@public_bp.route('/donate')
def donate():
    """Public Online Giving page – hidden via 404 if disabled in Settings."""
    if not g.settings.get('online_donations_enabled'):
        abort(404)

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    options = []
    try:
        cur.execute("""
            SELECT id, name, option_type, url, embed_code, image_path
            FROM online_donation_options
            WHERE enabled = 1
            ORDER BY sort_order ASC, id ASC
        """)
        options = cur.fetchall()
        # Safe – admin-controlled
    except Exception as e:
        print(f"donate page options load error: {e}")

    return render_template('public/donate.html',
                           title=g.settings.get('donations_page_title', 'Support Our Ministry'),
                           welcome=g.settings.get('donations_welcome_text'),
                           thank_you=g.settings.get('donations_thank_you_text'),
                           extra=g.settings.get('donations_extra_text'),
                           options=options)