# MYVINECHURCH.ONLINE/app/routes/public/announcements/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/announcements/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions specifically for the public Announcements section.
# Returns ONLY public + active records (with rich creator_name via LEFT JOIN).
# 100% rebuilt to match the public/events/queries.py and public/dreams/queries.py gold standard - uses a.* so all columns are available to views and templates.

from app.models.db import get_db
import pymysql.cursors


def get_public_announcements(limit=None):
    """
    Retrieve publicly visible and active announcements for the main public announcements listing page.
    Ordered by most recent first. Supports optional limit for previews (dashboard).
    Uses a.* + creator_name exactly as the Events/Dreams gold standard.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    sql = """
        SELECT 
            a.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                a.contributor_name,
                'Anonymous'
            ) AS creator_name
        FROM announcements a
        LEFT JOIN users u ON COALESCE(a.created_by, a.user_id) = u.id
        WHERE a.visibility = 'public'
          AND a.is_active = 1
        ORDER BY a.created_at DESC
    """

    if limit is not None:
        sql += " LIMIT %s"
        cur.execute(sql, (int(limit),))
    else:
        cur.execute(sql)

    announcements = cur.fetchall()
    cur.close()
    return announcements


def get_public_announcement(ann_id):
    """
    Retrieve a single public + active announcement by ID for the detail page.
    Includes creator_name and all fields needed for the template.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            a.*,
            COALESCE(
                CONCAT(u.first_name, ' ', u.last_name),
                u.username,
                a.contributor_name,
                'Anonymous'
            ) AS creator_name
        FROM announcements a
        LEFT JOIN users u ON COALESCE(a.created_by, a.user_id) = u.id
        WHERE a.id = %s 
          AND a.visibility = 'public'
          AND a.is_active = 1
    """, (ann_id,))

    announcement = cur.fetchone()
    cur.close()
    return announcement


