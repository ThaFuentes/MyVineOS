from app.models.db import get_db
from app.utils.comment_moderation import fetch_manager_comments
import pymysql.cursors


def get_all_prayers(filter_type='all', search_query=None, limit=500):
    """Get prayers with optional filter and search for the manager listing."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    where_clauses = []
    params = []

    if filter_type == 'public':
        where_clauses.append("p.visibility = 'public'")
    elif filter_type == 'private':
        where_clauses.append("p.visibility = 'private'")
    elif filter_type == 'pending':
        where_clauses.append("COALESCE(p.status, 'approved') = 'pending'")

    if search_query:
        where_clauses.append("(p.title LIKE %s OR p.description LIKE %s)")
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
        SELECT 
            p.*,
            p.description AS prayer_text,
            p.date_posted AS created_at,
            COALESCE(p.status, 'approved') AS status,
            COALESCE(u.username, p.contributor_name, 'Anonymous') AS creator_name,
            (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS comment_count
        FROM prayers p
        LEFT JOIN users u ON p.user_id = u.id
        {where_sql}
        ORDER BY p.date_posted DESC
        LIMIT {int(limit)}
    """

    cur.execute(query, params)
    prayers = cur.fetchall()
    cur.close()
    return prayers


def get_prayer(prayer_id):
    """Get a single prayer by ID for edit/view pages."""
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            p.*,
            p.description AS prayer_text,
            p.date_posted AS created_at,
            COALESCE(p.status, 'approved') AS status,
            COALESCE(u.username, p.contributor_name, 'Anonymous') AS creator_name,
            (SELECT COUNT(*) FROM prayers_added pa WHERE pa.prayer_request_id = p.id) AS comment_count
        FROM prayers p
        LEFT JOIN users u ON p.user_id = u.id
        WHERE p.id = %s
    """, (prayer_id,))

    prayer = cur.fetchone()
    cur.close()
    return prayer


def get_prayer_comments(prayer_id, search=None, status_filter='all'):
    """Get prayer responses from prayers_added (manager moderation)."""
    return fetch_manager_comments('prayer', prayer_id, search=search, status_filter=status_filter)


def update_prayer_status(prayer_id, status):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE prayers SET status = %s WHERE id = %s", (status, prayer_id))
    db.commit()
    cur.close()


