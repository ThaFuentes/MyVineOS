# MYVINECHURCH.ONLINE/app/routes/the_gathering/events/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/the_gathering/events/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database queries specifically for the Events section
# of the Gathering Place Manager.
# • Provides listing, single event, potluck signups, and comment queries for moderation.
# • All queries safe, use LEFT JOINs for creator names.
# • 100% consistent with the_gathering/dreams/queries.py and announcements/queries.py.
# • Only this file was rebuilt.

from app.models.db import get_db
from app.utils.comment_moderation import comment_count_subquery, fetch_manager_comments
import pymysql.cursors


def get_all_events(filter_type='all', search_query=None, limit=50):
    """Get events with optional filter and search for the manager listing."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    where_clauses = []
    params = []

    if filter_type == 'public':
        where_clauses.append("e.visibility = 'public'")
    elif filter_type == 'private':
        where_clauses.append("e.visibility = 'private'")

    if search_query:
        where_clauses.append("(e.event_name LIKE %s OR e.description LIKE %s OR e.location LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cc = comment_count_subquery('event', 'e')
    query = f"""
        SELECT 
            e.*,
            e.created_at AS created_at,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        {where_sql}
        ORDER BY e.event_date ASC, e.created_at DESC
        LIMIT {limit}
    """

    cur.execute(query, params)
    events = cur.fetchall()
    cur.close()
    return events


def get_event(event_id):
    """Get a single event by ID for edit/view pages."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cc = comment_count_subquery('event', 'e')
    cur.execute(f"""
        SELECT 
            e.*,
            e.created_at AS created_at,
            COALESCE(u.username, 'Anonymous') AS creator_name,
            {cc}
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.id = %s
    """, (event_id,))

    event = cur.fetchone()
    cur.close()
    return event


def get_event_potluck_signups(event_id):
    """Get potluck signups for an event (for manager moderation/editing)."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT id, name, item, quantity, note, ip, created_at
        FROM potluck_signups
        WHERE event_id = %s
        ORDER BY created_at ASC
    """, (event_id,))

    signups = cur.fetchall()
    cur.close()
    return signups


def get_event_comments(event_id, search=None, status_filter='all'):
    """Get all comments for a specific event (manager moderation)."""
    return fetch_manager_comments('event', event_id, search=search, status_filter=status_filter)


print("✅ MYVINECHURCH.ONLINE the_gathering/events/queries.py loaded successfully (event listing + potluck + comments.html + moderation queries ready)")