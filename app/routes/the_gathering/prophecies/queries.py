# MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/prophecies/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database queries specifically for the Prophecies section
# of the Gathering Place Manager.
# - Provides listing with filters/search (all/public/private), single prophecy fetch,
#   and comment queries for moderation.
# - All queries are safe, efficient, and use LEFT JOINs for creator names.
# - Designed to be called only from prophecies/views.py - keeps views clean.
# - 100% consistent with the_gathering/events/queries.py, dreams/queries.py, prayers/queries.py and announcements/queries.py patterns.
# - Only this file was rebuilt - everything else on the site remains untouched and secure.

from app.models.db import get_db
from app.utils.comment_moderation import comment_count_subquery, fetch_manager_comments
import pymysql.cursors


def get_all_prophecies(filter_type='all', search_query=None, limit=50):
    """Get prophecies with optional filter and search for the manager listing."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    where_clauses = []
    params = []

    if filter_type == 'public':
        where_clauses.append("pr.visibility = 'public'")
    elif filter_type == 'private':
        where_clauses.append("pr.visibility = 'private'")

    if search_query:
        where_clauses.append("(pr.title LIKE %s OR pr.prophecy_text LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cc = comment_count_subquery('prophecy', 'pr')
    query = f"""
        SELECT 
            pr.*,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM prophecies pr
        LEFT JOIN users u ON pr.created_by = u.id
        {where_sql}
        ORDER BY pr.created_at DESC
        LIMIT {limit}
    """

    cur.execute(query, params)
    prophecies = cur.fetchall()
    cur.close()
    return prophecies


def get_prophecy(prophecy_id):
    """Get a single prophecy by ID for edit/view pages."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cc = comment_count_subquery('prophecy', 'pr')
    cur.execute(f"""
        SELECT 
            pr.*,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM prophecies pr
        LEFT JOIN users u ON pr.created_by = u.id
        WHERE pr.id = %s
    """, (prophecy_id,))

    prophecy = cur.fetchone()
    cur.close()
    return prophecy


def get_prophecy_comments(prophecy_id, search=None, status_filter='all'):
    """Get all comments for a specific prophecy (manager moderation)."""
    return fetch_manager_comments('prophecy', prophecy_id, search=search, status_filter=status_filter)


# print(" MYVINECHURCH.ONLINE the_gathering/prophecies/queries.py loaded successfully (prophecy listing + comments.html + moderation queries ready)")