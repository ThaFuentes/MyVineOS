# app/routes/auth/queries.py
# Full path: MyVineChurch/app/routes/auth/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Auth module.
# - Pure data-access layer – no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE from the original auth.py is now here.
# - 100% MariaDB/pymysql compatible, parameterized, reusable functions.
# - Designed for easy growth – add new query functions anytime without touching views.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# User Count & First-User Logic
# ----------------------------------------------------------------------
def get_total_user_count():
    """Return total number of users in the system (used to decide Owner vs pending)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('SELECT COUNT(*) AS total FROM users')
    result = cur.fetchone()
    return result['total'] if result else 0


# ----------------------------------------------------------------------
# Lookup Users
# ----------------------------------------------------------------------
def get_user_by_username(username):
    """Return full user row for login (or None)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('SELECT * FROM users WHERE username = %s', (username,))
    return cur.fetchone()


def get_user_by_email(email):
    """Return user row by email (used for password reset & forgot username)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    return cur.fetchone()


def get_user_by_verification_token(token):
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute('SELECT * FROM users WHERE email_verification_token = %s', (token,))
    return cur.fetchone()


def count_pending_registrations() -> int:
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'pending'")
    row = cur.fetchone()
    return int(row['total'] if row else 0)


def get_pending_registrations():
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT id, username, first_name, last_name, email, created_at, email_verified
        FROM users WHERE role = 'pending'
        ORDER BY created_at DESC
    """)
    return cur.fetchall()


# ----------------------------------------------------------------------
# Create & Update
# ----------------------------------------------------------------------
def create_new_user(first_name, last_name, email, phone, address, birthday,
                    username, hashed_password, role, needs_approval,
                    accepts_emails, show_birthday,
                    email_verified=1, email_verification_token=None):
    """Insert new user. Returns new user ID or raises on error."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('''
            INSERT INTO users 
            (first_name, last_name, email, phone, address, birthday, username, password,
             role, needs_approval, accepts_emails, show_birthday,
             email_verified, email_verification_token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (first_name, last_name, email, phone, address, birthday, username,
              hashed_password, role, needs_approval, accepts_emails, show_birthday,
              email_verified, email_verification_token))
        db.commit()
        return cur.lastrowid
    except Exception as e:
        db.rollback()
        print(f"Create new user error: {e}")  # For debugging during rebuild
        raise


def set_verification_token(user_id, token):
    """Store a fresh verification token; keeps email_verified = 0."""
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE users SET email_verification_token = %s, email_verified = 0 WHERE id = %s",
        (token, user_id),
    )
    db.commit()


def get_unverified_user_by_email(email):
    """Return user row if this email is registered, not banned, and not yet verified."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT * FROM users
        WHERE LOWER(email) = LOWER(%s)
          AND (email_verified = 0 OR email_verified IS NULL)
          AND role != 'banned'
        LIMIT 1
    """, (email,))
    return cur.fetchone()


def mark_email_verified(user_id):
    """Mark verified and clear the one-time token so it cannot be reused."""
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE users
        SET email_verified = 1,
            email_verified_at = CURRENT_TIMESTAMP,
            email_verification_token = NULL
        WHERE id = %s
    """, (user_id,))
    db.commit()


def update_user_password(user_id, hashed_password):
    """Update password (used for reset code)."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute('UPDATE users SET password = %s WHERE id = %s',
                    (hashed_password, user_id))
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Update user password error: {e}")
        raise


# ----------------------------------------------------------------------
# Guest welcome page overview
# ----------------------------------------------------------------------
def get_welcome_overview(event_limit=5):
    """Load upcoming public events and weekly service schedule for the guest welcome page."""
    from app.routes.public.events.queries import get_public_events
    from app.models.pastoral.service_plans import get_upcoming_services_display

    upcoming_events = get_public_events()[:event_limit]

    try:
        upcoming_services = get_upcoming_services_display(limit=2)
    except Exception:
        upcoming_services = []

    return {
        'upcoming_events': upcoming_events,
        'upcoming_services': upcoming_services,
    }