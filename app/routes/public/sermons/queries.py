# MYVINECHURCH.ONLINE/app/routes/public/sermons/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/sermons/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions specifically for the public Sermons section.
# Returns ONLY public records (with creator_name via LEFT JOIN on uploaded_by).
# Clean, efficient, and 100% consistent with the public/events/queries.py gold standard.

from app.models.db import get_db
import pymysql.cursors


def get_public_sermons():
    """
    Retrieve publicly visible sermons for the main public sermons listing page.
    Ordered by most recent first. Includes creator_name exactly as the Events gold standard.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            s.id,
            s.title,
            s.notes,
            s.details,
            s.uploaded_at,
            COALESCE(u.username, 'Anonymous') AS creator_name
        FROM sermons s
        LEFT JOIN users u ON s.uploaded_by = u.id
        WHERE s.visibility = 'public'
        ORDER BY s.uploaded_at DESC
    """)
    sermons = cur.fetchall()
    cur.close()
    return sermons


def get_public_sermon(sermon_id):
    """
    Retrieve a single public sermon by ID for the detail page (view_sermon.html).
    Includes creator_name and all fields needed for comments.html/media.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            s.*,
            COALESCE(u.username, 'Anonymous') AS creator_name
        FROM sermons s
        LEFT JOIN users u ON s.uploaded_by = u.id
        WHERE s.id = %s 
          AND s.visibility = 'public'
    """, (sermon_id,))

    sermon = cur.fetchone()
    cur.close()
    return sermon


# print("✅ MYVINECHURCH.ONLINE public/sermons/queries.py loaded successfully (creator_name fixed to match Events gold standard)")