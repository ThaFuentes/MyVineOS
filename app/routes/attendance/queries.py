# app/routes/attendance/queries.py
# Full path: MyVineChurch/app/routes/attendance/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Attendance module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE from the original attendance.py is now here.
# - 100% MariaDB/pymysql compatible, parameterized, reusable functions.
# - Designed for easy growth - add new query functions anytime without touching views.

import pymysql
from datetime import date, datetime
from app.models.db import get_db


# ----------------------------------------------------------------------
# Dashboard & Day Views
# ----------------------------------------------------------------------
def get_today_attendance_count():
    """Return count of check-ins for today."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    today_str = date.today().strftime('%Y-%m-%d')
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE DATE(service_date) = %s
    """, (today_str,))
    result = cur.fetchone()
    return result['count'] if result else 0


def get_recent_days(limit=10):
    """Return last N days with attendance counts."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT DATE(service_date) AS date, COUNT(*) AS count
        FROM attendance
        GROUP BY DATE(service_date)
        ORDER BY DATE(service_date) DESC
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


def get_day_count_and_attendees(service_date):
    """Return count + full attendee list for a specific date."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM attendance
        WHERE DATE(service_date) = %s
    """, (service_date,))
    count = cur.fetchone()['count']

    cur.execute("""
        SELECT u.id, u.first_name, u.last_name, u.username, a.check_in
        FROM attendance a
        JOIN users u ON a.user_id = u.id
        WHERE DATE(a.service_date) = %s
        ORDER BY a.check_in DESC
    """, (service_date,))
    attendees = cur.fetchall()

    return count, attendees


# ----------------------------------------------------------------------
# Kiosk Session Management
# ----------------------------------------------------------------------
def create_kiosk_session(user_id, token, expires_at):
    """Insert new kiosk session. Returns True on success."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO kiosk_sessions (token, created_by, expires_at, active)
            VALUES (%s, %s, %s, 1)
        """, (token, user_id, expires_at))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def close_kiosk_session(token):
    """Close (deactivate) kiosk session. Returns True if a row was updated."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE kiosk_sessions SET active = 0 WHERE token = %s", (token,))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def validate_kiosk_session(token):
    """Return session_row or None if invalid/expired."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT active, expires_at FROM kiosk_sessions WHERE token = %s", (token,))
    return cur.fetchone()


# ----------------------------------------------------------------------
# Kiosk Search & Check-in
# ----------------------------------------------------------------------
def search_members(search_term):
    """Return matching members for kiosk live search."""
    if not search_term:
        return []
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    like_param = f'%{search_term}%'
    cur.execute("""
        SELECT id, first_name, last_name, username
        FROM users
        WHERE LOWER(CONCAT(first_name, ' ', last_name)) LIKE LOWER(%s)
           OR LOWER(first_name) LIKE LOWER(%s)
           OR LOWER(last_name) LIKE LOWER(%s)
           OR LOWER(username) LIKE LOWER(%s)
        ORDER BY last_name, first_name
        LIMIT 200
    """, (like_param, like_param, like_param, like_param))
    return cur.fetchall()


def get_member_for_checkin(member_id):
    """Return member details needed for PIN/proxy validation."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, first_name, last_name, allow_proxy_checkin, checkin_pin
        FROM users WHERE id = %s
    """, (member_id,))
    return cur.fetchone()


def record_attendance(user_id, service_date, check_in_utc):
    """Insert or update attendance record (ON DUPLICATE KEY)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO attendance (user_id, service_date, check_in)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE check_in = %s
        """, (user_id, service_date, check_in_utc, check_in_utc))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Self Check-In Helpers
# ----------------------------------------------------------------------
def get_user_for_self_checkin(user_id):
    """Return basic user info for self-checkin page."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT first_name, last_name, username
        FROM users WHERE id = %s
    """, (user_id,))
    return cur.fetchone()


def get_existing_attendance(user_id, service_date):
    """Return existing attendance row for today (or None)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT check_in
        FROM attendance
        WHERE user_id = %s AND DATE(service_date) = %s
    """, (user_id, service_date))
    return cur.fetchone()