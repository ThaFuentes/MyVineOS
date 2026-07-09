# app/routes/dashboard_tgp.py
# Full path: WebChurchMan/app/routes/dashboard_tgp.py
# File name: dashboard_tgp.py
# Brief, detailed purpose: Handles the dashboard_tgp route (single URL /dashboard_tgp).
#          • Guests (not logged in): Shows public-only content → renders templates/public/public_dashboard.html (public view).
#          • Logged-in: Shows all content (public + private) → renders dashboard_tgp/gathering_dashboard.html (private view with full data).
#          No @login_required on viewing – guests see public version, logged-in see private version on SAME URL.
#          Visibility enforced at query level – public content in both, private only for logged-in.
#          FULL REBUILD: Integrated timezone-aware handling.
#                    - "Today" calculations use church local time (now_church()).
#                    - All datetime fields from DB (assumed UTC) formatted with format_church() for display.
#                    - Added 'formatted_date' and 'formatted_time' to each item for template use.
#                    - Events: separate event_date/event_time handling with church local formatting.
#                    - All existing functionality preserved exactly – only time handling updated for consistency.

from flask import Blueprint, render_template, session, flash
from app.models.db import get_db
from app.utils.helpers import censor_text
from app.utils.time_utils import now_church, format_church
from datetime import datetime
import pymysql

dashboard_bp = Blueprint('dashboard_tgp', __name__)


@dashboard_bp.route('/dashboard_tgp')
def dashboard():
    """
    Dashboard – single URL.
    Guests: public content only → public template.
    Logged-in: all content → private template.
    All titles censored server-side for display safety.
    Times displayed in church local timezone (UTC storage assumed).
    """
    is_logged_in = session.get('user_id') is not None
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

    # Church local "today" for birthdays and upcoming events_tgp
    today_local = now_church()
    today_month = today_local.month
    today_day = today_local.day
    today_str = today_local.strftime('%Y-%m-%d')

    # Today's Birthdays (month/day only – no timezone issue)
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
        error_msg = f"Birthdays load failed: {str(e)}"
        print(error_msg)
        flash('Failed to load birthdays.', 'error')

    # Recent Prayers – uses date_posted (UTC in DB)
    try:
        cur.execute(f"""
            SELECT id, title, date_posted AS datetime, visibility
            FROM prayers_tgp
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
        error_msg = f"Prayers load failed: {str(e)}"
        print(error_msg)
        flash('Failed to load recent prayers_tgp.', 'error')

    # Recent Dreams & Visions – uses date_posted (UTC in DB)
    try:
        cur.execute(f"""
            SELECT d.id, d.title, d.date_posted AS datetime, d.visibility,
                   u.username AS poster_username
            FROM dreams_tgp d
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
        error_msg = f"Dreams load failed: {str(e)}"
        print(error_msg)
        flash('Failed to load recent dreams_tgp.', 'error')

    # Recent Prophecies – uses created_at (UTC in DB)
    try:
        cur.execute(f"""
            SELECT p.id, p.title, p.created_at AS datetime, p.visibility,
                   u.username AS poster_username
            FROM prophecies_tgp p
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
        error_msg = f"Prophecies load failed: {str(e)}"
        print(error_msg)
        flash('Failed to load recent prophecies_tgp.', 'error')

    # Recent Sermons – uses uploaded_at (UTC in DB)
    try:
        cur.execute(f"""
            SELECT s.id, s.title, s.uploaded_at AS datetime, s.visibility,
                   u.username AS poster_username
            FROM sermons_tgp s
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
        error_msg = f"Sermons load failed: {str(e)}"
        print(error_msg)
        flash('Failed to load recent sermons_tgp.', 'error')

    # Recent Active Announcements – uses created_at (UTC in DB)
    try:
        ann_filter = " AND a.visibility = 'public'" if not is_logged_in else ""
        cur.execute(f"""
            SELECT a.id, a.title, a.created_at AS datetime, a.visibility,
                   u.username AS poster_username
            FROM announcements_tgp a
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
        error_msg = f"Announcements load failed: {str(e)}"
        print(error_msg)
        flash('Failed to load recent announcements_tgp.', 'error')

    # Upcoming Events (event_date is date-only, event_time is time string or NULL)
    try:
        cur.execute(f"""
            SELECT id, event_name AS title, event_date, event_time, visibility
            FROM events_tgp
            WHERE event_date >= %s {visibility_filter}
            ORDER BY event_date ASC, event_time ASC
            LIMIT 5
        """, (today_str,))
        events = cur.fetchall()
        for e in events:
            e['title'] = censor_text(e['title'])
            # Format date (local calendar date)
            e['formatted_date'] = e['event_date'].strftime('%A, %B %d, %Y')
            if e['event_time']:
                # Assume event_time is stored as local time string 'HH:MM:SS'
                # Parse and display as-is (local)
                time_obj = datetime.strptime(e['event_time'], '%H:%M:%S').time()
                e['formatted_time'] = time_obj.strftime('%I:%M %p')
                e['formatted_full'] = f"{e['formatted_date']} at {e['formatted_time']}"
            else:
                e['formatted_time'] = 'All Day'
                e['formatted_full'] = e['formatted_date']
    except Exception as e:
        error_msg = f"Events load failed: {str(e)}"
        print(error_msg)
        flash('Failed to load upcoming events_tgp.', 'error')

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
            error_msg = f"Widgets load failed: {str(e)}"
            print(error_msg)
            flash('Failed to load widgets.', 'error')

    # Template selection
    template = 'dashboard_tgp/gathering_dashboard.html' if is_logged_in else 'public/public_dashboard.html'

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