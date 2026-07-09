# app/routes/dashboard/queries.py
# Full path: MyVineChurch/app/routes/dashboard/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Dashboard module.
# - Pure data-access layer – no Flask routes, no templates, no flash messages.
# - Every SELECT from the original dashboard.py is now here (birthdays, prayers, dreams, prophecies, sermons, announcements, events, widgets).
# - 100% MariaDB/pymysql compatible, parameterized, reusable functions.
# - Designed for easy growth – add new dashboard sections anytime without touching views.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Today's Birthdays
# ----------------------------------------------------------------------
def get_todays_birthdays(user_id=None):
    """Return users with birthday today (exclude self if logged in)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    today_local = __import__('app.utils.time_utils', fromlist=['now_church']).now_church()
    sql = """
        SELECT first_name, last_name, birthday
        FROM users
        WHERE MONTH(birthday) = %s
          AND DAYOFMONTH(birthday) = %s
          AND show_birthday = 1
    """
    params = (today_local.month, today_local.day)

    if user_id:
        sql += " AND id != %s"
        params += (user_id,)

    cur.execute(sql, params)
    return cur.fetchall()


# ----------------------------------------------------------------------
# Recent Content (prayers, dreams, prophecies, sermons, announcements)
# ----------------------------------------------------------------------
def get_recent_prayers(is_logged_in=False):
    """Return latest 5 prayers (public only for guests)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    visibility_filter = " AND visibility = 'public'" if not is_logged_in else ""
    cur.execute(f"""
        SELECT id, title, date_posted AS datetime, visibility
        FROM prayers
        WHERE 1=1 {visibility_filter}
        ORDER BY date_posted DESC
        LIMIT 5
    """)
    return cur.fetchall()


def get_recent_dreams(is_logged_in=False):
    """Return latest 5 dreams with poster username."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    visibility_filter = " AND visibility = 'public'" if not is_logged_in else ""
    cur.execute(f"""
        SELECT d.id, d.title, d.date_posted AS datetime, d.visibility,
               u.username AS poster_username
        FROM dreams d
        LEFT JOIN users u ON d.user_id = u.id
        WHERE 1=1 {visibility_filter}
        ORDER BY d.date_posted DESC
        LIMIT 5
    """)
    return cur.fetchall()


def get_recent_prophecies(is_logged_in=False):
    """Return latest 5 prophecies with poster username."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    visibility_filter = " AND visibility = 'public'" if not is_logged_in else ""
    cur.execute(f"""
        SELECT p.id, p.title, p.created_at AS datetime, p.visibility,
               u.username AS poster_username
        FROM prophecies p
        LEFT JOIN users u ON p.user_id = u.id
        WHERE 1=1 {visibility_filter}
        ORDER BY p.created_at DESC
        LIMIT 5
    """)
    return cur.fetchall()


def get_recent_sermons(is_logged_in=False):
    """Return latest 5 sermons with poster username."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    visibility_filter = " AND visibility = 'public'" if not is_logged_in else ""
    cur.execute(f"""
        SELECT s.id, s.title, s.uploaded_at AS datetime, s.visibility,
               u.username AS poster_username
        FROM sermons s
        LEFT JOIN users u ON s.uploaded_by = u.id
        WHERE 1=1 {visibility_filter}
        ORDER BY s.uploaded_at DESC
        LIMIT 5
    """)
    return cur.fetchall()


def get_recent_announcements(is_logged_in=False):
    """Return latest 5 active announcements."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
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
    return cur.fetchall()


# ----------------------------------------------------------------------
# Upcoming Events
# ----------------------------------------------------------------------
def get_upcoming_events(today_str, is_logged_in=False):
    """Return next 5 upcoming events."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    visibility_filter = " AND visibility = 'public'" if not is_logged_in else ""
    cur.execute(f"""
        SELECT id, event_name AS title, event_date, event_time, visibility
        FROM events
        WHERE event_date >= %s {visibility_filter}
        ORDER BY event_date ASC, event_time ASC
        LIMIT 5
    """, (today_str,))
    return cur.fetchall()


# ----------------------------------------------------------------------
# User Widgets (logged-in only)
# ----------------------------------------------------------------------
def get_user_widgets(user_id):
    """Return enabled widget names for a user."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT widget_name
        FROM user_widgets
        WHERE user_id = %s AND is_enabled = 1
    """, (user_id,))
    return [row['widget_name'] for row in cur.fetchall()]