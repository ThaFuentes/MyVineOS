# app/routes/dreams/queries.py
# Full path: MyVineChurch/app/routes/dreams/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Dreams module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE/DELETE from the original dreams.py is now here.
# - Supports public/private/personal visibility enforcement at query level.
# - 100% MariaDB/pymysql compatible, parameterized, reusable functions.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Listing & Detail
# ----------------------------------------------------------------------
def get_dreams_list(is_logged_in=False, user_id=None, search_query=None):
    """Return dreams list with proper visibility filtering."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT d.id, d.title, d.description, d.notes, d.category, d.date_occurred,
               d.date_posted, d.visibility, d.user_id,
               COALESCE(u.username, d.contributor_name, 'Anonymous') AS poster_name
        FROM dreams d
        LEFT JOIN users u ON d.user_id = u.id
    """
    params = []

    if is_logged_in and user_id:
        sql += """
            WHERE d.visibility IN ('public', 'private')
               OR (d.visibility = 'personal' AND d.user_id = %s)
        """
        params.append(user_id)
    else:
        sql += " WHERE d.visibility = 'public'"

    if search_query:
        like_param = '%' + search_query.lower() + '%'
        sql += " AND (LOWER(d.title) LIKE %s OR LOWER(d.description) LIKE %s)"
        params.extend([like_param, like_param])

    sql += " ORDER BY d.date_posted DESC"

    cur.execute(sql, params)
    return cur.fetchall()


def get_dream_by_id(dream_id):
    """Return single dream or None."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT d.*,
               COALESCE(u.username, d.contributor_name, 'Anonymous') AS poster_name
        FROM dreams d
        LEFT JOIN users u ON d.user_id = u.id
        WHERE d.id = %s
    """, (dream_id,))
    return cur.fetchone()


# ----------------------------------------------------------------------
# CRUD Operations
# ----------------------------------------------------------------------
def create_dream(user_id, title, description, notes, category, date_occurred, visibility):
    """Insert new dream. Returns new dream_id."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO dreams
            (user_id, title, description, notes, category, date_occurred, visibility)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, title, description, notes or None, category or None, date_occurred, visibility))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_dream(dream_id, title, description, notes, category, date_occurred, visibility):
    """Update existing dream."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE dreams
            SET title = %s, description = %s, notes = %s, category = %s,
                date_occurred = %s, visibility = %s
            WHERE id = %s
        """, (title, description, notes or None, category or None, date_occurred, visibility, dream_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_dream(dream_id):
    """Delete dream. Returns True if deleted."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM dreams WHERE id = %s", (dream_id,))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Comments
# ----------------------------------------------------------------------
def get_dream_comments(dream_id):
    """Return all comments.html for a dream."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT dc.id, dc.comment, dc.date_posted, dc.user_id,
               COALESCE(u.username, dc.contributor_name, 'Anonymous') AS commenter_name
        FROM dream_comments dc
        LEFT JOIN users u ON dc.user_id = u.id
        WHERE dc.dream_id = %s
        ORDER BY dc.date_posted ASC
    """, (dream_id,))
    return cur.fetchall()


def add_dream_comment(dream_id, user_id, comment_text):
    """Add a comment to a dream."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO dream_comments (dream_id, user_id, comment)
            VALUES (%s, %s, %s)
        """, (dream_id, user_id, comment_text))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def update_dream_comment(comment_id, new_text):
    """Update an existing comment."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE dream_comments SET comment = %s WHERE id = %s", (new_text, comment_id))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise


def delete_dream_comment(comment_id):
    """Delete a comment."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM dream_comments WHERE id = %s", (comment_id,))
        db.commit()
        return cur.rowcount > 0
    except Exception:
        db.rollback()
        raise