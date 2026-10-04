# app/routes/prophecies/queries.py
# Full path: MyVineChurch/app/routes/prophecies/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Prophecies module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE/DELETE from the original prophecies.py is now here.
# - Supports public/private/personal visibility enforcement at query level.
# - 100% MariaDB/pymysql compatible, parameterized, reusable functions.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Listing
# ----------------------------------------------------------------------
def get_prophecies_list(is_logged_in=False, user_id=None, search_query=''):
    """Return prophecies list with visibility filtering and optional search."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT p.id, p.title, p.description, p.created_at AS date_posted, p.visibility,
               p.user_id,
               COALESCE(u.username, 'Anonymous') AS poster_name,
               (SELECT COUNT(*) FROM prophecy_comments pc WHERE pc.prophecy_id = p.id) AS comment_count
        FROM prophecies p
        LEFT JOIN users u ON p.user_id = u.id
    """
    params = []

    if not is_logged_in:
        sql += " WHERE COALESCE(p.moderation_hidden, 0) = 0 AND p.visibility = %s"
        params.append('public')
    else:
        sql += """
            WHERE COALESCE(p.moderation_hidden, 0) = 0
              AND (p.visibility IN ('public', 'private')
                   OR (p.visibility = 'personal' AND p.user_id = %s))
        """
        params.append(user_id)

    if search_query:
        like_param = '%' + search_query + '%'
        sql += " AND (LOWER(p.title) LIKE %s OR LOWER(p.description) LIKE %s)"
        params.extend([like_param, like_param])

    sql += " ORDER BY p.created_at DESC"
    cur.execute(sql, params)
    return cur.fetchall()


# ----------------------------------------------------------------------
# Single Prophecy + Comments
# ----------------------------------------------------------------------
def get_prophecy_by_id(prophecy_id, is_logged_in=False, user_id=None):
    """Return single prophecy or None with visibility enforcement."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if is_logged_in:
        cur.execute("""
            SELECT p.*,
                   COALESCE(u.username, 'Anonymous') AS poster_name
            FROM prophecies p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.id = %s AND COALESCE(p.moderation_hidden, 0) = 0
        """, (prophecy_id,))
    else:
        cur.execute("""
            SELECT p.*,
                   COALESCE(p.contributor_name, 'Anonymous') AS poster_name
            FROM prophecies p
            WHERE p.id = %s AND p.visibility = 'public' AND COALESCE(p.moderation_hidden, 0) = 0
        """, (prophecy_id,))

    return cur.fetchone()


def get_prophecy_comments(prophecy_id):
    """Return all comments.html for a prophecy."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT pc.id, pc.comment, pc.date_added, pc.user_id,
               COALESCE(u.username, 'Anonymous') AS commenter_name
        FROM prophecy_comments pc
        LEFT JOIN users u ON pc.user_id = u.id
        WHERE pc.prophecy_id = %s AND COALESCE(pc.removed, 0) = 0
        ORDER BY pc.date_added ASC
    """, (prophecy_id,))
    return cur.fetchall()


# ----------------------------------------------------------------------
# CRUD Operations
# ----------------------------------------------------------------------
def create_prophecy(title, description, visibility, user_id):
    """Insert new prophecy request. Returns new prophecy_id."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO prophecies (title, description, visibility, user_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (title, description, visibility, user_id))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_prophecy(prophecy_id, title, description, visibility):
    """Update existing prophecy."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE prophecies 
            SET title = %s, description = %s, visibility = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (title, description, visibility, prophecy_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_prophecy(prophecy_id):
    """Soft-delete a prophecy (hidden + ledger, restorable); comments stay with it."""
    from app.models import moderation as mod
    db = get_db()
    try:
        actor = mod.session_actor_id()
        if not actor:
            raise RuntimeError('delete_prophecy needs a signed-in actor')
        ok, msg = mod.soft_delete_content('prophecy', int(prophecy_id), actor, 'Deleted')
        if not ok:
            raise RuntimeError(msg)
        return True
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Comments
# ----------------------------------------------------------------------
def add_prophecy_comment(prophecy_id, user_id, comment_text):
    """Add a new comment to a prophecy."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO prophecy_comments (prophecy_id, user_id, comment, date_added)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (prophecy_id, user_id, comment_text))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def update_prophecy_comment(comment_id, comment_text):
    """Update an existing comment."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE prophecy_comments SET comment = %s WHERE id = %s", (comment_text, comment_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_prophecy_comment(comment_id):
    """Remove a comment (soft: hidden + ledger, restorable)."""
    from app.models.moderation import soft_delete_comment_auto
    db = get_db()
    try:
        return soft_delete_comment_auto('prophecy_comments', int(comment_id))
    except Exception:
        db.rollback()
        raise