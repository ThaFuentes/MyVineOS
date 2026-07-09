# MYVINECHURCH.ONLINE/app/routes/the_gathering/sermons/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/sermons/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database queries specifically for the Sermons section
# of the Gathering Place Manager.
# - Provides listing with filters/search (all/public/private), single sermon fetch,
#   and comment queries for moderation.
# - All queries are safe, efficient, and use LEFT JOINs for creator names.
# - Designed to be called only from sermons/views.py - keeps views clean.
# - 100% consistent with the_gathering/events/queries.py, prayers/queries.py,
#   dreams/queries.py, prophecies/queries.py and announcements/queries.py patterns.
# - Only this file was rebuilt - everything else on the site remains untouched and secure.

from app.models.db import get_db
from app.utils.comment_moderation import comment_count_subquery, fetch_manager_comments
import pymysql.cursors


def get_all_sermons(filter_type='all', search_query=None, limit=50):
    """Get sermons with optional filter and search for the manager listing."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    where_clauses = []
    params = []

    if filter_type == 'public':
        where_clauses.append("s.visibility = 'public'")
    elif filter_type == 'private':
        where_clauses.append("s.visibility = 'private'")

    if search_query:
        where_clauses.append("(s.title LIKE %s OR s.scripture LIKE %s OR s.sermon_text LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
        SELECT 
            s.*,
            s.uploaded_at AS created_at,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {comment_count_subquery('sermon', 's')}
        FROM sermons s
        LEFT JOIN users u ON s.created_by = u.id
        {where_sql}
        ORDER BY s.uploaded_at DESC
        LIMIT {limit}
    """

    cur.execute(query, params)
    sermons = cur.fetchall()
    cur.close()
    return sermons


def get_sermon(sermon_id):
    """Get a single sermon by ID for edit/view pages."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cc = comment_count_subquery('sermon', 's')
    cur.execute(f"""
        SELECT 
            s.*,
            s.uploaded_at AS created_at,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM sermons s
        LEFT JOIN users u ON s.created_by = u.id
        WHERE s.id = %s
    """, (sermon_id,))

    sermon = cur.fetchone()
    cur.close()
    return sermon


def get_sermon_comments(sermon_id, search=None, status_filter='all'):
    """Get all comments for a specific sermon (manager moderation)."""
    return fetch_manager_comments('sermon', sermon_id, search=search, status_filter=status_filter)


