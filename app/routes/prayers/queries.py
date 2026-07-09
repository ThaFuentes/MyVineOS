# app/routes/prayers/queries.py
# Full path: MyVineChurch/app/routes/prayers/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Prayers module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE/DELETE from the original prayers.py is now here.
# - Supports public/private visibility enforcement at query level.
# - 100% MariaDB/pymysql compatible, parameterized, reusable functions.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Listing
# ----------------------------------------------------------------------
def get_prayers_list(is_logged_in=False, user_id=None):
    """Return prayers list with proper visibility filtering + response count."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if is_logged_in:
        cur.execute("""
            SELECT p.id, p.title, p.description, p.date_posted, p.visibility,
                   COALESCE(CONCAT(u.first_name, ' ', u.last_name), p.contributor_name, 'Anonymous') AS creator_name,
                   (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS response_count
            FROM prayers p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.visibility IN ('public', 'private')
              AND COALESCE(p.status, 'approved') != 'rejected'
            ORDER BY p.date_posted DESC
        """)
    else:
        cur.execute("""
            SELECT p.id, p.title, p.description, p.date_posted,
                   COALESCE(p.contributor_name, 'Anonymous') AS creator_name,
                   (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS response_count
            FROM prayers p
            WHERE p.visibility = 'public'
              AND COALESCE(p.status, 'approved') = 'approved'
            ORDER BY p.date_posted DESC
        """)

    return cur.fetchall()


# ----------------------------------------------------------------------
# Single Prayer + Responses
# ----------------------------------------------------------------------
def get_prayer_by_id(prayer_id, is_logged_in=False, user_id=None):
    """Return single prayer or None with visibility enforcement."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if is_logged_in:
        cur.execute("""
            SELECT p.*,
                   COALESCE(CONCAT(u.first_name, ' ', u.last_name), p.contributor_name, 'Anonymous') AS creator_name
            FROM prayers p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.id = %s AND p.visibility IN ('public', 'private')
              AND COALESCE(p.status, 'approved') != 'rejected'
        """, (prayer_id,))
    else:
        cur.execute("""
            SELECT p.*,
                   COALESCE(p.contributor_name, 'Anonymous') AS creator_name
            FROM prayers p
            WHERE p.id = %s AND p.visibility = 'public'
              AND COALESCE(p.status, 'approved') = 'approved'
        """, (prayer_id,))

    return cur.fetchone()


def get_prayer_responses(prayer_id):
    """Return all responses for a prayer."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT pa.id, pa.prayer, pa.date_added,
               COALESCE(CONCAT(u.first_name, ' ', u.last_name), pa.contributor_name, 'Anonymous') AS responder_name
        FROM prayers_added pa
        LEFT JOIN users u ON pa.user_id = u.id
        WHERE pa.prayer_request_id = %s
        ORDER BY pa.date_added ASC
    """, (prayer_id,))
    return cur.fetchall()


# ----------------------------------------------------------------------
# CRUD Operations
# ----------------------------------------------------------------------
def create_prayer(title, description, visibility, user_id, contributor_name, ip_address, status='approved'):
    """Insert new prayer request. Returns new prayer_id."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO prayers
            (title, description, visibility, user_id, contributor_name, ip_address, status, date_posted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())
        """, (title, description, visibility, user_id, contributor_name, ip_address, status))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_prayer(prayer_id, title, description, visibility):
    """Update existing prayer request."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE prayers
            SET title = %s, description = %s, visibility = %s
            WHERE id = %s
        """, (title, description, visibility, prayer_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def update_prayer_status(prayer_id, status):
    """Approve or reject a prayer request."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE prayers SET status = %s WHERE id = %s", (status, prayer_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_prayer(prayer_id):
    """Delete prayer and all its responses."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM prayers_added WHERE prayer_request_id = %s", (prayer_id,))
        cur.execute("DELETE FROM prayers WHERE id = %s", (prayer_id,))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise