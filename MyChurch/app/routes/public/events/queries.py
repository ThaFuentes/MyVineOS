# MYVINECHURCH.ONLINE/app/routes/public/events/queries.py
# Full path: MYVINECHURCH.ONLINE/app/routes/public/events/queries.py
# File name: queries.py
# Brief, detailed purpose: Reusable database query functions specifically for the public Events section.
# Returns ONLY public + upcoming records (with creator_name via LEFT JOIN). Clean, efficient, and feature-specific - no generic table-name passing.
# Used by views.py for listing and single-event detail pages. 100% matches original public_events.py + shared queries.py logic for events.

from app.models.db import get_db
import pymysql.cursors


def get_public_events():
    """
    Retrieve publicly visible upcoming events for the main public events listing page.
    Ordered by event_date + event_time. Includes creator_name exactly as the original code did.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            e.*,
            COALESCE(u.username, 'Anonymous') AS creator_name
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.visibility = 'public'
          AND e.event_date >= CURDATE()
        ORDER BY e.event_date ASC, e.event_time ASC
    """)
    events = cur.fetchall()
    cur.close()
    return events


def get_public_event(event_id):
    """
    Retrieve a single public event by ID for the detail page (event_detail.html).
    Includes creator_name and all fields needed for potluck + comments.html.
    """
    db = get_db()
    cur = db.cursor(pymysql.cursors.DictCursor)

    cur.execute("""
        SELECT 
            e.*,
            COALESCE(u.username, 'Anonymous') AS creator_name
        FROM events e
        LEFT JOIN users u ON e.created_by = u.id
        WHERE e.id = %s 
          AND e.visibility = 'public'
    """, (event_id,))

    event = cur.fetchone()
    cur.close()
    return event


