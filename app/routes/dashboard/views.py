# app/routes/dashboard/views.py
# Full path: MyVineChurch/app/routes/dashboard/views.py
# File name: views.py
# Brief, detailed purpose: All route handlers (controllers) for the Dashboard blueprint.
# - Single route /dashboard that intelligently serves public or private view based on login status.
# - 100% original behavior preserved: birthdays, prayers, dreams, prophecies, sermons, announcements, events, widgets, server-side censorship, church-local timezone formatting (now_church/format_church), visibility enforcement.
# - This is the "HTTP layer" only - thin, readable, easy to grow.
# - DB operations, time helpers, and widgets will be extracted next (queries.py / utils.py) for true scalability.

from flask import render_template, session, flash
from datetime import datetime
import pymysql

# Package-relative blueprint (defined in __init__.py)
from . import dashboard_bp

# Top-level app imports (unchanged)
from app.models.db import get_db
from app.utils.helpers import censor_text
from app.utils.time_utils import now_church, format_church


# ----------------------------------------------------------------------
# Dashboard - single URL (public for guests, full private for logged-in)
# ----------------------------------------------------------------------
@dashboard_bp.route('/dashboard')
def dashboard():
    """
    Dashboard - single URL.
    Guests: public content only -> public template.
    Logged-in: all content -> private template.
    All titles censored server-side.
    Times displayed in church local timezone.
    """
    is_logged_in = session.get('user_id') is not None
    if is_logged_in:
        try:
            from app.utils.scheduled_emails import maybe_run_scheduled_emails
            maybe_run_scheduled_emails()
        except Exception:
            pass
    user_id = session.get('user_id')
    username = session.get('username', 'User')
    role = session.get('user_role', 'Member')

    # Initialize data containers
    birthdays = []
    prayers = []
    dreams = []
    prophecies = []
    sermons = []
    announcements = []
    events = []
    widgets = []

    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    # Visibility filter
    visibility_filter = " AND visibility = 'public'" if not is_logged_in else ""

    # Church local "today" for birthdays and upcoming events
    today_local = now_church()
    today_month = today_local.month
    today_day = today_local.day
    today_str = today_local.strftime('%Y-%m-%d')

    # Today's Birthdays (month/day only)
    try:
        birthday_sql = """
            SELECT first_name, last_name, birthday
            FROM users
            WHERE MONTH(birthday) = %s
              AND DAYOFMONTH(birthday) = %s
              AND show_birthday = 1
        """
        params = (today_month, today_day)
        if is_logged_in:
            birthday_sql += " AND id != %s"
            params += (user_id,)
        cur.execute(birthday_sql, params)
        birthdays = cur.fetchall()
    except Exception as e:
        print(f"Birthdays load failed: {e}")
        flash('Failed to load birthdays.', 'error')

    # Recent Prayers
    try:
        cur.execute(f"""
            SELECT id, title, date_posted AS datetime, visibility
            FROM prayers
            WHERE 1=1 {visibility_filter}
            ORDER BY date_posted DESC
            LIMIT 5
        """)
        prayers = cur.fetchall()
        for p in prayers:
            p['title'] = censor_text(p['title'])
            if p['datetime']:
                p['formatted_date'] = format_church(p['datetime'], '%B %d, %Y')
                p['formatted_time'] = format_church(p['datetime'], '%I:%M %p')
            else:
                p['formatted_date'] = 'Unknown'
                p['formatted_time'] = ''
    except Exception as e:
        print(f"Prayers load failed: {e}")
        flash('Failed to load recent prayers.', 'error')

    # Recent Dreams & Visions
    try:
        cur.execute(f"""
            SELECT d.id, d.title, d.date_posted AS datetime, d.visibility,
                   u.username AS poster_username
            FROM dreams d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE 1=1 {visibility_filter}
            ORDER BY d.date_posted DESC
            LIMIT 5
        """)
        dreams = cur.fetchall()
        for d in dreams:
            d['title'] = censor_text(d['title'])
            if d['datetime']:
                d['formatted_date'] = format_church(d['datetime'], '%B %d, %Y')
                d['formatted_time'] = format_church(d['datetime'], '%I:%M %p')
            else:
                d['formatted_date'] = 'Unknown'
                d['formatted_time'] = ''
    except Exception as e:
        print(f"Dreams load failed: {e}")
        flash('Failed to load recent dreams.', 'error')

    # Recent Prophecies
    try:
        cur.execute(f"""
            SELECT p.id, p.title, p.created_at AS datetime, p.visibility,
                   u.username AS poster_username
            FROM prophecies p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE 1=1 {visibility_filter}
            ORDER BY p.created_at DESC
            LIMIT 5
        """)
        prophecies = cur.fetchall()
        for p in prophecies:
            p['title'] = censor_text(p['title'])
            if p['datetime']:
                p['formatted_date'] = format_church(p['datetime'], '%B %d, %Y')
                p['formatted_time'] = format_church(p['datetime'], '%I:%M %p')
            else:
                p['formatted_date'] = 'Unknown'
                p['formatted_time'] = ''
    except Exception as e:
        print(f"Prophecies load failed: {e}")
        flash('Failed to load recent prophecies.', 'error')

    # Recent Sermons
    try:
        cur.execute(f"""
            SELECT s.id, s.title, s.uploaded_at AS datetime, s.visibility,
                   u.username AS poster_username
            FROM sermons s
            LEFT JOIN users u ON s.uploaded_by = u.id
            WHERE 1=1 {visibility_filter}
            ORDER BY s.uploaded_at DESC
            LIMIT 5
        """)
        sermons = cur.fetchall()
        for s in sermons:
            s['title'] = censor_text(s['title'])
            if s['datetime']:
                s['formatted_date'] = format_church(s['datetime'], '%B %d, %Y')
                s['formatted_time'] = format_church(s['datetime'], '%I:%M %p')
            else:
                s['formatted_date'] = 'Unknown'
                s['formatted_time'] = ''
    except Exception as e:
        print(f"Sermons load failed: {e}")
        flash('Failed to load recent sermons.', 'error')

    # Recent Active Announcements
    try:
        ann_filter = " AND a.visibility = 'public'" if not is_logged_in else ""
        cur.execute(f"""
            SELECT a.id, a.title, a.created_at AS datetime, a.visibility,
                   u.username AS poster_username
            FROM announcements a
            LEFT JOIN users u ON a.created_by = u.id
            WHERE a.is_active = 1 {ann_filter}
            ORDER BY a.created_at DESC
            LIMIT 5
        """)
        announcements = cur.fetchall()
        for a in announcements:
            a['title'] = censor_text(a['title'])
            if a['datetime']:
                a['formatted_date'] = format_church(a['datetime'], '%B %d, %Y')
                a['formatted_time'] = format_church(a['datetime'], '%I:%M %p')
            else:
                a['formatted_date'] = 'Unknown'
                a['formatted_time'] = ''
    except Exception as e:
        print(f"Announcements load failed: {e}")
        flash('Failed to load recent announcements.', 'error')

    # Upcoming Events
    try:
        cur.execute(f"""
            SELECT id, event_name AS title, event_date, event_time, visibility
            FROM events
            WHERE event_date >= %s {visibility_filter}
            ORDER BY event_date ASC, event_time ASC
            LIMIT 5
        """, (today_str,))
        events = cur.fetchall()
        for e in events:
            e['title'] = censor_text(e['title'])
            e['formatted_date'] = e['event_date'].strftime('%A, %B %d, %Y')
            if e['event_time']:
                time_obj = datetime.strptime(e['event_time'], '%H:%M:%S').time()
                e['formatted_time'] = time_obj.strftime('%I:%M %p')
                e['formatted_full'] = f"{e['formatted_date']} at {e['formatted_time']}"
            else:
                e['formatted_time'] = 'All Day'
                e['formatted_full'] = e['formatted_date']
    except Exception as e:
        print(f"Events load failed: {e}")
        flash('Failed to load upcoming events.', 'error')

    # User Widgets (logged-in only)
    if is_logged_in:
        try:
            cur.execute("""
                SELECT widget_name
                FROM user_widgets
                WHERE user_id = %s AND is_enabled = 1
            """, (user_id,))
            widgets = [row['widget_name'] for row in cur.fetchall()]
        except Exception as e:
            print(f"Widgets load failed: {e}")
            flash('Failed to load widgets.', 'error')

    # Template selection
    template = 'dashboard/dashboard.html' if is_logged_in else 'public/public_dashboard.html'

    return render_template(
        template,
        username=username if is_logged_in else None,
        role=role if is_logged_in else None,
        birthdays=birthdays,
        events=events,
        prayers=prayers,
        dreams=dreams,
        prophecies=prophecies,
        sermons=sermons,
        announcements=announcements,
        widgets=widgets
    )