# MYVINECHURCH.ONLINE/app/routes/the_gathering/dreams/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/dreams/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database queries specifically for the Dreams section
# of the Gathering Place Manager.
# • Provides listing with filters/search (all/public/private), single dream fetch,
#   and comment queries for moderation.
# • All queries are safe, efficient, and use LEFT JOINs for creator names.
# • Designed to be called only from dreams/views.py — keeps views clean.
# • 100% consistent with the_gathering/announcements/queries.py and public/events/queries.py patterns.
# • Only this file was rebuilt — everything else on the site remains untouched and secure.

from app.models.db import get_db
from app.utils.comment_moderation import comment_count_subquery, fetch_manager_comments
import pymysql.cursors


def get_all_dreams(filter_type='all', search_query=None, limit=50):
    """Get dreams with optional filter and search for the manager listing."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    where_clauses = []
    params = []

    if filter_type == 'public':
        where_clauses.append("d.visibility = 'public'")
    elif filter_type == 'private':
        where_clauses.append("d.visibility = 'private'")

    if search_query:
        where_clauses.append("(d.title LIKE %s OR d.dream_text LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
        SELECT 
            d.*,
            d.date_posted AS created_at,
            {comment_count_subquery('dream', 'd')},
            COALESCE(u.username, 'Anonymous') AS creator_name
        FROM dreams d
        LEFT JOIN users u ON d.created_by = u.id
        {where_sql}
        ORDER BY d.date_posted DESC
        LIMIT {limit}
    """

    cur.execute(query, params)
    dreams = cur.fetchall()
    cur.close()
    return dreams


def get_dream(dream_id):
    """Get a single dream by ID for edit/view pages."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cc = comment_count_subquery('dream', 'd')
    cur.execute(f"""
        SELECT 
            d.*,
            d.date_posted AS created_at,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM dreams d
        LEFT JOIN users u ON d.created_by = u.id
        WHERE d.id = %s
    """, (dream_id,))

    dream = cur.fetchone()
    cur.close()
    return dream


def get_dream_comments(dream_id, search=None, status_filter='all'):
    """Get all comments for a specific dream (manager moderation)."""
    return fetch_manager_comments('dream', dream_id, search=search, status_filter=status_filter)


# print("✅ MYVINECHURCH.ONLINE the_gathering/dreams/queries.py loaded successfully (dream listing + comments.html + moderation queries ready)")