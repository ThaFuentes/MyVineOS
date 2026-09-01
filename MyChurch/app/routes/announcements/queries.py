# app/routes/announcements/queries.py
# Full path: MyVineChurch/app/routes/announcements/queries.py
# File name: queries.py
# Brief, detailed purpose: All database queries and operations for the Announcements module.
# - Pure data-access layer - no Flask routes, no templates, no flash messages.
# - Every SELECT/INSERT/UPDATE/DELETE from the original announcements.py is now here.
# - 100% MariaDB/pymysql compatible, parameterized queries (secure), reusable functions.
# - Designed for easy growth - add new query functions anytime without touching views.

import pymysql
from app.models.db import get_db


# ----------------------------------------------------------------------
# Listing (public or private dashboard)
# ----------------------------------------------------------------------
def get_announcements_list(is_logged_in=False):
    """Return all announcements (filtered for guests)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if is_logged_in:
        cur.execute("""
            SELECT a.id, a.title, a.content, a.created_at, a.visibility,
                   a.is_active, a.comments_enabled, a.created_by,
                   COALESCE(u.username, 'Unknown') AS creator_name
            FROM announcements a
            LEFT JOIN users u ON a.created_by = u.id
            ORDER BY a.created_at DESC
        """)
    else:
        cur.execute("""
            SELECT a.id, a.title, a.content, a.created_at,
                   a.visibility, a.is_active, a.comments_enabled,
                   COALESCE(u.username, 'Unknown') AS creator_name
            FROM announcements a
            LEFT JOIN users u ON a.created_by = u.id
            WHERE a.visibility = 'public' AND a.is_active = 1
            ORDER BY a.created_at DESC
        """)

    return cur.fetchall()


# ----------------------------------------------------------------------
# Single announcement + comments.html + counts
# ----------------------------------------------------------------------
def get_announcement_by_id(ann_id):
    """Return one announcement or None."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT a.*,
               COALESCE(u.username, 'Unknown') AS creator_name
        FROM announcements a
        LEFT JOIN users u ON a.created_by = u.id
        WHERE a.id = %s
    """, (ann_id,))
    return cur.fetchone()


def get_announcement_comments(ann_id):
    """Return all comments.html for one announcement."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("""
        SELECT c.comment, c.date_added,
               COALESCE(u.username, 'Anonymous') AS commenter_name
        FROM announcement_comments c
        LEFT JOIN users u ON c.user_id = u.id
        WHERE c.announcement_id = %s
        ORDER BY c.date_added ASC
    """, (ann_id,))
    return cur.fetchall()


def get_comment_count(ann_id):
    """Return comment count for one announcement."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT COUNT(*) AS cnt FROM announcement_comments WHERE announcement_id = %s", (ann_id,))
    result = cur.fetchone()
    return result['cnt'] if result else 0


def get_announcement_summary_counts():
    """Return total, active, and public counts for dashboard."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT COUNT(*) AS cnt FROM announcements")
    total_count = cur.fetchone()['cnt'] or 0

    cur.execute("SELECT COUNT(*) AS cnt FROM announcements WHERE is_active = 1")
    active_count = cur.fetchone()['cnt'] or 0

    cur.execute("SELECT COUNT(*) AS cnt FROM announcements WHERE visibility = 'public'")
    public_count = cur.fetchone()['cnt'] or 0

    return {
        'total_count': total_count,
        'active_count': active_count,
        'public_count': public_count
    }


def get_members_for_email(member_ids=None):
    """Return email list - all members or specific ones."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    if member_ids:
        placeholders = ','.join(['%s'] * len(member_ids))
        cur.execute(f"""
            SELECT email FROM users 
            WHERE id IN ({placeholders}) 
            AND email IS NOT NULL AND email != ''
        """, [int(mid) for mid in member_ids])
    else:
        cur.execute("""
            SELECT email FROM users 
            WHERE email IS NOT NULL AND email != ''
        """)

    return [r['email'] for r in cur.fetchall()]


# ----------------------------------------------------------------------
# Create / Edit / Delete / Comment
# ----------------------------------------------------------------------
def create_announcement(title, content, visibility, is_active, comments_enabled, user_id):
    """Insert new announcement. Returns new ID or raises error."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO announcements
            (title, content, visibility, is_active, comments_enabled, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, content, visibility, is_active, comments_enabled, user_id))
        db.commit()
        return cur.lastrowid
    except Exception:
        db.rollback()
        raise


def update_announcement(ann_id, title, content, visibility, is_active, comments_enabled, user_id):
    """Update existing announcement."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE announcements
            SET title = %s, content = %s, visibility = %s,
                is_active = %s, comments_enabled = %s, updated_by = %s
            WHERE id = %s
        """, (title, content, visibility, is_active, comments_enabled, user_id, ann_id))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_announcement(ann_id):
    """Delete announcement + comments.html. Returns title for logging."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT title FROM announcements WHERE id = %s", (ann_id,))
    row = cur.fetchone()
    title = row['title'] if row else 'Unknown'

    try:
        cur.execute("DELETE FROM announcement_comments WHERE announcement_id = %s", (ann_id,))
        cur.execute("DELETE FROM announcements WHERE id = %s", (ann_id,))
        db.commit()
        return title
    except Exception:
        db.rollback()
        raise


def add_announcement_comment(ann_id, user_id, comment_text):
    """Add a comment to an announcement."""
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO announcement_comments (announcement_id, user_id, comment)
            VALUES (%s, %s, %s)
        """, (ann_id, user_id, comment_text))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------------
# Get title for logging (used in email route)
# ----------------------------------------------------------------------
def get_announcement_title(ann_id):
    """Return title only (for logging)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT title, content FROM announcements WHERE id = %s", (ann_id,))
    return cur.fetchone()