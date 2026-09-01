# MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/announcements/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database queries specifically for the Announcements section
# of the Gathering Place Manager.
# - Provides listing with filters/search (active/expired/pinned/all), single announcement fetch,
#   and comment queries for moderation.
# - All queries are safe, efficient, and use LEFT JOINs for creator names.
# - Designed to be called only from announcements/views.py - keeps views clean.
# - 100% consistent with the_gathering/events/queries.py and public/events/queries.py patterns.
# - Only this file was rebuilt - everything else on the site remains untouched and secure.

from app.models.db import get_db
from app.utils.comment_moderation import comment_count_subquery, fetch_manager_comments
import pymysql.cursors
from datetime import datetime


def get_all_announcements(filter_type='all', search_query=None, limit=50):
    """Get announcements with optional filter and search for the manager listing."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    where_clauses = ["a.is_archived = 0"]  # never show archived in main list
    params = []

    if filter_type == 'pinned':
        where_clauses.append("a.is_pinned = 1")
    elif filter_type == 'active':
        where_clauses.append("a.expiration_date IS NULL OR a.expiration_date >= CURDATE()")
    elif filter_type == 'expired':
        where_clauses.append("a.expiration_date IS NOT NULL AND a.expiration_date < CURDATE()")

    if search_query:
        where_clauses.append("(a.title LIKE %s OR a.content LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cc = comment_count_subquery('announcement', 'a')
    query = f"""
        SELECT 
            a.*,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM announcements a
        LEFT JOIN users u ON a.created_by = u.id
        {where_sql}
        ORDER BY a.is_pinned DESC, a.created_at DESC
        LIMIT {limit}
    """

    cur.execute(query, params)
    announcements = cur.fetchall()
    cur.close()
    return announcements


def get_announcement(announcement_id):
    """Get a single announcement by ID for edit/view pages."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cc = comment_count_subquery('announcement', 'a')
    cur.execute(f"""
        SELECT 
            a.*,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM announcements a
        LEFT JOIN users u ON a.created_by = u.id
        WHERE a.id = %s
    """, (announcement_id,))

    announcement = cur.fetchone()
    cur.close()
    return announcement


def get_announcement_comments(announcement_id, search=None, status_filter='all'):
    """Get all comments for a specific announcement (manager moderation)."""
    return fetch_manager_comments('announcement', announcement_id, search=search, status_filter=status_filter)


# print(" MYVINECHURCH.ONLINE the_gathering/announcements/queries.py loaded successfully (announcement listing + comments.html + moderation queries ready)")